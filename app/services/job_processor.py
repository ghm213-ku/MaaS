"""Job processor for backend worker service.

Stopping a job
--------------
A stop request (``stop_job``, called by the web API) does three things:

1. Stores a durable stop flag in Redis (``measurement:stop_requested:<id>``).
2. Marks the measurement's status ``stopped``.
3. Publishes the id on ``measurement:stop_channel`` (pub/sub) as a fast path.

Pub/sub is fire-and-forget: a message sent while the job is still starting up,
or while the worker's listener is reconnecting, is simply lost. So every
running job also has a watcher that checks the stop flag every
``STOP_POLL_INTERVAL_SECONDS`` and stops the handler itself. A job that is
picked up from the queue after its stop flag was set never starts.

When a job whose stop was requested has fully ended, the worker writes an
acknowledgment (``measurement:stop_ack:<id>``), which the API waits for
(``wait_for_stop_ack``) so it can tell the client whether the stop took effect.

Jobs that are running on the worker are listed in the ``measurement:running``
hash (id -> type and start time).
"""

import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

import redis

from app.config import STOP_POLL_INTERVAL_SECONDS
from app.models import DEFAULT_TARGET_LOCATION, get_metadata_model
from app.services.status_manager import MeasurementStatus, StatusManager
from app.utils.path_utils import format_target_location

logger = logging.getLogger(__name__)

STOP_CHANNEL_KEY = "measurement:stop_channel"
STOP_REQUEST_PREFIX = "measurement:stop_requested:"
STOP_ACK_PREFIX = "measurement:stop_ack:"
RUNNING_JOBS_KEY = "measurement:running"

