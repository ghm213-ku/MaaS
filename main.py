"""Main application entry point - Distributed Architecture."""

from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.services.status_manager import StatusManager
from app.services.job_processor import JobProcessor
from app.services.file_logger import initialize_file_logger
from app.api import routes
from app.utils.logger import configure_logging

logger = configure_logging(__name__)

# Global instances
status_manager: StatusManager = None
job_processor: JobProcessor = None
file_logger = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global status_manager, job_processor, file_logger

    # Startup
    logger.info("Application starting up...")

    # Initialize file logger for request logging
    file_logger = initialize_file_logger("request_logs")
    logger.info("File logger initialized")
    logger.info(f"Channel log file: {file_logger.channel_log_file}")
    logger.info(f"Measurement log file: {file_logger.measurement_log_file}")

    # Initialize status manager (includes channel management)
    status_manager = StatusManager(
        redis_host="localhost",
        redis_port=6379,
        redis_db=0,
    )

    job_processor = JobProcessor(status_manager)

    # Set up routes with job processor for enqueueing and file logger
    routes.set_processors(job_processor, status_manager, file_logger)

    logger.info("Web API layer initialized")
    logger.info("Job processing delegated to backend worker")

    yield

    # Shutdown
    logger.info("Application shutting down...")


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

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
