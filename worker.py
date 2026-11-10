"""Worker entry point: runs measurement jobs on the Time Tagger.

Polls the Redis job queue filled by the web API (main.py) and runs each job in
its own thread with the handler registered for its measurement type. Reconnects
to Redis with exponential backoff if the connection drops.
"""

import argparse
import logging
import sys
import time

from Swabian import TimeTagger

from app.config import REDIS_DB, REDIS_HOST, REDIS_PORT
from app.handlers.coincidences import CoincidencesMeasurementHandler
from app.handlers.coincidences_live import CoincidencesLiveMeasurementHandler
from app.handlers.correlation import CorrelationMeasurementHandler
from app.handlers.count_rate import CountRateMeasurementHandler
from app.handlers.count_rate_live import CountRateLiveMeasurementHandler
from app.handlers.save_raw_tags import SaveRawTagsMeasurementHandler
from app.handlers.set_parameters import SetParametersHandler
from app.handlers.time_histograms_live import (
    CorrelationLiveMeasurementHandler,
    HistogramLiveMeasurementHandler,
    StartStopLiveMeasurementHandler,
)
from app.services.channel_parameters import record_channel_parameters
from app.services.file_logger import FileLogger
from app.services.job_processor import JobProcessor
from app.services.status_manager import StatusManager
from app.utils.logger import configure_root_logging

logger = logging.getLogger(__name__)

# Handler class for each measurement type (MeasurementType values)
HANDLERS = {
    "count_rate": CountRateMeasurementHandler,
    "count_rate_live": CountRateLiveMeasurementHandler,
    "correlation": CorrelationMeasurementHandler,
    "correlation_live": CorrelationLiveMeasurementHandler,
    "coincidences": CoincidencesMeasurementHandler,
    "coincidence": CoincidencesMeasurementHandler,
    "coincidences_live": CoincidencesLiveMeasurementHandler,
    "coincidence_live": CoincidencesLiveMeasurementHandler,
    "startstop_live": StartStopLiveMeasurementHandler,
    "histogram_live": HistogramLiveMeasurementHandler,
    "save_raw_tags": SaveRawTagsMeasurementHandler,
    "set_parameters": SetParametersHandler,
}

# Channels that get the built-in test signal when the worker runs with --testing
TEST_SIGNAL_CHANNELS = [1, 2, 3, 4, 5]


def configure_test_signals(tagger, testing: bool) -> None:
    """Set the TimeTagger's built-in test signal for this run mode.

    Normal run: the test signal is switched off on every input channel so only
    real detector signals are measured.
    Testing run: the test signal is switched on for TEST_SIGNAL_CHANNELS (and off
    on all other channels), so measurements produce data without detectors.
    """
    all_channels = list(tagger.getChannelList(TimeTagger.ChannelEdge.Rising))
    tagger.setTestSignal(all_channels, False)
    if testing:
        tagger.setTestSignal(TEST_SIGNAL_CHANNELS, True)
        logger.info(f"Testing mode: test signal enabled on channels {TEST_SIGNAL_CHANNELS}")
    else:
        logger.info("Test signal disabled on all channels")


