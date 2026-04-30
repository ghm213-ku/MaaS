"""Backend worker service for processing measurement jobs.

This service runs as a separate process and continuously processes jobs from the queue.
Each job spawns a new thread to handle the measurement.
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

logger = configure_logging(__name__)


class BackendWorker:
    """Backend worker service that processes measurement jobs."""
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
    ):
        """Initialize the backend worker."""
        self.status_manager = StatusManager(
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
        )
        self.job_processor = JobProcessor(self.status_manager)
        
        # Register handlers
        self.job_processor.register_handler("count_rate", CountRateMeasurementHandler)
        self.job_processor.register_handler("save_raw_tags", SaveRawTagsMeasurementHandler)
        
        logger.info("Backend worker initialized")
    
    def run(self, poll_interval: int = 1):
        """
        Run the backend worker.
        
        This is a simple implementation that keeps the process alive.
        In a production system, you would use RQ Worker or similar.
        
        Args:
            poll_interval: Seconds to sleep between status checks
        """
        logger.info("Backend worker started")
        logger.info(f"Registered handlers: count_rate, save_raw_tags")
        logger.info(f"Redis connection: {self.status_manager.redis_client.connection_pool.connection_kwargs}")
        
        try:
            while True:
                # Check Redis connection health
                if not self.status_manager.health_check():
                    logger.warning("Redis connection unhealthy, retrying...")
                    time.sleep(poll_interval)
                    continue
                
                # In this implementation, jobs are processed in separate threads
                # when process_job() is called from the API layer
                # The worker just keeps the process alive
                
                time.sleep(poll_interval)
        
        except KeyboardInterrupt:
            logger.info("Backend worker shutting down...")
        except Exception as e:
            logger.error(f"Backend worker error: {e}", exc_info=True)
        finally:
            logger.info("Backend worker stopped")


def main():
    """Entry point for the backend worker."""
    worker = BackendWorker(
        redis_host="localhost",
        redis_port=6379,
        redis_db=0,
    )
    worker.run()


if __name__ == "__main__":
    main()
