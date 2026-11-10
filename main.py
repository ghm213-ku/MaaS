"""Web API entry point.

Receives measurement and channel requests, records them in Redis and queues
jobs for the worker (worker.py), which talks to the Time Tagger.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import channels, dependencies, measurements, parameters
from app.api.auth import auth_router
from app.config import API_HOST, API_PORT, REDIS_DB, REDIS_HOST, REDIS_PORT
from app.middleware.auth_middleware import AuthMiddleware
from app.services.file_logger import FileLogger
from app.services.job_processor import JobProcessor
from app.services.status_manager import StatusManager
from app.utils.logger import configure_root_logging

configure_root_logging("logs/services/main.log")
logger = logging.getLogger(__name__)

status_manager: StatusManager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to Redis and register the services the endpoints use."""
    global status_manager

    logger.info("Web API starting up...")
    file_logger = FileLogger("request_logs", "logs/measurements")
    status_manager = StatusManager(
        redis_host=REDIS_HOST,
        redis_port=REDIS_PORT,
        redis_db=REDIS_DB,
        file_logger=file_logger,
    )
    if status_manager.health_check():
        logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT} (DB {REDIS_DB})")
    else:
        logger.warning(f"Redis at {REDIS_HOST}:{REDIS_PORT} is not responding")

    dependencies.set_services(JobProcessor(status_manager), status_manager, file_logger)
    logger.info("Web API ready; jobs are run by the worker")

    try:
        yield
    finally:
        logger.info("Web API shutting down...")
        status_manager.close()


app = FastAPI(
    title="MaaS - Measurements as a Service",
    description="Distributed measurement service with Redis and backend workers",
    version="2.0",
    lifespan=lifespan,
)
app.add_middleware(AuthMiddleware)
app.include_router(auth_router)
app.include_router(measurements.router)
app.include_router(channels.router)
app.include_router(parameters.router)


@app.get("/health")
async def health_check():
    """Health of the web layer and its Redis connection."""
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
    """Service information and the main endpoints."""
    return measurements.service_info()


if __name__ == "__main__":
    import uvicorn

    try:
        uvicorn.run(
            app,
            host=API_HOST,
            port=API_PORT,
            log_level="info",
            # Don't hang forever on Ctrl+C if a client keeps a connection open
            timeout_graceful_shutdown=5,
        )
    except KeyboardInterrupt:
        pass