class BackendWorker:
    """Backend worker service that processes measurement jobs."""

    def __init__(
        self,
        redis_host: str = REDIS_HOST,
        redis_port: int = REDIS_PORT,
        redis_db: int = REDIS_DB,
        max_retries: int = 5,
        retry_backoff: float = 2.0,
        testing: bool = False,
        no_hardware: bool = False,
    ):
        """Initialize the backend worker.

        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database index
            max_retries: Maximum retry attempts before failing
            retry_backoff: Backoff multiplier for exponential retry (e.g., 2.0 = doubles each time)
            testing: Enable the TimeTagger test signal on channels 1-5
                (TEST_SIGNAL_CHANNELS). When False, the test signal is off on all channels.
            no_hardware: Don't connect to a TimeTagger at all (jobs needing
                hardware will fail). Useful for exercising Redis/queue plumbing.
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.testing = testing
        self.no_hardware = no_hardware

        # State tracking
        self.retry_count = 0
        self.current_retry_delay = 1.0
        self.jobs_processed = 0
        self.jobs_failed = 0
        self.is_running = False

        logger.info("Backend worker initializing...")
        logger.info(f"  Redis: {redis_host}:{redis_port} (DB {redis_db})")
        logger.info(
            f"  Retry config: max_retries={max_retries}, backoff={retry_backoff}"
        )

        self._initialize_services()

    def _initialize_services(self):
        """Initialize StatusManager and JobProcessor with error handling."""
        try:
            logger.debug("Creating FileLogger...")
            file_logger = FileLogger()

            logger.debug("Creating StatusManager...")
            self.status_manager = StatusManager(
                redis_host=self.redis_host,
                redis_port=self.redis_port,
                redis_db=self.redis_db,
                file_logger=file_logger,
            )

            logger.debug("Verifying Redis connection...")
            if not self.status_manager.health_check():
                raise RuntimeError("Redis health check failed")

            logger.debug("Redis connection verified")

            if not self.no_hardware:
                logger.debug("Initializing TimeTagger...")
                tagger = TimeTagger.createTimeTagger()
                configure_test_signals(tagger, self.testing)
                tagger.setTriggerLevel(12, 0.0)
                tagger.setTriggerLevel(16, 0.0)
                # Publish every channel's starting trigger/delay for GET /channels/parameters
                record_channel_parameters(
                    self.status_manager.redis_client,
                    tagger,
                    tagger.getChannelList(TimeTagger.ChannelEdge.Rising),
                )
            else:
                logger.debug("No-hardware mode enabled, skipping TimeTagger initialization")
                tagger = None

            logger.debug("Creating JobProcessor...")
            self.job_processor = JobProcessor(self.status_manager, tagger=tagger)

            for measurement_type, handler_class in HANDLERS.items():
                self.job_processor.register_handler(measurement_type, handler_class)

            logger.info(f"Backend worker initialized; handlers: {', '.join(HANDLERS)}")
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
        logger.info(f"  Poll timeout: {poll_timeout}s")
        logger.info(f"  Redis: {self.redis_host}:{self.redis_port}")
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
        logger.info("Statistics:")
        logger.info(f"  Jobs processed: {self.jobs_processed}")
        logger.info(f"  Jobs failed: {self.jobs_failed}")
        logger.info(f"  Success rate: {self._calculate_success_rate():.1f}%")
        logger.info("=" * 70)

        # Stop active jobs gracefully
        try:
            if hasattr(self, 'job_processor') and self.job_processor:
                self.job_processor.shutdown_all_jobs()
        except Exception as e:
            logger.error(f"Error shutting down jobs: {e}", exc_info=True)

        # Close Redis connection
        try:
            if self.status_manager:
                logger.debug("Closing Redis connection...")
                self.status_manager.close()
                logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}", exc_info=True)

        self.is_running = False
        logger.info("=" * 70)
        logger.info("Backend worker stopped")
        logger.info("=" * 70)

    def _calculate_success_rate(self) -> float:
        """Calculate job success rate."""
        total = self.jobs_processed + self.jobs_failed
        if total == 0:
            return 0.0
        return (self.jobs_processed / total) * 100.0


def parse_args(argv=None):
    """Parse worker command-line flags."""
    parser = argparse.ArgumentParser(description="MaaS backend worker")
    parser.add_argument(
        "--testing",
        action="store_true",
        help="Enable the TimeTagger test signal on channels 1-5 "
        "(default: test signal off on all channels)",
    )
    parser.add_argument(
        "--no-hardware",
        action="store_true",
        help="Run without connecting to a TimeTagger (jobs needing hardware will fail)",
    )
    return parser.parse_args(argv)


def main():
    """Entry point for the backend worker."""
    args = parse_args()
    configure_root_logging("logs/services/worker.log")
    try:
        worker = BackendWorker(testing=args.testing, no_hardware=args.no_hardware)
        worker.run(poll_timeout=1)
    except Exception as e:
        logger.critical(f"Failed to start backend worker: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
