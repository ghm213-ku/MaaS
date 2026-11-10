"""Channel endpoints: /api/v1/channels (list, book, release, current parameters).

A user books channels before measuring on them. Channels stay booked until the
user (or an admin) releases them; releasing also queues a job that resets the
channels' trigger level and input delay to their defaults.
"""

import logging
import uuid
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from app.api.audit_route import AuditRoute
from app.api.dependencies import get_file_logger, get_job_processor, get_status_manager
from app.db.database import get_user_by_id
from app.models import (
    ChannelBookRequest,
    ChannelBookResponse,
    ChannelListResponse,
    ChannelParametersResponse,
    ChannelReleaseRequest,
    ChannelReleaseResponse,
    ChannelStatsResponse,
    MeasurementType,
)
from app.services.channel_parameters import get_channel_parameters
from app.services.file_logger import FileLogger
from app.services.job_processor import JobProcessor
from app.services.status_manager import StatusManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/channels", tags=["channels"], route_class=AuditRoute)

# Parameters applied to channels when they are released
DEFAULT_CHANNEL_PARAMETERS = {"input_delay": 0, "trigger_voltage": 0.5}


# ========== AUTHORIZATION ==========


def _get_caller_username(http_request: Request) -> Optional[str]:
    """Return the username of the authenticated caller, or None if unknown."""
    caller_id = getattr(http_request.state, "user_id", None)
    if caller_id is None:
        return None
    caller = get_user_by_id(caller_id)
    return caller["username"] if caller is not None else None


def _authorize_channel_booking(http_request: Request, user_name: str) -> None:
    """Allow a booking only under the caller's own username (no admin bypass)."""
    if _get_caller_username(http_request) != user_name:
        logger.warning(
            f"[{user_name}] Channel booking denied for "
            f"user_id={getattr(http_request.state, 'user_id', None)} "
            f"(role={getattr(http_request.state, 'role', None)})"
        )
        raise HTTPException(status_code=403, detail="You can only book channels under your own username")


def _authorize_channel_release(http_request: Request, user_name: str) -> None:
    """Allow a release only for the caller's own channels, unless they are an admin."""
    role = getattr(http_request.state, "role", None)
    if role == "admin":
        return
    if _get_caller_username(http_request) != user_name:
        logger.warning(
            f"[{user_name}] Channel release denied for "
            f"user_id={getattr(http_request.state, 'user_id', None)} (role={role})"
        )
        raise HTTPException(status_code=403, detail="You can only release your own channels")


# ========== ENDPOINTS ==========


@router.get("/", response_model=ChannelListResponse)
@router.get("", response_model=ChannelListResponse, include_in_schema=False)
def list_all_channels(
    status_manager: StatusManager = Depends(get_status_manager),
) -> ChannelListResponse:
    """All channels with their status (available or booked) and who booked them."""
    try:
        stats = status_manager.get_channel_stats()
        return ChannelListResponse(
            channels=status_manager.get_all_channels(),
            total_channels=stats["total_channels"],
            available_channels=stats["available_channels"],
            booked_channels=stats["booked_channels"],
        )
    except Exception as e:
        logger.error(f"Failed to list channels: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/parameters", response_model=ChannelParametersResponse)
def list_channel_parameters(
    status_manager: StatusManager = Depends(get_status_manager),
) -> ChannelParametersResponse:
    """Current trigger level (V) and input delay (ps) of each channel.

    Values are read back from the Time Tagger by the worker at startup and after
    every set-parameters job (including the reset queued when channels are
    released), so they reflect the hardware rather than what a client last sent.
    Channels the worker has not reported yet are omitted.
    """
    try:
        return ChannelParametersResponse(channels=get_channel_parameters(status_manager.redis_client))
    except Exception as e:
        logger.error(f"Failed to read channel parameters: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/available", response_model=ChannelStatsResponse)
