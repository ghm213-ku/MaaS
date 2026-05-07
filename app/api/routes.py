"""API routes for measurement requests - Distributed Architecture."""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime
import uuid

from app.models import (
    CountRateMeasurementRequest,
    SaveRawTagsMeasurmentRequest,
    MeasurementResponse,
    MeasurementStatusResponse,
    ErrorResponse,
)
from app.services.job_processor import JobProcessor
from app.services.status_manager import StatusManager, MeasurementStatus
from app.utils.logger import configure_logging

logger = configure_logging(__name__)

router = APIRouter(prefix="/api/v1/measurements", tags=["measurements"])

# These will be set by main.py
_job_processor: Optional[JobProcessor] = None
_status_manager: Optional[StatusManager] = None


def set_processors(
    job_processor: JobProcessor,
    status_manager: StatusManager,
) -> None:
    """Set the job processor and status manager."""
    global _job_processor, _status_manager
    _job_processor = job_processor
    _status_manager = status_manager


def get_job_processor() -> JobProcessor:
    """Dependency injection for job processor."""
    if _job_processor is None:
        raise RuntimeError("Job processor not initialized")
    return _job_processor


def get_status_manager() -> StatusManager:
    """Dependency injection for status manager."""
    if _status_manager is None:
        raise RuntimeError("Status manager not initialized")
    return _status_manager


