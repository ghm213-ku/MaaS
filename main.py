"""Main application entry point - Distributed Architecture."""
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.services.job_processor import JobProcessor
from app.services.status_manager import StatusManager
from app.services.count_rate import CountRateMeasurementHandler
from app.services.save_raw_tags import SaveRawTagsMeasurementHandler
from app.api import routes
from app.utils.logger import configure_logging

logger = configure_logging(__name__)

# Global instances
status_manager: StatusManager = None
job_processor: JobProcessor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global status_manager, job_processor
    
    # Startup
    logger.info("Application starting up...")
    
    # Initialize status manager and job processor
    status_manager = StatusManager(
        redis_host="localhost",
        redis_port=6379,
        redis_db=0,
    )
    
    job_processor = JobProcessor(status_manager)
    job_processor.register_handler("count_rate", CountRateMeasurementHandler)
    job_processor.register_handler("save_raw_tags", SaveRawTagsMeasurementHandler)
    
    # Set up routes
    routes.set_processors(job_processor, status_manager)
    
    logger.info("Distributed measurement system initialized")
    logger.info("Components: StatusManager (Redis), JobProcessor (Thread Pool)")
    
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


# Include routes
app.include_router(routes.router)


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
        "endpoints": {
            "start_measurement": "POST /api/v1/measurements/count-rate (or /save-raw-tags)",
            "start_count_rate": "POST /api/v1/measurements/count-rate",
            "start_save_raw_tags": "POST /api/v1/measurements/save-raw-tags",
            "get_status": "GET /api/v1/measurements/{measurement_id}/status",
            "stop_measurement": "DELETE /api/v1/measurements/{measurement_id}",
            "health": "GET /health",
            "api_docs": "GET /docs",
        },
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
