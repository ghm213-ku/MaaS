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
import json

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
    
    def run(self, poll_timeout: int = 1):
        """
        Run the backend worker.
        
        Continuously polls the job queue from Redis and processes jobs.
        """
        logger.info("Backend worker started")
        logger.info(f"Registered handlers: count_rate, save_raw_tags")
        logger.info(f"Redis connection: {self.status_manager.redis_client.connection_pool.connection_kwargs}")
        
        try:
            while True:
                # Check Redis connection health
                if not self.status_manager.health_check():
                    logger.warning("Redis connection unhealthy, retrying...")
                    time.sleep(poll_timeout)
                    continue
                
                # Get next job from queue (blocking pop with timeout)
                job = self.job_processor.get_next_job()
                
                if job:
                    status_id = job.get("status_id")
                    measurement_type = job.get("measurement_type")
                    duration_seconds = job.get("duration_seconds")
                    metadata = job.get("metadata")
                    
                    logger.info(f"[{status_id}] Processing job: {measurement_type}")
                    
                    try:
                        # Process the job (spawns a thread)
                        self.job_processor.process_job(
                            status_id=status_id,
                            measurement_type=measurement_type,
                            duration_seconds=duration_seconds,
                            metadata=metadata,
                        )
                    except Exception as e:
                        logger.error(f"[{status_id}] Error processing job: {e}", exc_info=True)
        
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
