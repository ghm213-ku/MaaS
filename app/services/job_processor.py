"""Job processor for backend worker service."""

import asyncio
import os
import threading
import json
from typing import Optional, Dict, Any, Callable
from datetime import datetime
import redis
from app.services.status_manager import StatusManager, MeasurementStatus
from app.models import (
    SaveRawTagsMetadata,
    CountRateMetadata,
    CorrelationMetadata,
    CoincidencesMetadata,
)
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
        # Live handler instances keyed by status_id, used to stop a running job
        self.active_handlers: Dict[str, Any] = {}
        self.job_handlers: Dict[str, type] = {}  # Store handler classes only
        self.redis_client = redis_client or status_manager.redis_client
        self.job_queue_key = "measurement:job_queue"
        self.tagger = tagger  # Store tagger for creating handler instances
        self.stop_channel_key = "measurement:stop_channel"

        if self.tagger is not None:
            self._start_stop_listener()

        # Expose handlers for backward compatibility
        self.handlers = self.job_handlers

    def _start_stop_listener(self):
        """Start a background thread to listen for stop events via Redis Pub/Sub."""
        self._pubsub = self.redis_client.pubsub()
        self._pubsub.subscribe(self.stop_channel_key)
        self._pubsub_thread = threading.Thread(
            target=self._listen_for_stops, daemon=True, name="pubsub_listener"
        )
        self._pubsub_thread.start()
        logger.info("Started Redis Pub/Sub listener for stop events")

    def _listen_for_stops(self):
        """Listen for stop events and halt the corresponding active handlers."""
        for message in self._pubsub.listen():
            if message["type"] == "message":
                status_id = message["data"]
                if isinstance(status_id, bytes):
                    status_id = status_id.decode("utf-8")
                handler_info = self.active_handlers.get(status_id)
                if handler_info is not None:
                    logger.info(f"[{status_id}] Stop event received via Pub/Sub, stopping handler")
                    if isinstance(handler_info, tuple):
                        handler, loop = handler_info
                    else:
                        handler, loop = handler_info, None
                    
                    try:
                        if loop is not None and loop.is_running():
                            future = asyncio.run_coroutine_threadsafe(handler.stop(), loop)
                            def _log_exception(f):
                                try:
                                    f.result()
                                except Exception as inner_e:
                                    logger.error(f"[{status_id}] Exception inside handler.stop(): {inner_e}", exc_info=True)
                            future.add_done_callback(_log_exception)
                        else:
                            new_loop = asyncio.new_event_loop()
                            new_loop.run_until_complete(handler.stop())
                            new_loop.close()
                    except Exception as e:
                        logger.error(f"[{status_id}] Error stopping handler from Pub/Sub listener: {e}", exc_info=True)

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
            # If the measurement was stopped while still queued, skip running it
            existing = self.status_manager.get_status(status_id)
            if existing and existing.get("status") == MeasurementStatus.STOPPED.value:
                logger.info(
                    f"[{status_id}] Job was stopped before starting; skipping execution"
                )
                return

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

            # Track the live handler instance so a stop request can reach it
            self.active_handlers[status_id] = handler

            # Use provided metadata or fetch from status manager
            if metadata is None:
                metadata = self.status_manager.get_metadata(status_id) or {}

            # Run the handler based on measurement type
            if measurement_type == "count_rate":
                self._handle_count_rate(handler, duration_seconds, metadata, status_id)
            elif measurement_type == "correlation":
                self._handle_correlation(handler, duration_seconds, metadata, status_id)
            elif measurement_type == "coincidences":
                self._handle_coincidences(handler, duration_seconds, metadata, status_id)
            elif measurement_type == "save_raw_tags":
                self._handle_save_raw_tags(handler, duration_seconds, metadata, status_id)
            else:
                raise ValueError(f"Unknown measurement type: {measurement_type}")

            # If the job was stopped by the user, don't overwrite the STOPPED
            # status with COMPLETED.
            current = self.status_manager.get_status(status_id)
            if current and current.get("status") == MeasurementStatus.STOPPED.value:
                logger.info(f"[{status_id}] Job was stopped by user; not marking completed")
            else:
                # Update status to completed
                self.status_manager.update_status(
                    status_id,
                    MeasurementStatus.COMPLETED.value,
                    f"{measurement_type} measurement completed successfully",
                )

                logger.info(f"[{status_id}] Job completed successfully")

        except asyncio.CancelledError:
            # Task was cancelled due to a stop request, no error logging needed
            pass
        except Exception as e:
            logger.error(f"[{status_id}] Job failed: {e}", exc_info=True)
            self.status_manager.update_status(
                status_id, MeasurementStatus.FAILED.value, f"Job failed: {str(e)}"
            )

        finally:
            # Release channels if any were booked
            try:
                self.status_manager.release_channels(status_id)
                logger.info(f"[{status_id}] Channels released after job completion")
            except Exception as e:
                logger.debug(
                    f"[{status_id}] No channels to release or release failed: {e}"
                )

            # Clean up from active jobs and handlers
            if status_id in self.active_jobs:
                del self.active_jobs[status_id]
            if status_id in self.active_handlers:
                del self.active_handlers[status_id]

    def _format_target_location(self, target_location: str, measurement_type: str) -> str:
        """Format the target location, replacing placeholders and ensuring it's a file path."""
        if not target_location:
            return target_location
            
        dt_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        formatted = target_location.replace("{datetime}", dt_str)
        formatted = formatted.replace("{measurement-type}", measurement_type)
        
        # If the path represents an existing directory or ends with a slash, append a default filename
        if os.path.isdir(formatted) or formatted.endswith(('/', '\\')):
            ext = ".tags" if measurement_type == "save_raw_tags" else ".csv"
            formatted = os.path.join(formatted, f"{measurement_type}_{dt_str}{ext}")
            
        return formatted

    def _handle_count_rate(
        self,
        handler: Any,
        duration_seconds: Optional[int],
        metadata: Dict[str, Any],
        status_id: Optional[str] = None,
    ) -> None:
        """Handle count-rate measurement."""
        if not duration_seconds:
            raise ValueError("duration_seconds is required for count_rate")

        channels = metadata.get("channels")
        if not channels:
            raise ValueError("channels are required in metadata")

        # Create CountRateMetadata from dict
        binwidth = metadata.get("binwidth", int(1e9))
        n_values = metadata.get("n_values", 1)
        target_location = metadata.get(
            "target_location", os.path.expanduser("~/Desktop/MaasData/{datetime}/{measurement-type}")
        )
        target_location = self._format_target_location(target_location, "count_rate")

        count_rate_metadata = CountRateMetadata(
            channels=channels,
            binwidth=binwidth,
            n_values=n_values,
            target_location=target_location,
        )


        # Run the async handler
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            if status_id:
                self.active_handlers[status_id] = (handler, loop)
            loop.run_until_complete(
                handler.start(duration_seconds, count_rate_metadata)
            )
        finally:
            loop.close()

    def _handle_save_raw_tags(
        self,
        handler: Any,
        duration_seconds: Optional[int],
        metadata: Dict[str, Any],
        status_id: Optional[str] = None,
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
            
        target_file_path = self._format_target_location(target_file_path, "save_raw_tags")

        # Run the async handler
        saveRawTagMetadata = SaveRawTagsMetadata(
            channel_list=channel_list, target_file_path=target_file_path
        )


        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                handler.start(duration_seconds, saveRawTagMetadata)
            )
        finally:
            loop.close()

    def _handle_correlation(
        self,
        handler: Any,
        duration_seconds: Optional[int],
        metadata: Dict[str, Any],
        status_id: Optional[str] = None,
    ) -> None:
        """Handle correlation measurement."""
        if not duration_seconds:
            raise ValueError("duration_seconds is required for correlation")

        channel1 = metadata.get("channel1")
        channel2 = metadata.get("channel2")

        if channel1 is None or channel2 is None:
            raise ValueError("channel1 and channel2 are required in metadata")

        # Create CorrelationMetadata from dict
        binwidth = metadata.get("binwidth", int(1e9))
        n_values = metadata.get("n_values", 100)
        target_location = metadata.get(
            "target_location", os.path.expanduser("~/Desktop/MaasData/{datetime}/{measurement-type}")
        )
        target_location = self._format_target_location(target_location, "correlation")

        correlation_metadata = CorrelationMetadata(
            channel1=channel1,
            channel2=channel2,
            binwidth=binwidth,
            n_values=n_values,
            target_location=target_location,
        )


        # Run the async handler
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            if status_id:
                self.active_handlers[status_id] = (handler, loop)
            loop.run_until_complete(
                handler.start(duration_seconds, correlation_metadata)
            )
        finally:
            loop.close()

    def _handle_coincidences(
        self,
        handler: Any,
        duration_seconds: Optional[int],
        metadata: Dict[str, Any],
        status_id: Optional[str] = None,
    ) -> None:
        """Handle coincidences measurement."""
        if not duration_seconds:
            raise ValueError("duration_seconds is required for coincidences")

        channels = metadata.get("channels")
        if not channels:
            raise ValueError("channels are required in metadata")

        # Create CoincidencesMetadata from dict
        binwidth = metadata.get("binwidth", int(1e9))
        n_values = metadata.get("n_values", 1)
        target_location = metadata.get(
            "target_location", os.path.expanduser("~/Desktop/MaasData/{datetime}/{measurement-type}")
        )
        target_location = self._format_target_location(target_location, "coincidences")

        coincidences_metadata = CoincidencesMetadata(
            channels=channels,
            binwidth=binwidth,
            n_values=n_values,
            target_location=target_location,
        )


        # Run the async handler
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            if status_id:
                self.active_handlers[status_id] = (handler, loop)
            loop.run_until_complete(
                handler.start(duration_seconds, coincidences_metadata)
            )
        finally:
            loop.close()

    def stop_job(self, status_id: str) -> bool:
        """Stop a running job, stopping the measurement and deleting its data file.

        Publishes a stop event via Redis Pub/Sub, which is intercepted by the worker
        to gracefully halt the active measurement.
        """
        # Update status to stopped first so the running job thread does not
        # overwrite it with COMPLETED once the measurement is interrupted.
        self.status_manager.update_status(
            status_id, MeasurementStatus.STOPPED.value, "Measurement stopped by user"
        )

        logger.info(f"[{status_id}] Publishing stop event via Redis Pub/Sub")
        self.redis_client.publish(self.stop_channel_key, status_id)
        
        return True

    def get_job_status(self, status_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a job."""
        return self.status_manager.get_status(status_id)

    def is_job_active(self, status_id: str) -> bool:
        """Check if a job is currently running."""
        return status_id in self.active_jobs and self.active_jobs[status_id].is_alive()
