"""Job processor for backend worker service."""

import asyncio
import threading
import json
from typing import Optional, Dict, Any, Callable
from datetime import datetime
import redis
from app.services.status_manager import StatusManager, MeasurementStatus
from app.models import SaveRawTagsMetadata
from app.utils.logger import configure_logging

logger = configure_logging(__name__)


class JobProcessor:
    """Processes measurement jobs in separate threads."""

    def __init__(
        self,
        status_manager: StatusManager,
        redis_client: Optional[redis.Redis] = None,
        tagger: Optional[Any] = None,
    ):
        """Initialize job processor.

        Args:
            status_manager: Status manager for tracking job status
            redis_client: Redis client (optional, uses status_manager's if not provided)
            tagger: TimeTagger instance for handlers that need it
        """
        self.status_manager = status_manager
        self.active_jobs: Dict[str, threading.Thread] = {}
        self.job_handlers: Dict[str, type] = {}  # Store handler classes only
        self.redis_client = redis_client or status_manager.redis_client
        self.job_queue_key = "measurement:job_queue"
        self.tagger = tagger  # Store tagger for creating handler instances

        # Expose handlers for backward compatibility
        self.handlers = self.job_handlers

    def register_handler(self, measurement_type: str, handler_class: type) -> None:
        """Register a handler class for a measurement type.

        Each job will create a fresh instance of the handler class in its thread.

        Args:
            measurement_type: Type of measurement (e.g., 'count_rate', 'save_raw_tags')
            handler_class: Handler class to instantiate for each job
        """
        self.job_handlers[measurement_type] = handler_class
        logger.info(f"Registered handler for measurement type: {measurement_type}")

    def enqueue_job(
        self,
        status_id: str,
        measurement_type: str,
        duration_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Enqueue a job to Redis for the worker to process.

        This is called by the web layer to queue jobs.
        The worker will pick them up from the queue.

        Args:
            status_id: Unique measurement ID
            measurement_type: Type of measurement (e.g., 'count_rate')
            duration_seconds: Duration for the measurement
            metadata: Measurement metadata (detector_id, channels, etc.)
        """
        job_data = {
            "status_id": status_id,
            "measurement_type": measurement_type,
            "duration_seconds": duration_seconds,
            "metadata": metadata or {},
        }

        # Push to Redis job queue
        self.redis_client.rpush(self.job_queue_key, json.dumps(job_data))

        logger.info(f"[{status_id}] Job enqueued: {measurement_type}")

    def get_next_job(self) -> Optional[Dict[str, Any]]:
        """Get the next job from the queue (blocking pop).

        This is called by the worker to retrieve jobs.
        Returns None if timeout occurs.
        """
        # Blocking pop with timeout
        result = self.redis_client.blpop(self.job_queue_key, timeout=1)

        if result:
            # result is (key, value) tuple
            job_json = result[1]
            return json.loads(job_json)

        return None

    def process_job(
        self,
        status_id: str,
        measurement_type: str,
        duration_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Process a measurement job in a new thread.

        This method spawns a new thread for the job and returns immediately,
        allowing other jobs to be processed concurrently.

        Called by the worker after retrieving from queue.

        Args:
            status_id: Unique measurement ID
            measurement_type: Type of measurement
            duration_seconds: Duration for the measurement
            metadata: Measurement metadata
        """
        # Create and start job thread
        job_thread = threading.Thread(
            target=self._run_job_in_thread,
            args=(status_id, measurement_type, duration_seconds, metadata),
            daemon=False,
            name=f"job-{status_id}",
        )

        job_thread.start()
        self.active_jobs[status_id] = job_thread

        logger.info(f"[{status_id}] Job thread started for {measurement_type}")

    def _run_job_in_thread(
        self,
        status_id: str,
        measurement_type: str,
        duration_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Run the job in the spawned thread."""
        try:
            # Update status to active
            self.status_manager.update_status(
                status_id,
                MeasurementStatus.ACTIVE.value,
                f"{measurement_type} measurement started",
            )

            # Get handler for this measurement type
            if measurement_type not in self.job_handlers:
                raise ValueError(f"Unknown measurement type: {measurement_type}")

            handler_class = self.job_handlers[measurement_type]

            # Create fresh handler instance for this job thread
            # Pass tagger to handlers that need it
            if self.tagger is None:
                raise RuntimeError(
                    "SaveRawTagsMeasurementHandler requires tagger but none was provided to JobProcessor"
                )
            handler = handler_class(tagger=self.tagger)

            # Use provided metadata or fetch from status manager
            if metadata is None:
                metadata = self.status_manager.get_metadata(status_id) or {}

            # Run the handler based on measurement type
            if measurement_type == "count_rate":
                self._handle_count_rate(status_id, handler, duration_seconds, metadata)
            elif measurement_type == "save_raw_tags":
                self._handle_save_raw_tags(
                    status_id, handler, duration_seconds, metadata
                )
            else:
                raise ValueError(f"Unknown measurement type: {measurement_type}")

            # Update status to completed
            self.status_manager.update_status(
                status_id,
                MeasurementStatus.COMPLETED.value,
                f"{measurement_type} measurement completed successfully",
            )

            logger.info(f"[{status_id}] Job completed successfully")

        except Exception as e:
            logger.error(f"[{status_id}] Job failed: {e}", exc_info=True)
            self.status_manager.update_status(
                status_id, MeasurementStatus.FAILED.value, f"Job failed: {str(e)}"
            )

        finally:
            # Clean up from active jobs
            if status_id in self.active_jobs:
                del self.active_jobs[status_id]

    def _handle_count_rate(
        self,
        status_id: str,
        handler: Any,
        duration_seconds: Optional[int],
        metadata: Dict[str, Any],
    ) -> None:
        """Handle count-rate measurement."""
        # Run the async handler
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(handler.start(duration_seconds, metadata))
        finally:
            loop.close()

    def _handle_save_raw_tags(
        self,
        status_id: str,
        handler: Any,
        duration_seconds: Optional[int],
        metadata: Dict[str, Any],
    ) -> None:
        """Handle save-raw-tags measurement."""
        if not duration_seconds:
            raise ValueError("duration_seconds is required for save_raw_tags")

        channel_list = metadata.get("channel_list")
        target_file_path = metadata.get("target_file_path")

        if not channel_list or not target_file_path:
            raise ValueError(
                "channel_list and target_file_path are required in metadata"
            )

        # Run the async handler
        saveRawTagMetadata = SaveRawTagsMetadata(
            channel_list=channel_list, target_file_path=target_file_path
        )
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(handler.start(duration_seconds, saveRawTagMetadata))
        finally:
            loop.close()

    def stop_job(self, status_id: str) -> bool:
        """Stop a running job (returns after stopping)."""
        # Update status to stopped
        self.status_manager.update_status(
            status_id, MeasurementStatus.STOPPED.value, "Measurement stopped by user"
        )

        # Try to remove from active jobs if present
        if status_id in self.active_jobs:
            logger.info(f"[{status_id}] Stop signal sent to job thread")
            # Note: Python threads cannot be forcibly terminated safely.
            # In a production system, you would implement a cancellation mechanism
            # (e.g., setting a flag that the job checks periodically)
        else:
            logger.info(f"[{status_id}] Job not in active jobs, but marked as stopped")

        return True

    def get_job_status(self, status_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a job."""
        return self.status_manager.get_status(status_id)

    def is_job_active(self, status_id: str) -> bool:
        """Check if a job is currently running."""
        return status_id in self.active_jobs and self.active_jobs[status_id].is_alive()
