"""Job processor for backend worker service."""

import asyncio
import os
import threading
import json
from typing import Optional, Dict, Any, Callable
from datetime import datetime
import redis
from app.services.status_manager import StatusManager, MeasurementStatus
from app.payloads import MeasurementPayloadMapper
from app.utils.path_utils import format_target_location
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
        try:
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
        except (ValueError, ConnectionError, Exception) as e:
            logger.debug(f"Pub/Sub listener stopped: {e}")

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
            daemon=True,
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

            if not existing:
                logger.warning(
                    f"[{status_id}] Status not found before starting job; creating it."
                )
                self.status_manager.create_status(
                    status_id=status_id,
                    measurement_type=measurement_type,
                    duration_seconds=duration_seconds,
                    metadata=metadata,
                )

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
                    f"{measurement_type} measurement requires a Time Tagger but none was provided to JobProcessor"
                )
            handler = handler_class(tagger=self.tagger)

            # Inject context for handlers that might need it
            handler.status_id = status_id
            handler.redis_client = self.redis_client

            # Track the live handler instance so a stop request can reach it
            self.active_handlers[status_id] = handler

            # Use provided metadata or fetch from status manager
            if metadata is None:
                metadata = self.status_manager.get_metadata(status_id) or {}

            # Generic execution pipeline replacing redundant _handle_* methods
            if duration_seconds is None and not measurement_type.endswith("_live"):
                raise ValueError(f"duration_seconds is required for {measurement_type}")

            try:
                metadata_model_class = MeasurementPayloadMapper.get_metadata_model_for_type(measurement_type)
            except ValueError:
                raise ValueError(f"Unknown measurement type: {measurement_type}")

            # Apply format to target_location/target_file_path
            path_key = "target_file_path" if measurement_type == "save_raw_tags" else "target_location"
            
            # For types other than save_raw_tags, provide a default if missing
            if path_key == "target_location" and path_key not in metadata:
                metadata[path_key] = os.path.expanduser("~/Desktop/MaasData/{datetime}/{measurement-type}")
                
            if path_key in metadata:
                metadata[path_key] = format_target_location(metadata[path_key], measurement_type)

            # Instantiate the proper Pydantic model. Validation happens automatically here.
            parsed_metadata = metadata_model_class(**metadata)

            # Run the async handler
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                if status_id:
                    self.active_handlers[status_id] = (handler, loop)
                result = loop.run_until_complete(
                    handler.start(duration_seconds, parsed_metadata)
                )
            finally:
                loop.close()

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
                    results=result
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

            # Clean up from active jobs and handlers
            if status_id in self.active_jobs:
                del self.active_jobs[status_id]
            if status_id in self.active_handlers:
                del self.active_handlers[status_id]





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

    def shutdown_all_jobs(self):
        """Shutdown all active jobs and wait for them to finish."""
        logger.info(f"Shutting down {len(self.active_jobs)} active jobs...")
        
        # Send stop signal to all running jobs
        for status_id in list(self.active_jobs.keys()):
            self.stop_job(status_id)
            
        # Wait for threads to complete
        for status_id, thread in list(self.active_jobs.items()):
            if thread.is_alive():
                logger.debug(f"Waiting for job thread {status_id} to finish...")
                thread.join(timeout=2.0)
