"""Main application entry point - Distributed Architecture."""

from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.services.status_manager import StatusManager
from app.services.job_processor import JobProcessor
from app.services.file_logger import initialize_file_logger
from app.api import routes
from app.utils.logger import configure_logging, configure_root_logging

# Configure root logger first - all child loggers will inherit this configuration
# This ensures all logs from all modules (routes, services, etc.) go to the file
configure_root_logging("logs/services/main.log")

logger = configure_logging(__name__)

# Global instances
status_manager: StatusManager = None
job_processor: JobProcessor = None
file_logger = None


class AppMetrics:
    """Track application metrics."""

    def __init__(self):
        self.startup_time = None
        self.total_requests = 0
        self.total_errors = 0

    def reset(self):
        """Reset metrics."""
        self.startup_time = None
        self.total_requests = 0
        self.total_errors = 0


app_metrics = AppMetrics()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global status_manager, job_processor, file_logger

    # Startup
    logger.info("=" * 70)
    logger.info("Web API layer starting up...")
    logger.info("=" * 70)

    from datetime import datetime

    app_metrics.startup_time = datetime.utcnow()
    logger.info(f"Startup time: {app_metrics.startup_time.isoformat()}")

    # Initialize file logger for request logging
    file_logger = initialize_file_logger("request_logs", "logs/measurements")
    logger.info("File logger initialized")
    logger.info(f"  Channel log file: {file_logger.channel_log_file}")
    logger.info(f"  Measurement log file: {file_logger.measurement_log_file}")
    logger.info(
        f"  Measurement status log file: {file_logger.measurement_status_log_file}"
    )

    # Initialize status manager (includes channel management)
    try:
        status_manager = StatusManager(
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
            file_logger=file_logger,
        )
        logger.info("StatusManager initialized with Redis connection")

        # Verify Redis connection
        if status_manager.health_check():
            logger.info("Redis health check passed")
        else:
            logger.warning("Redis health check failed")

    except Exception as e:
        logger.error(f"Failed to initialize StatusManager: {e}", exc_info=True)
        raise

    job_processor = JobProcessor(status_manager)

    # Set up routes with job processor for enqueueing and file logger
    routes.set_processors(job_processor, status_manager, file_logger)

    logger.info("=" * 70)
    logger.info("Web API layer initialized successfully")
    logger.info("Job processing delegated to backend worker")
    logger.info("Configuration:")
    logger.info(f"  Redis: localhost:6379 (DB 0)")
    logger.info(f"  File logging: enabled")
    logger.info("=" * 70)

    try:
        yield
    finally:
        # Shutdown
        logger.info("=" * 70)
        logger.info("Web API layer shutting down...")
        logger.info("=" * 70)

        # Log shutdown statistics
        from datetime import datetime

        if app_metrics.startup_time:
            runtime = datetime.utcnow() - app_metrics.startup_time
            logger.info(f"Statistics:")
            logger.info(f"  Total requests processed: {app_metrics.total_requests}")
            logger.info(f"  Total errors: {app_metrics.total_errors}")
            logger.info(f"  Runtime: {runtime}")
            if app_metrics.total_requests > 0:
                error_rate = (
                    app_metrics.total_errors / app_metrics.total_requests
                ) * 100
                logger.info(f"  Error rate: {error_rate:.1f}%")

        # Close Redis connection
        try:
            if status_manager:
                logger.debug("Closing Redis connection...")
                status_manager.close()
                logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}", exc_info=True)

        logger.info("=" * 70)
        logger.info("Web API layer stopped")
        logger.info("=" * 70)


# Create FastAPI app with lifespan
app = FastAPI(
    title="MaaS - Measurements as a Service",
    description="Distributed measurement service with Redis and backend workers",
    version="2.0",
    lifespan=lifespan,
)


# Include routers
app.include_router(routes.measurement_router)
app.include_router(routes.channels_router)
app.include_router(routes.parameters_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    redis_healthy = True
    if status_manager:
        try:
            redis_healthy = status_manager.health_check()
        except Exception:
            redis_healthy = False

    return {
        "status": "healthy" if redis_healthy else "unhealthy",
        "service": "MaaS",
        "version": "2.0",
        "components": {
            "web_layer": "healthy",
            "redis": "healthy" if redis_healthy else "unhealthy",
            "job_processor": "ready",
        },
    }


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "MaaS - Measurements as a Service",
        "version": "2.0",
        "architecture": "Distributed (Web Layer + Redis + Backend Workers)",
        "measurement_endpoints": {
            "start_count_rate": "POST /api/v1/measurements/count-rate",
            "start_correlation": "POST /api/v1/measurements/correlation",
            "start_coincidences": "POST /api/v1/measurements/coincidences",
            "start_save_raw_tags": "POST /api/v1/measurements/save-raw-tags",
            "get_status": "GET /api/v1/measurements/{measurement_id}/status",
            "stop_measurement": "DELETE /api/v1/measurements/{measurement_id}",
        },
        "channel_endpoints": {
            "list_channels": "GET /api/v1/channels/",
            "list_available": "GET /api/v1/channels/available",
            "book_channels": "POST /api/v1/channels/book",
            "release_channels": "POST /api/v1/channels/release/{booked_by}",
        },
        "docs": "GET /docs",
        "health": "GET /health",
    }


if __name__ == "__main__":
    import uvicorn

    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
        )
    except KeyboardInterrupt:
        # Graceful shutdown - uvicorn already handles cleanup via lifespan
        pass
