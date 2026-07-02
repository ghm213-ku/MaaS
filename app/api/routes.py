"""API routes for measurement requests - Distributed Architecture.

This module provides two main routers:
- measurement_router: For /api/v1/measurements (count-rate, save-raw-tags, status, stop)
- channels_router: For /api/v1/channels (list, book, release channel management)
"""

from fastapi import APIRouter, HTTPException, Depends, Body
from typing import Optional
from datetime import datetime
import uuid

from app.models import (
    CountRateMeasurementRequest,
    CorrelationMeasurementRequest,
    CoincidencesMeasurementRequest,
    SaveRawTagsMeasurmentRequest,
    MeasurementResponse,
    MeasurementStatusResponse,
    ErrorResponse,
    ChannelBookRequest,
    ChannelBookResponse,
    ChannelReleaseResponse,
    ChannelListResponse,
    ChannelStatsResponse,
    ChannelInfo,
    MeasurementType,
    SetParametersRequest,
)
from app.services.job_processor import JobProcessor
from app.services.status_manager import StatusManager, MeasurementStatus
from app.services.file_logger import FileLogger
from app.utils.logger import configure_logging

logger = configure_logging(__name__)

# Separate routers for measurements and channels
measurement_router = APIRouter(prefix="/api/v1/measurements", tags=["measurements"])
channels_router = APIRouter(prefix="/api/v1/channels", tags=["channels"])
parameters_router = APIRouter(prefix="/api/v1/set-parameters", tags=["parameters"])

# These will be set by main.py
_job_processor: Optional[JobProcessor] = None
_status_manager: Optional[StatusManager] = None
_file_logger: Optional[FileLogger] = None


def set_processors(
    job_processor: JobProcessor,
    status_manager: StatusManager,
    file_logger: Optional[FileLogger] = None,
) -> None:
    """Set the job processor, status manager, and file logger."""
    global _job_processor, _status_manager, _file_logger
    _job_processor = job_processor
    _status_manager = status_manager
    _file_logger = file_logger


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


def get_file_logger() -> Optional[FileLogger]:
    """Dependency injection for file logger."""
    return _file_logger


# ========== MEASUREMENT ENDPOINTS ==========

