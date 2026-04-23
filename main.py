"""MaaS - Measurement as a Service
Local HTTPS service for managing count-rate and other measurements.
"""
import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse

from config import (
    SERVICE_HOST,
    SERVICE_PORT,
    SERVICE_NAME,
    SSL_CERT_FILE,
    SSL_KEY_FILE,
)
from app.utils.ssl_utils import generate_self_signed_cert
from app.utils.logger import configure_logging
from app.services.measurement import MeasurementService
from app.services.count_rate import CountRateMeasurementHandler
from app.api import routes

logger = configure_logging(__name__)

# Global measurement service instance
measurement_service: MeasurementService = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan event handler."""
    # Startup
    logger.info("=" * 80)
    logger.info(f"Starting {SERVICE_NAME}")
    logger.info("=" * 80)
    
    # Initialize measurement service
    global measurement_service
    measurement_service = MeasurementService()
    
    # Register handlers
    measurement_service.register_handler("count_rate", CountRateMeasurementHandler)
    logger.info("Measurement handlers registered")
    
    # Set up dependency provider for routes
    routes.set_service_provider(lambda: measurement_service)
    
    # Use localhost for display URLs (0.0.0.0 is not a valid client address)
    display_host = "localhost" if SERVICE_HOST == "0.0.0.0" else SERVICE_HOST
    logger.info(f"Service ready on https://{display_host}:{SERVICE_PORT}")
    logger.info("=" * 80)
    
    yield
    
    # Shutdown
    logger.info("=" * 80)
    logger.info("Shutting down service")
    logger.info("=" * 80)
    
    await measurement_service.cleanup()
    logger.info("Cleanup completed")


def get_measurement_service_static() -> MeasurementService:
    """Get the global measurement service instance."""
    if measurement_service is None:
        raise RuntimeError("Measurement service not initialized")
    return measurement_service


# Create FastAPI application
app = FastAPI(
    title=SERVICE_NAME,
    description="Local HTTPS service for measurement management",
    version="1.0.0",
    lifespan=lifespan,
)


# Include routes
app.include_router(routes.router)


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    logger.debug("Health check request")
    return JSONResponse(
        status_code=200,
        content={"status": "healthy", "service": SERVICE_NAME},
    )


@app.get("/", tags=["root"])
async def root():
    """Root endpoint with API information."""
    logger.debug("Root endpoint request")
    return JSONResponse(
        status_code=200,
        content={
            "service": SERVICE_NAME,
            "version": "1.0.0",
            "endpoints": {
                "health": "/health",
                "docs": "/docs",
                "start_measurement": "POST /api/v1/measurements/count-rate",
                "stop_measurement": "DELETE /api/v1/measurements/{measurement_id}",
                "get_status": "GET /api/v1/measurements/{measurement_id}/status",
            },
        },
    )


def main():
    """Main entry point."""
    logger.info(f"Generating SSL certificate if needed")
    
    try:
        # Generate or verify SSL certificates
        cert_file, key_file = generate_self_signed_cert(
            SSL_CERT_FILE,
            SSL_KEY_FILE,
            hostname="localhost",
        )
        
        # Use localhost for display URLs (0.0.0.0 is not a valid client address)
        display_host = "localhost" if SERVICE_HOST == "0.0.0.0" else SERVICE_HOST
        
        logger.info(f"Starting HTTPS server on https://{display_host}:{SERVICE_PORT}")
        logger.info(f"API Documentation: https://{display_host}:{SERVICE_PORT}/docs")
        logger.info(f"Health check: https://{display_host}:{SERVICE_PORT}/health")
        logger.info(f"\nNote: This uses a self-signed certificate. Ignore SSL warnings in clients.")
        
        # Start Uvicorn server with SSL
        uvicorn.run(
            app,
            host=SERVICE_HOST,
            port=SERVICE_PORT,
            ssl_certfile=str(cert_file),
            ssl_keyfile=str(key_file),
            log_config={
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "default": {
                        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    },
                },
                "handlers": {
                    "default": {
                        "formatter": "default",
                        "class": "logging.StreamHandler",
                        "stream": "ext://sys.stdout",
                    },
                },
                "loggers": {
                    "uvicorn": {
                        "handlers": ["default"],
                        "level": "INFO",
                    },
                    "uvicorn.access": {
                        "handlers": ["default"],
                        "level": "INFO",
                        "propagate": False,
                    },
                },
            },
        )
        
    except Exception as e:
        logger.error(f"Failed to start service: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
