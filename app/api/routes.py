"""API routes for measurement requests."""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, Callable
from app.models import (
    CountRateMeasurementRequest,
    MeasurementResponse,
    MeasurementStatusResponse,
    ErrorResponse,
)
from app.services.measurement import MeasurementService
from app.utils.logger import configure_logging
from datetime import datetime

logger = configure_logging(__name__)

router = APIRouter(prefix="/api/v1/measurements", tags=["measurements"])

# This will be set by main.py
_get_service: Optional[Callable[[], MeasurementService]] = None


def set_service_provider(provider: Callable[[], MeasurementService]) -> None:
    """Set the service provider function."""
    global _get_service
    _get_service = provider


def get_measurement_service() -> MeasurementService:
    """Dependency injection for measurement service."""
    if _get_service is None:
        raise RuntimeError("Service provider not initialized")
    return _get_service()


@router.post("/count-rate", response_model=MeasurementResponse, status_code=201)
async def start_count_rate_measurement(
    request: CountRateMeasurementRequest,
    service: MeasurementService = Depends(get_measurement_service),
) -> MeasurementResponse:
    """
    Start a new count-rate measurement request.
    
    Returns a unique measurement ID to be used for status queries and stopping.
    
    Example:
        POST /api/v1/measurements/count-rate
        {
            "measurement_type": "count_rate",
            "duration_seconds": 60,
            "metadata": {"detector_id": "det_001"}
        }
    """
    logger.info(f"Received count-rate measurement request: {request.dict()}")
    
    try:
        # Start measurement
        measurement_id = await service.start_measurement(
            measurement_type=request.measurement_type.value,
            duration_seconds=request.duration_seconds,
            metadata=request.metadata,
        )
        
        logger.info(f"[{measurement_id}] Count-rate measurement started successfully")
        
        return MeasurementResponse(
            measurement_id=measurement_id,
            measurement_type=request.measurement_type,
            status="active",
            started_at=datetime.utcnow(),
            message=f"Count-rate measurement started. Use ID '{measurement_id}' to query status or stop.",
        )
        
    except Exception as e:
        logger.error(f"Failed to start count-rate measurement: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.delete("/{measurement_id}", response_model=MeasurementResponse)
async def stop_measurement(
    measurement_id: str,
    service: MeasurementService = Depends(get_measurement_service),
) -> MeasurementResponse:
    """
    Stop an active measurement request.
    
    Only active measurements can be stopped. Returns the final results.
    
    Args:
        measurement_id: The unique ID returned when starting the measurement
        
    Returns:
        Measurement response with results
        
    Raises:
        404: If measurement not found
        409: If measurement is not active
    """
    logger.info(f"[{measurement_id}] Received stop request")
    
    try:
        # Verify measurement exists
        try:
            measurement = service.get_measurement_status(measurement_id)
        except ValueError:
            logger.warning(f"[{measurement_id}] Stop requested for non-existent measurement")
            raise HTTPException(
                status_code=404,
                detail=f"Measurement '{measurement_id}' not found",
            )
        
        # Stop the measurement
        results = await service.stop_measurement(measurement_id)
        
        logger.info(f"[{measurement_id}] Measurement stopped with results: {results}")
        
        return MeasurementResponse(
            measurement_id=measurement_id,
            measurement_type=measurement.measurement_type,
            status="stopped",
            started_at=measurement.started_at,
            message=f"Measurement stopped successfully. Results: {results}",
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"[{measurement_id}] {str(e)}")
        raise HTTPException(
            status_code=409,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"[{measurement_id}] Failed to stop measurement: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/{measurement_id}/status", response_model=MeasurementStatusResponse)
async def get_measurement_status(
    measurement_id: str,
    service: MeasurementService = Depends(get_measurement_service),
) -> MeasurementStatusResponse:
    """
    Query the status of an active or completed measurement.
    
    Args:
        measurement_id: The unique ID returned when starting the measurement
        
    Returns:
        Current status and duration information
        
    Raises:
        404: If measurement not found
    """
    logger.debug(f"[{measurement_id}] Status query received")
    
    try:
        measurement = service.get_measurement_status(measurement_id)
        
        return MeasurementStatusResponse(
            measurement_id=measurement_id,
            measurement_type=measurement.measurement_type,
            status=measurement.status,
            started_at=measurement.started_at,
            duration_so_far=measurement.get_duration(),
            metadata=measurement.metadata,
            results=measurement.results,
        )
        
    except ValueError:
        logger.warning(f"[{measurement_id}] Status query for non-existent measurement")
        raise HTTPException(
            status_code=404,
            detail=f"Measurement '{measurement_id}' not found",
        )
    except Exception as e:
        logger.error(f"[{measurement_id}] Failed to get measurement status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/", response_model=dict)
async def list_measurements(
    service: MeasurementService = Depends(get_measurement_service),
    status: Optional[str] = Query(None, description="Filter by status (active, stopped, error)"),
) -> dict:
    """
    List all measurements, optionally filtered by status.
    
    Args:
        status: Optional status filter
        
    Returns:
        Dictionary with measurement summaries
    """
    logger.debug(f"List measurements request - filter status={status}")
    
    try:
        # This would need to be implemented in MeasurementService
        # For now, return a basic response
        return {
            "message": "List measurements endpoint",
            "note": "Full implementation can be added as needed",
        }
    except Exception as e:
        logger.error(f"Failed to list measurements: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