def _handle_measurement_request(
    request_name: str,
    measurement_type: MeasurementType,
    duration_seconds: Optional[int],
    metadata_dump: dict,
    channels: list[int],
    processor: JobProcessor,
    status_manager: StatusManager,
    file_logger: Optional[FileLogger],
    user_name: str,
) -> MeasurementResponse:
    try:
        # Generate unique status ID
        status_id = str(uuid.uuid4())

        logger.info(f"[{status_id}] Received {request_name} measurement request: {metadata_dump}")

        # Validate that channels are already booked by the user
        status_manager.validate_channels(channels)
        booked_channels_map = status_manager.get_booked_channels()
        for channel in channels:
            if booked_channels_map.get(channel) != user_name:
                raise HTTPException(
                    status_code=403,
                    detail=f"Channel {channel} is not booked by user '{user_name}'"
                )

        logger.info(f"[{status_id}] Verified channels {channels} are booked by {user_name}")

        # Prepare metadata
        metadata_dict = metadata_dump.copy()

        # Create status in Redis
        status_manager.create_status(
            status_id=status_id,
            measurement_type=measurement_type.value,
            duration_seconds=duration_seconds,
            metadata=metadata_dict,
        )

        # Enqueue job for backend worker (don't process immediately)
        processor.enqueue_job(
            status_id=status_id,
            measurement_type=measurement_type.value,
            duration_seconds=duration_seconds,
            metadata=metadata_dict,
        )

        logger.info(f"[{status_id}] {request_name.capitalize()} measurement enqueued successfully")

        # Log measurement request to file
        if file_logger:
            logger.info(
                f"[{status_id}] File logger available, writing to measurement log"
            )
            try:
                file_logger.log_measurement_request(
                    measurement_id=status_id,
                    measurement_type=measurement_type.value,
                    duration_seconds=duration_seconds,
                    metadata=metadata_dump,
                    timestamp=datetime.utcnow(),
                )
                logger.info(f"[{status_id}] Measurement logged to file successfully")
            except Exception as e:
                logger.error(
                    f"[{status_id}] Failed to log measurement: {e}", exc_info=True
                )
        else:
            logger.warning(f"[{status_id}] File logger is None - skipping file logging")

        return MeasurementResponse(
            measurement_id=status_id,
            measurement_type=measurement_type,
            status=MeasurementStatus.QUEUED.value,
            started_at=datetime.utcnow(),
            message=f"{request_name.capitalize()} measurement queued with channels {channels}. Use ID '{status_id}' to query status or stop.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enqueue {request_name} measurement: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@measurement_router.post(
    "/count-rate", response_model=MeasurementResponse, status_code=201
)
async def start_count_rate_measurement(
    request: CountRateMeasurementRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """
    Start a new count-rate measurement request.

    Returns a unique measurement ID (status ID) to be used for status queries and stopping.
    The job is enqueued for processing by the backend worker.

    Automatically books the specified channels.
    """
    return _handle_measurement_request(
        request_name="count-rate",
        measurement_type=request.measurement_type,
        duration_seconds=request.duration_seconds,
        metadata_dump=request.metadata.model_dump(),
        channels=request.metadata.channels,
        processor=processor,
        status_manager=status_manager,
        file_logger=file_logger,
        user_name=request.metadata.user_name,
    )


@measurement_router.post(
    "/save-raw-tags", response_model=MeasurementResponse, status_code=201
)
async def start_save_raw_tags_measurement(
    request: SaveRawTagsMeasurmentRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """
    Start a new save-raw-tags measurement request.

    Returns a unique measurement ID (status ID) to be used for status queries and stopping.
    The job is enqueued for processing by the backend worker.

    Automatically books the channels specified in the channel_list.
    """
    return _handle_measurement_request(
        request_name="save-raw-tags",
        measurement_type=request.measurement_type,
        duration_seconds=request.duration_seconds,
        metadata_dump=request.metadata.model_dump(),
        channels=request.metadata.channel_list,
        processor=processor,
        status_manager=status_manager,
        file_logger=file_logger,
        user_name=request.user_name,
    )


@measurement_router.post(
    "/correlation", response_model=MeasurementResponse, status_code=201
)
async def start_correlation_measurement(
    request: CorrelationMeasurementRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """
    Start a new correlation measurement request.

    Returns a unique measurement ID (status ID) to be used for status queries and stopping.
    The job is enqueued for processing by the backend worker.

    Automatically books the specified channels (channel1 and channel2).
    """
    return _handle_measurement_request(
        request_name="correlation",
        measurement_type=request.measurement_type,
        duration_seconds=request.duration_seconds,
        metadata_dump=request.metadata.model_dump(),
        channels=[request.metadata.channel1, request.metadata.channel2],
        processor=processor,
        status_manager=status_manager,
        file_logger=file_logger,
        user_name=request.user_name,
    )


@measurement_router.post(
    "/coincidences", response_model=MeasurementResponse, status_code=201
)
async def start_coincidences_measurement(
    request: CoincidencesMeasurementRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """
    Start a new coincidences measurement request.

    Returns a unique measurement ID (status ID) to be used for status queries and stopping.
    The job is enqueued for processing by the backend worker.

    Automatically books the specified channels.
    """
    return _handle_measurement_request(
        request_name="coincidences",
        measurement_type=request.measurement_type,
        duration_seconds=request.duration_seconds,
        metadata_dump=request.metadata.model_dump(),
        channels=request.metadata.channels,
        processor=processor,
        status_manager=status_manager,
        file_logger=file_logger,
        user_name=request.user_name,
    )

# ========== CHANNEL MANAGEMENT ENDPOINTS ==========


@parameters_router.post(
    "/", response_model=MeasurementResponse, status_code=201
)
async def start_set_parameters(
    request: SetParametersRequest = Body(
        ...,
        example={
            "measurement_type": "set_parameters",
            "duration_seconds": 0,
            "metadata": {
                "channels": [1, 2],
                "user_name": "abc-123-def",
                "input_delay": 1000,
                "trigger_voltage": 0.5
            }
        }
    ),
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """
    Start a set parameters request.

    Returns a unique status ID to be used for status queries.
    The job is enqueued for processing by the backend worker.

    """
    return _handle_measurement_request(
        request_name="set-parameters",
        measurement_type=request.measurement_type,
        duration_seconds=request.duration_seconds,
        metadata_dump=request.metadata.model_dump(),
        channels=request.metadata.channels,
        processor=processor,
        status_manager=status_manager,
        file_logger=file_logger,
        user_name=request.user_name,
    )


@channels_router.get("/", response_model=ChannelListResponse)
async def list_all_channels(
    status_manager: StatusManager = Depends(get_status_manager),
) -> ChannelListResponse:
    """
    Get all channels with their status (available or booked).

    Endpoint: GET /api/v1/channels/

    Returns:
        List of all channels with current status and booking information.
    """
    logger.debug("List all channels request received")

    try:
        channels = status_manager.get_all_channels()
        stats = status_manager.get_channel_stats()

        return ChannelListResponse(
            channels=channels,
            total_channels=stats["total_channels"],
            available_channels=stats["available_channels"],
            booked_channels=stats["booked_channels"],
        )
    except Exception as e:
        logger.error(f"Failed to list channels: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@channels_router.get("/available", response_model=ChannelStatsResponse)
async def list_available_channels(
    status_manager: StatusManager = Depends(get_status_manager),
) -> ChannelStatsResponse:
    """
    Get list of available channels and channel statistics.

    Endpoint: GET /api/v1/channels/available

    Returns:
        Statistics and list of currently available channel numbers.
    """
    logger.debug("List available channels request received")

    try:
        available = status_manager.get_available_channels()
        booked = status_manager.get_booked_channels()
        stats = status_manager.get_channel_stats()

        # Build mapping of identifiers to channels
        user_names = {}
        for channel, identifier in booked.items():
            if identifier not in user_names:
                user_names[identifier] = []
            user_names[identifier].append(channel)

        return ChannelStatsResponse(
            total_channels=stats["total_channels"],
            available_channels=stats["available_channels"],
            booked_channels=stats["booked_channels"],
            utilization_percent=stats["utilization_percent"],
            available_channel_numbers=available,
            user_names=user_names,
        )
    except Exception as e:
        logger.error(f"Failed to list available channels: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@channels_router.post(
    "/book",
    response_model=ChannelBookResponse,
    status_code=201,
)
async def book_channels(
    request: ChannelBookRequest,
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> ChannelBookResponse:
    """
    Book (reserve) channels for a measurement or user.

    Endpoint: POST /api/v1/channels/book

    Args:
        request: Contains booked_by identifier and list of channel_numbers to book

    Returns:
        Booking confirmation with booked channels and timestamp

    Raises:
        400: If channel numbers are invalid
        409: If any channels are already booked
    """
    logger.info(
        f"[{request.user_name}] Channel booking request for channels: {request.channel_numbers}"
    )

    try:
        # Validate channels
        status_manager.validate_channels(request.channel_numbers)

        # Book the channels
        booking_result = status_manager.book_channels(
            request.channel_numbers,
            request.user_name,
        )

        logger.info(f"[{request.user_name}] Channels booked successfully")

        # Log channel booking request to file
        if file_logger:
            logger.info(
                f"[{request.user_name}] File logger available, writing to channel log"
            )
            try:
                file_logger.log_channel_book_request(
                    user_name=booking_result["user_name"],
                    channel_numbers=booking_result["booked_channels"],
                    timestamp=booking_result["booking_time"],
                )
                logger.info(
                    f"[{request.user_name}] Channel booking logged to file successfully"
                )
            except Exception as e:
                logger.error(
                    f"[{request.user_name}] Failed to log channel booking: {e}",
                    exc_info=True,
                )
        else:
            logger.warning(
                f"[{request.user_name}] File logger is None - skipping file logging"
            )

        return ChannelBookResponse(
            user_name=booking_result["user_name"],
            booked_channels=booking_result["booked_channels"],
            booking_time=booking_result["booking_time"],
            total_booked=booking_result["total_booked"],
        )

    except ValueError as e:
        logger.warning(f"[{request.user_name}] Channel booking validation failed: {e}")
        raise HTTPException(
            status_code=400 if "Invalid channel" in str(e) else 409,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            f"[{request.user_name}] Channel booking failed: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@channels_router.post(
    "/release/{user_name}",
    response_model=ChannelReleaseResponse,
)
async def release_channels(
    user_name: str,
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> ChannelReleaseResponse:
    """
    Release (free up) all channels booked by a measurement or user.

    Endpoint: POST /api/v1/channels/release/{user_name}

    Args:
        user_name: The identifier (user) whose channels to release

    Returns:
        Release confirmation with released channels count

    Note:
        Channels are automatically released when a measurement completes, stops, or fails.
        This endpoint allows explicit manual release if needed.
    """
    logger.info(f"[{user_name}] Channel release request")

    try:
        release_result = status_manager.release_channels(user_name)

        logger.info(
            f"[{user_name}] Channels released successfully: {release_result['released_channels']}"
        )

        # Log channel release request to file
        if file_logger:
            logger.info(f"[{user_name}] File logger available, writing to channel log")
            try:
                file_logger.log_channel_release_request(
                    user_name=release_result["user_name"],
                    released_channels=release_result["released_channels"],
                    timestamp=datetime.utcnow(),
                )
                logger.info(
                    f"[{user_name}] Channel release logged to file successfully"
                )
            except Exception as e:
                logger.error(
                    f"[{user_name}] Failed to log channel release: {e}", exc_info=True
                )
        else:
            logger.warning(f"[{user_name}] File logger is None - skipping file logging")

        return ChannelReleaseResponse(
            user_name=release_result["user_name"],
            released_channels=release_result["released_channels"],
            total_released=release_result["total_released"],
        )

    except Exception as e:
        logger.error(f"[{user_name}] Channel release failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


async def get_user_name_channels(
    user_name: str,
    status_manager: StatusManager = Depends(get_status_manager),
) -> dict:
    """
    Get all channels currently booked by a specific user.

    Args:
        user_name: The user identifier

    Returns:
        List of booked channels and count
    """
    logger.debug(f"[{user_name}] Get booked channels request")

    try:
        channels = status_manager.get_booked_channels_by(user_name)

        return {
            "user_name": user_name,
            "booked_channels": channels,
            "total_booked": len(channels),
        }
    except Exception as e:
        logger.error(f"[{user_name}] Failed to get booked channels: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@measurement_router.delete("/{measurement_id}", response_model=MeasurementResponse)
async def stop_measurement(
    measurement_id: str,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
) -> MeasurementResponse:
    """
    Stop an active measurement request, delete its data file, and release channels.

    Stops the running measurement, deletes any data file that has already been
    written for it, and releases its booked channels.

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
            logger.warning(
                f"[{measurement_id}] Stop requested for non-existent measurement"
            )
            raise HTTPException(
                status_code=404,
                detail=f"Measurement '{measurement_id}' not found",
            )

        current_status = status_obj["status"]

        # Stop the job if it's active or queued
        if current_status in [
            MeasurementStatus.QUEUED.value,
            MeasurementStatus.ACTIVE.value,
        ]:
            processor.stop_job(measurement_id)
        elif current_status in [
            MeasurementStatus.COMPLETED.value,
            MeasurementStatus.STOPPED.value,
        ]:
            logger.info(
                f"[{measurement_id}] Job already {current_status}, nothing to stop"
            )
        else:
            logger.warning(
                f"[{measurement_id}] Cannot stop job in {current_status} state"
            )

        # Release channels was removed because channels are manually booked by user

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
        logger.error(
            f"[{measurement_id}] Failed to stop measurement: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@measurement_router.get(
    "/{measurement_id}/status", response_model=MeasurementStatusResponse
)
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
            logger.warning(
                f"[{measurement_id}] Status query for non-existent measurement"
            )
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
        logger.error(
            f"[{measurement_id}] Failed to get measurement status: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@measurement_router.get("/", response_model=dict)
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
            "parameter_endpoints": {
                "start_set_parameters": "POST /api/v1/set-parameters",
            },
        }
    except Exception as e:
        logger.error(f"Failed to get system info: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
