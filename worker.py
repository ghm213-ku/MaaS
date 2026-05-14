"""Backend worker service for processing measurement jobs.

This service runs as a separate process and continuously processes jobs from the queue.
Each job spawns a new thread to handle the measurement.

Features:
- Continuous job polling from Redis
- Automatic retry with exponential backoff for Redis failures
- Health checking and reconnection
- Detailed logging of all operations
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.job_processor import JobProcessor
from app.services.status_manager import StatusManager
from app.services.count_rate import CountRateMeasurementHandler
from app.services.save_raw_tags import SaveRawTagsMeasurementHandler
from app.utils.logger import configure_logging
import time
from Swabian import TimeTagger

logger = configure_logging(__name__)


class BackendWorker:
    """Backend worker service that processes measurement jobs."""

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        max_retries: int = 5,
        retry_backoff: float = 2.0,
    ):
        """Initialize the backend worker.

        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database index
            max_retries: Maximum retry attempts before failing
            retry_backoff: Backoff multiplier for exponential retry (e.g., 2.0 = doubles each time)
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

        # State tracking
        self.retry_count = 0
        self.current_retry_delay = 1.0
        self.jobs_processed = 0
        self.jobs_failed = 0
        self.is_running = False

        logger.info(f"Backend worker initializing...")
        logger.info(f"  Redis: {redis_host}:{redis_port} (DB {redis_db})")
        logger.info(
            f"  Retry config: max_retries={max_retries}, backoff={retry_backoff}"
        )

        self._initialize_services()

    def _initialize_services(self):
        """Initialize StatusManager and JobProcessor with error handling."""
        try:
            logger.debug("Creating StatusManager...")
            self.status_manager = StatusManager(
                redis_host=self.redis_host,
                redis_port=self.redis_port,
                redis_db=self.redis_db,
            )

            logger.debug("Verifying Redis connection...")
            if not self.status_manager.health_check():
                raise RuntimeError("Redis health check failed")

            logger.debug("Redis connection verified")
            
            logger.debug("Initializing TimeTagger...")
            tagger = TimeTagger.createTimeTagger()
            tagger.setTestSignal([1, 2, 3, 4], True)

            logger.debug("Creating JobProcessor...")
            self.job_processor = JobProcessor(self.status_manager, tagger=tagger)

            logger.debug("Registering measurement handlers...")
            self.job_processor.register_handler(
                "count_rate", CountRateMeasurementHandler
            )
            self.job_processor.register_handler(
                "save_raw_tags", SaveRawTagsMeasurementHandler
            )

            logger.info("Backend worker initialized successfully")
            logger.info("  Handlers registered: count_rate, save_raw_tags")
            self.retry_count = 0
            self.current_retry_delay = 1.0

        except Exception as e:
            logger.error(f"Error initializing services: {e}", exc_info=True)
            raise

    def _handle_redis_disconnection(self):
        """Handle Redis disconnection with retry logic."""
        self.retry_count += 1

        if self.retry_count > self.max_retries:
            logger.error(
                f"Failed to reconnect to Redis after {self.max_retries} retries. Giving up."
            )
            raise RuntimeError(
                f"Could not reconnect to Redis after {self.max_retries} retries"
            )

        self.current_retry_delay = min(
            60.0, self.current_retry_delay * self.retry_backoff
        )

        logger.warning(
            f"Redis connection lost. Retry {self.retry_count}/{self.max_retries} "
            f"in {self.current_retry_delay:.1f} seconds..."
        )

        time.sleep(self.current_retry_delay)

        try:
            logger.debug("Attempting to reconnect to Redis...")
            self._initialize_services()
            logger.info("Successfully reconnected to Redis")
        except Exception as e:
            logger.debug(f"Reconnection attempt {self.retry_count} failed: {e}")
            self._handle_redis_disconnection()

    def run(self, poll_timeout: int = 1):
        """
        Run the backend worker.

        Continuously polls the job queue from Redis and processes jobs.

        Args:
            poll_timeout: Timeout in seconds for polling Redis
        """
        self.is_running = True
        logger.info("=" * 70)
        logger.info("Backend worker started")
        logger.info("=" * 70)
        logger.info(f"Configuration:")
        logger.info(f"  Poll timeout: {poll_timeout}s")
        logger.info(f"  Redis: {self.redis_host}:{self.redis_port}")
        logger.info(f"  Registered handlers: count_rate, save_raw_tags")
        logger.info("=" * 70)

        try:
            while self.is_running:
                try:
                    # Check Redis connection health
                    if not self.status_manager.health_check():
                        logger.warning(
                            "Redis connection unhealthy, attempting reconnection..."
                        )
                        self._handle_redis_disconnection()
                        continue

                    # Get next job from queue (blocking pop with timeout)
                    job = self.job_processor.get_next_job()

                    if job:
                        status_id = job.get("status_id")
                        measurement_type = job.get("measurement_type")
                        duration_seconds = job.get("duration_seconds")
                        metadata = job.get("metadata")

                        logger.info(
                            f"[{status_id}] Processing job: {measurement_type} "
                            f"(duration={duration_seconds}s)"
                        )
                        logger.debug(f"[{status_id}] Job metadata: {metadata}")

                        try:
                            # Process the job (spawns a thread)
                            self.job_processor.process_job(
                                status_id=status_id,
                                measurement_type=measurement_type,
                                duration_seconds=duration_seconds,
                                metadata=metadata,
                            )
                            self.jobs_processed += 1
                            logger.debug(
                                f"[{status_id}] Job processing started in background thread"
                            )

                        except Exception as e:
                            self.jobs_failed += 1
                            logger.error(
                                f"[{status_id}] Error processing job: {e}",
                                exc_info=True,
                            )
                    else:
                        # No job available, sleep briefly
                        time.sleep(poll_timeout)

                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    # Temporary error, log and continue
                    logger.error(f"Error during job polling: {e}", exc_info=True)
                    time.sleep(poll_timeout)

        except KeyboardInterrupt:
            logger.info("Received shutdown signal (CTRL+C)")

        except Exception as e:
            logger.error(f"Backend worker fatal error: {e}", exc_info=True)

        finally:
            self._shutdown()

    def _shutdown(self):
        """Clean shutdown of worker."""
        logger.info("=" * 70)
        logger.info("Backend worker shutting down...")
        logger.info("=" * 70)
        logger.info(f"Statistics:")
        logger.info(f"  Jobs processed: {self.jobs_processed}")
        logger.info(f"  Jobs failed: {self.jobs_failed}")
        logger.info(f"  Success rate: {self._calculate_success_rate():.1f}%")
        logger.info("=" * 70)

        self.is_running = False
        logger.info("Backend worker stopped")

    def _calculate_success_rate(self) -> float:
        """Calculate job success rate."""
        total = self.jobs_processed + self.jobs_failed
        if total == 0:
            return 0.0
        return (self.jobs_processed / total) * 100.0


def main():
    """Entry point for the backend worker."""
    try:
        worker = BackendWorker(
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
            max_retries=5,
            retry_backoff=2.0,
        )
        worker.run(poll_timeout=1)
    except Exception as e:
        logger.critical(f"Failed to start backend worker: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