@router.post("/count-rate", response_model=MeasurementResponse, status_code=201)
async def start_count_rate_measurement(
    request: CountRateMeasurementRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
) -> MeasurementResponse:
    """
    Start a new count-rate measurement request.
    
    Returns a unique measurement ID (status ID) to be used for status queries and stopping.
    The job is enqueued for processing by the backend worker.
    
    Example:
        POST /api/v1/measurements/count-rate
        {
            "measurement_type": "count_rate",
            "duration_seconds": 60,
            "metadata": {"detector_id": "det_001"}
        }
    """
    try:
        # Generate unique status ID
        status_id = str(uuid.uuid4())
        
        logger.info(f"[{status_id}] Received count-rate measurement request: {request.dict()}")
        
        # Create status in Redis
        status_manager.create_status(
            status_id=status_id,
            measurement_type=request.measurement_type.value,
            duration_seconds=request.duration_seconds,
            metadata=request.metadata,
        )
        
        # Enqueue job for backend worker (don't process immediately)
        processor.enqueue_job(
            status_id=status_id,
            measurement_type=request.measurement_type.value,
            duration_seconds=request.duration_seconds,
        )
        
        logger.info(f"[{status_id}] Count-rate measurement enqueued successfully")
        
        return MeasurementResponse(
            measurement_id=status_id,
            measurement_type=request.measurement_type,
            status=MeasurementStatus.QUEUED.value,
            started_at=datetime.utcnow(),
            message=f"Count-rate measurement queued. Use ID '{status_id}' to query status or stop.",
        )
    
    except Exception as e:
        logger.error(f"Failed to enqueue count-rate measurement: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.post("/save-raw-tags", response_model=MeasurementResponse, status_code=201)
async def start_save_raw_tags_measurement(
    request: SaveRawTagsMeasurmentRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
) -> MeasurementResponse:
    """
    Start a new save-raw-tags measurement request.
    
    Returns a unique measurement ID (status ID) to be used for status queries and stopping.
    The job is enqueued for processing by the backend worker.
    
    Example:
        POST /api/v1/measurements/save-raw-tags
        {
            "measurement_type": "save_raw_tags",
            "duration_seconds": 60,
            "metadata": {
                "channel_list": [1, 2, 3],
                "target_file_path": "C:\\Users\\s257050\\Desktop\\"
            }
        }
    """
    try:
        # Generate unique status ID
        status_id = str(uuid.uuid4())
        
        logger.info(f"[{status_id}] Received save-raw-tags measurement request: {request.dict()}")
        
        # Create status in Redis
        status_manager.create_status(
            status_id=status_id,
            measurement_type=request.measurement_type.value,
            duration_seconds=request.duration_seconds,
            metadata=request.metadata.model_dump(),
        )
        
        # Enqueue job for backend worker (don't process immediately)
        processor.enqueue_job(
            status_id=status_id,
            measurement_type=request.measurement_type.value,
            duration_seconds=request.duration_seconds,
            metadata=request.metadata.model_dump(),
        )
        
        return MeasurementResponse(
            measurement_id=status_id,
            measurement_type=request.measurement_type,
            status=MeasurementStatus.QUEUED.value,
            started_at=datetime.utcnow(),
            message=f"Save-raw-tags measurement queued. Use ID '{status_id}' to query status or stop.",
        )
    
    except Exception as e:
        logger.error(f"Failed to enqueue save-raw-tags measurement: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.delete("/{measurement_id}", response_model=MeasurementResponse)
async def stop_measurement(
    measurement_id: str,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
) -> MeasurementResponse:
    """
    Stop an active measurement request.
    
    Args:
        measurement_id: The unique status ID returned when starting the measurement
        
    Returns:
        Measurement response with stopped status
        
    Raises:
        404: If measurement not found
        409: If measurement is not active/queued
    """
    logger.info(f"[{measurement_id}] Received stop request")
    
    try:
        # Get current status
        status_obj = status_manager.get_status(measurement_id)
        
        if not status_obj:
            logger.warning(f"[{measurement_id}] Stop requested for non-existent measurement")
            raise HTTPException(
                status_code=404,
                detail=f"Measurement '{measurement_id}' not found",
            )
        
        current_status = status_obj["status"]
        
        # Stop the job if it's active or queued
        if current_status in [MeasurementStatus.QUEUED.value, MeasurementStatus.ACTIVE.value]:
            processor.stop_job(measurement_id)
        elif current_status in [MeasurementStatus.COMPLETED.value, MeasurementStatus.STOPPED.value]:
            logger.info(f"[{measurement_id}] Job already {current_status}, nothing to stop")
        else:
            logger.warning(f"[{measurement_id}] Cannot stop job in {current_status} state")
        
        # Get updated status
        updated_status = status_manager.get_status(measurement_id)
        
        logger.info(f"[{measurement_id}] Measurement stopped")
        
        return MeasurementResponse(
            measurement_id=measurement_id,
            measurement_type=updated_status["measurement_type"],
            status=updated_status["status"],
            started_at=datetime.fromisoformat(updated_status["started_at"]),
            message=f"Measurement {updated_status['status']}. {updated_status['message']}",
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{measurement_id}] Failed to stop measurement: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/{measurement_id}/status", response_model=MeasurementStatusResponse)
async def get_measurement_status(
    measurement_id: str,
    status_manager: StatusManager = Depends(get_status_manager),
) -> MeasurementStatusResponse:
    """
    Query the status of a measurement.
    
    Args:
        measurement_id: The unique status ID returned when starting the measurement
        
    Returns:
        Current status and duration information
        
    Raises:
        404: If measurement not found
    """
    logger.debug(f"[{measurement_id}] Status query received")
    
    try:
        status_obj = status_manager.get_status(measurement_id)
        
        if not status_obj:
            logger.warning(f"[{measurement_id}] Status query for non-existent measurement")
            raise HTTPException(
                status_code=404,
                detail=f"Measurement '{measurement_id}' not found",
            )
        
        # Get metadata and results
        metadata = status_manager.get_metadata(measurement_id)
        results = status_manager.get_results(measurement_id)
        
        # Calculate duration so far
        started_at = datetime.fromisoformat(status_obj["started_at"])
        duration_so_far = (datetime.utcnow() - started_at).total_seconds()
        
        return MeasurementStatusResponse(
            measurement_id=measurement_id,
            measurement_type=status_obj["measurement_type"],
            status=status_obj["status"],
            started_at=started_at,
            duration_so_far=max(0, duration_so_far),  # Ensure non-negative
            metadata=metadata,
            results=results,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{measurement_id}] Failed to get measurement status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.get("/", response_model=dict)
async def list_measurements(
    status_manager: StatusManager = Depends(get_status_manager),
) -> dict:
    """
    List system health and available endpoints.
    
    Returns:
        Service information and available endpoints
    """
    logger.debug("List/health endpoint query received")
    
    try:
        redis_healthy = status_manager.health_check()
        
        return {
            "service": "MaaS - Measurements as a Service",
            "version": "2.0",
            "architecture": "Distributed (Web Layer + Redis + Backend Workers)",
            "redis_status": "healthy" if redis_healthy else "unhealthy",
            "endpoints": {
                "start_count_rate": "POST /api/v1/measurements/count-rate",
                "start_save_raw_tags": "POST /api/v1/measurements/save-raw-tags",
                "get_status": "GET /api/v1/measurements/{measurement_id}/status",
                "stop_measurement": "DELETE /api/v1/measurements/{measurement_id}",
            },
        }
    except Exception as e:
        logger.error(f"Failed to get system info: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