# A stop flag outlives any queued job; an acknowledgment only needs to outlive
# the API's wait for it.
STOP_REQUEST_TTL_SECONDS = 24 * 3600
STOP_ACK_TTL_SECONDS = 3600
# How often a running job refreshes the TTL of its status keys
STATUS_TTL_REFRESH_SECONDS = 60


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
        # (handler, event loop) of each running job, keyed by status_id
        self.active_handlers: Dict[str, Any] = {}
        # status_ids whose handler.stop() has already been called
        self._stopping: set = set()
        self.job_handlers: Dict[str, type] = {}  # Store handler classes only
        self.redis_client = redis_client or status_manager.redis_client
        self.job_queue_key = "measurement:job_queue"
        self.tagger = tagger  # Store tagger for creating handler instances
        self.stop_channel_key = STOP_CHANNEL_KEY
        self._pubsub = None
        self._closed = False

        if self.tagger is not None:
            self._start_stop_listener()

    # ---------- stop listener (pub/sub fast path) ----------

    def _subscribe(self):
        pubsub = self.redis_client.pubsub()
        pubsub.subscribe(self.stop_channel_key)
        return pubsub

    def _start_stop_listener(self):
        """Start a background thread to listen for stop events via Redis Pub/Sub."""
        self._pubsub = self._subscribe()
        self._pubsub_thread = threading.Thread(
            target=self._listen_for_stops, daemon=True, name="pubsub_listener"
        )
        self._pubsub_thread.start()
        logger.info("Started Redis Pub/Sub listener for stop events")

    def _listen_for_stops(self):
        """Listen for stop events; resubscribe if the Redis connection drops."""
        while not self._closed:
            try:
                for message in self._pubsub.listen():
                    if message["type"] != "message":
                        continue
                    status_id = message["data"]
                    if isinstance(status_id, bytes):
                        status_id = status_id.decode("utf-8")
                    try:
                        self._on_stop_message(status_id)
                    except Exception as e:
                        logger.error(f"[{status_id}] Error handling stop event: {e}", exc_info=True)
                return  # listen() only ends when the pubsub is closed
            except Exception as e:
                if self._closed:
                    return
                logger.error(
                    f"Stop listener lost its Redis connection ({e}); resubscribing in 1 s. "
                    "Running jobs still stop via their stop flag."
                )
                time.sleep(1)
                try:
                    self._pubsub = self._subscribe()
                    logger.info("Stop listener resubscribed")
                except Exception as sub_e:
                    logger.error(f"Stop listener could not resubscribe: {sub_e}")

    def _on_stop_message(self, status_id: str) -> None:
        """Stop the job's handler right away if it is running on this worker."""
        handler_info = self.active_handlers.get(status_id)
        if handler_info is None:
            logger.info(
                f"[{status_id}] Stop event received; job is not running on this worker "
                "(it won't start, or it will pick up its stop flag)"
            )
            return
        handler, loop = handler_info if isinstance(handler_info, tuple) else (handler_info, None)
        if loop is None or not loop.is_running():
            logger.info(
                f"[{status_id}] Stop event received while the job is starting up; "
                "its stop-flag watcher will stop it"
            )
            return

        logger.info(f"[{status_id}] Stop event received via Pub/Sub, stopping handler")
        future = asyncio.run_coroutine_threadsafe(
            self._stop_handler(status_id, handler, "pub/sub"), loop
        )

        def _log_exception(f):
            try:
                f.result()
            except Exception as inner_e:
                logger.error(f"[{status_id}] Exception while stopping handler: {inner_e}", exc_info=True)

        future.add_done_callback(_log_exception)

    def close(self) -> None:
        """Stop the pub/sub listener (used when the worker replaces this processor)."""
        self._closed = True
        if self._pubsub is not None:
            try:
                self._pubsub.close()
            except Exception as e:
                logger.debug(f"Error closing stop listener: {e}")

    def adopt_jobs_from(self, old: "JobProcessor") -> None:
        """Take over the running jobs of a processor this one replaces.

        The worker builds a new JobProcessor after a Redis reconnect; without
        this, jobs started before the reconnect could no longer be stopped.
        """
        self.active_jobs = old.active_jobs
        self.active_handlers = old.active_handlers
        self._stopping = old._stopping
        old.close()
        if self.active_jobs:
            logger.info(f"Took over {len(self.active_jobs)} running job(s): {', '.join(self.active_jobs)}")

    # ---------- stop flag and acknowledgment ----------

    def is_stop_requested(self, status_id: str) -> bool:
        """True if a stop has been requested for this measurement."""
        return self.redis_client.exists(f"{STOP_REQUEST_PREFIX}{status_id}") == 1

    def is_stop_acknowledged(self, status_id: str) -> bool:
        """True once the worker has confirmed that a stopped job has ended."""
        return self.redis_client.exists(f"{STOP_ACK_PREFIX}{status_id}") == 1

    def _ack_stop(self, status_id: str, detail: str) -> None:
        """Record that a stopped job has ended and clear its stop flag."""
        try:
            self.redis_client.set(
                f"{STOP_ACK_PREFIX}{status_id}",
                json.dumps({
                    "acknowledged_at": datetime.utcnow().isoformat(),
                    "detail": detail,
                    "worker_pid": os.getpid(),
                }),
                ex=STOP_ACK_TTL_SECONDS,
            )
            self.redis_client.delete(f"{STOP_REQUEST_PREFIX}{status_id}")
            logger.info(f"[{status_id}] Stop acknowledged: {detail}")
        except Exception as e:
            logger.error(f"[{status_id}] Failed to write stop acknowledgment: {e}", exc_info=True)

    def wait_for_stop_ack(self, status_id: str, timeout: float) -> bool:
        """Wait up to ``timeout`` seconds for the worker to acknowledge a stop."""
        deadline = time.monotonic() + timeout
        while True:
            if self.is_stop_acknowledged(status_id):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.1)

    async def _stop_handler(self, status_id: str, handler: Any, source: str) -> None:
        """Call handler.stop() once, however many stop signals arrive."""
        if status_id in self._stopping:
            return
        self._stopping.add(status_id)
        logger.info(f"[{status_id}] Stopping handler ({source})")
        try:
            await handler.stop()
        except Exception as e:
            logger.error(f"[{status_id}] Exception inside handler.stop(): {e}", exc_info=True)

    async def _watch_for_stop(self, status_id: str, handler: Any) -> None:
        """Poll the stop flag while the job runs and stop the handler when it is set.

        Also keeps the measurement's status keys from expiring, so a job running
        longer than their TTL can still be stopped through the API.
        """
        loop = asyncio.get_running_loop()
        last_refresh = loop.time()
        while True:
            await asyncio.sleep(STOP_POLL_INTERVAL_SECONDS)
            try:
                if self.is_stop_requested(status_id):
                    await self._stop_handler(status_id, handler, "stop flag")
                    return
                if loop.time() - last_refresh >= STATUS_TTL_REFRESH_SECONDS:
                    self.status_manager.refresh_ttl(status_id)
                    last_refresh = loop.time()
            except Exception as e:
                logger.warning(f"[{status_id}] Stop-flag check failed (will retry): {e}")

    async def _run_handler(self, status_id: str, handler: Any, duration_seconds, metadata):
        """Run handler.start() with a stop-flag watcher alongside it."""
        watcher = asyncio.ensure_future(self._watch_for_stop(status_id, handler))
        try:
            return await handler.start(duration_seconds, metadata)
        finally:
            watcher.cancel()
            try:
                await watcher
            except asyncio.CancelledError:
                pass

    # ---------- running-jobs registry ----------

    def _mark_running(self, status_id: str, measurement_type: str) -> None:
        try:
            self.redis_client.hset(
                RUNNING_JOBS_KEY,
                status_id,
                json.dumps({
                    "measurement_type": measurement_type,
                    "started_at": datetime.utcnow().isoformat(),
                    "worker_pid": os.getpid(),
                }),
            )
        except Exception as e:
            logger.warning(f"[{status_id}] Could not record job as running: {e}")

    def _mark_finished(self, status_id: str) -> None:
        try:
            self.redis_client.hdel(RUNNING_JOBS_KEY, status_id)
        except Exception as e:
            logger.warning(f"[{status_id}] Could not remove job from running list: {e}")

    def clear_running_jobs(self) -> None:
        """Forget jobs recorded by a previous worker process (call once at worker start)."""
        self.redis_client.delete(RUNNING_JOBS_KEY)

    def get_running_jobs(self) -> Dict[str, Dict[str, Any]]:
        """Jobs currently running on the worker: status_id -> type, start time, pid."""
        return {k: json.loads(v) for k, v in self.redis_client.hgetall(RUNNING_JOBS_KEY).items()}

    # ---------- queue ----------

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
        """Push a job onto the Redis queue; called by the web API, consumed by the worker.

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

    # ---------- running a job ----------

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

        self.active_jobs[status_id] = job_thread
        job_thread.start()

        logger.info(f"[{status_id}] Job thread started for {measurement_type}")

    def _run_job_in_thread(
        self,
        status_id: str,
        measurement_type: str,
        duration_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Run the job in the spawned thread."""
        loop = None
        stop_seen = False
        ran = False
        try:
            # If the measurement was stopped while still queued, skip running it
            existing = self.status_manager.get_status(status_id)
            if (
                existing and existing.get("status") == MeasurementStatus.STOPPED.value
            ) or self.is_stop_requested(status_id):
                stop_seen = True
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

            # Use provided metadata or fetch from status manager
            if metadata is None:
                metadata = self.status_manager.get_metadata(status_id) or {}

            if duration_seconds is None and not measurement_type.endswith("_live"):
                raise ValueError(f"duration_seconds is required for {measurement_type}")

            metadata_model_class = get_metadata_model(measurement_type)

            # Expand {datetime}, {measurement-type} and ~ in the output path
            fields = metadata_model_class.model_fields
            if "target_location" in fields:
                metadata.setdefault("target_location", DEFAULT_TARGET_LOCATION)
            for path_key in ("target_location", "target_file_path"):
                if path_key in fields and metadata.get(path_key):
                    metadata[path_key] = format_target_location(metadata[path_key], measurement_type)

            parsed_metadata = metadata_model_class(**metadata)

            # Track the handler so a stop event can reach it, then run it with
            # a stop-flag watcher (which also catches a stop that arrived
            # during the setup above).
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.active_handlers[status_id] = (handler, loop)
            self._mark_running(status_id, measurement_type)
            ran = True
            result = loop.run_until_complete(
                self._run_handler(status_id, handler, duration_seconds, parsed_metadata)
            )

            # A stop request wins over completion. Check the flag too: if the
            # stop arrived while this job was starting, the ACTIVE update above
            # may have overwritten the STOPPED status.
            current = self.status_manager.get_status(status_id)
            stopped_status = bool(current) and current.get("status") == MeasurementStatus.STOPPED.value
            if stopped_status or self.is_stop_requested(status_id):
                stop_seen = True
                if not stopped_status:
                    self.status_manager.update_status(
                        status_id, MeasurementStatus.STOPPED.value, "Measurement stopped by user"
                    )
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
            if loop is not None:
                loop.close()

            # Clean up from active jobs and handlers
            self.active_jobs.pop(status_id, None)
            self.active_handlers.pop(status_id, None)
            self._stopping.discard(status_id)
            if ran:
                self._mark_finished(status_id)

            # Confirm the stop only now that the job has really ended
            try:
                if stop_seen or self.is_stop_requested(status_id):
                    self._ack_stop(
                        status_id,
                        "measurement ended" if ran else "job skipped before starting",
                    )
            except Exception as e:
                logger.error(f"[{status_id}] Failed to acknowledge stop: {e}", exc_info=True)

    def stop_job(self, status_id: str) -> bool:
        """Request a stop of a queued or running job.

        Stores a durable stop flag (picked up by the running job within
        STOP_POLL_INTERVAL_SECONDS, or by a queued job when it is dequeued),
        marks the status stopped, and publishes a stop event so a running job
        stops immediately. Use ``wait_for_stop_ack`` to confirm it ended.
        """
        # Clear any old acknowledgment so wait_for_stop_ack sees only this stop
        self.redis_client.delete(f"{STOP_ACK_PREFIX}{status_id}")
        self.redis_client.set(
            f"{STOP_REQUEST_PREFIX}{status_id}",
            datetime.utcnow().isoformat(),
            ex=STOP_REQUEST_TTL_SECONDS,
        )

        # Update status to stopped so the running job thread does not
        # overwrite it with COMPLETED once the measurement is interrupted.
        self.status_manager.update_status(
            status_id, MeasurementStatus.STOPPED.value, "Measurement stopped by user"
        )

        receivers = self.redis_client.publish(self.stop_channel_key, status_id)
        logger.info(f"[{status_id}] Stop requested (stop event delivered to {receivers} listener(s))")
        if receivers == 0:
            logger.warning(
                f"[{status_id}] No worker is listening for stop events; the stop flag "
                "will still stop the job if a worker is running it"
            )

        return True

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
        self.close()