def list_available_channels(
    status_manager: StatusManager = Depends(get_status_manager),
) -> ChannelStatsResponse:
    """Channel usage statistics, the available channel numbers, and each user's booked channels."""
    try:
        available = status_manager.get_available_channels()
        booked = status_manager.get_booked_channels()
        stats = status_manager.get_channel_stats()

        user_names: dict[str, list[int]] = {}
        for channel, user_name in booked.items():
            user_names.setdefault(user_name, []).append(channel)

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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/book", response_model=ChannelBookResponse, status_code=201)
def book_channels(
    request: ChannelBookRequest,
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
    http_request: Request = None,
) -> ChannelBookResponse:
    """Book channels under the caller's own username.

    Raises:
        400: a channel number is invalid
        403: user_name is not the caller's username (applies to admins too)
        409: a channel is already booked
    """
    logger.info(f"[{request.user_name}] Channel booking request for channels: {request.channel_numbers}")

    if http_request is not None:
        _authorize_channel_booking(http_request, request.user_name)

    try:
        status_manager.validate_channels(request.channel_numbers)
        result = status_manager.book_channels(request.channel_numbers, request.user_name)
    except ValueError as e:
        logger.warning(f"[{request.user_name}] Channel booking failed: {e}")
        raise HTTPException(status_code=400 if "Invalid channel" in str(e) else 409, detail=str(e))
    except Exception as e:
        logger.error(f"[{request.user_name}] Channel booking failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    if file_logger:
        try:
            file_logger.log_channel_book_request(
                user_name=result["user_name"],
                channel_numbers=result["booked_channels"],
                timestamp=result["booking_time"],
            )
        except Exception as e:
            logger.error(f"[{request.user_name}] Failed to log channel booking: {e}", exc_info=True)

    return ChannelBookResponse(
        user_name=result["user_name"],
        booked_channels=result["booked_channels"],
        booking_time=result["booking_time"],
        total_booked=result.get("total_booked", len(result["booked_channels"])),
    )


@router.post("/release/{user_name}", response_model=ChannelReleaseResponse)
def release_channels(
    user_name: str,
    request: Annotated[ChannelReleaseRequest, Body()],
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
    processor: JobProcessor = Depends(get_job_processor),
    http_request: Request = None,
) -> ChannelReleaseResponse:
    """Release the listed channels booked by `user_name`.

    The body {"channel_numbers": [...]} names which of the user's channels to
    release. Channels stay booked after a measurement completes, stops, or
    fails; this endpoint is the only way to free them. Releasing also queues a
    set-parameters job that resets the channels to input_delay=0 and
    trigger_voltage=0.5 (its ID is returned as parameter_reset_id).

    Raises:
        403: the caller is not an admin and user_name is not their username
        409: a requested channel is not booked by the user (nothing is released)
    """
    logger.info(f"[{user_name}] Channel release request: {request.channel_numbers}")

    if http_request is not None:
        _authorize_channel_release(http_request, user_name)

    try:
        result = status_manager.release_channels(user_name, request.channel_numbers)
        released = result["released_channels"]

        reset_status_id = None
        if released:
            reset_status_id = str(uuid.uuid4())
            reset_metadata = {"channels": released, "user_name": user_name, **DEFAULT_CHANNEL_PARAMETERS}
            status_manager.create_status(reset_status_id, MeasurementType.SET_PARAMETERS.value, 0, reset_metadata)
            processor.enqueue_job(
                status_id=reset_status_id,
                measurement_type=MeasurementType.SET_PARAMETERS.value,
                duration_seconds=0,
                metadata=reset_metadata,
            )
            logger.info(f"[{user_name}] Queued parameter reset {reset_status_id} for channels {released}")
    except ValueError as e:
        logger.warning(f"[{user_name}] Channel release failed: {e}")
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"[{user_name}] Channel release failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    if file_logger:
        try:
            file_logger.log_channel_release_request(
                user_name=result["user_name"],
                released_channels=released,
                timestamp=datetime.utcnow(),
            )
        except Exception as e:
            logger.error(f"[{user_name}] Failed to log channel release: {e}", exc_info=True)

    return ChannelReleaseResponse(
        user_name=result["user_name"],
        released_channels=released,
        total_released=result["total_released"],
        parameter_reset_id=reset_status_id,
    )
