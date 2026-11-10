"""Measurement endpoints: /api/v1/measurements.

Starting a measurement only queues a job in Redis; the worker runs it. The
channels a measurement uses must already be booked by the requesting user.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

import jwt
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.api.audit_route import AuditRoute
from app.api.dependencies import get_file_logger, get_job_processor, get_status_manager
from app.config import REDIS_DB, REDIS_HOST, REDIS_PORT, STOP_ACK_TIMEOUT_SECONDS
from app.models import (
    CoincidencesLiveMeasurementRequest,
    CoincidencesMeasurementRequest,
    CorrelationLiveMeasurementRequest,
    CorrelationMeasurementRequest,
    CountRateLiveMeasurementRequest,
    CountRateMeasurementRequest,
    HistogramLiveMeasurementRequest,
    MeasurementResponse,
    MeasurementStatusResponse,
    SaveRawTagsMeasurmentRequest,
    StartStopLiveMeasurementRequest,
)
from app.services.auth_service import decode_access_token
from app.services.file_logger import FileLogger
from app.services.job_processor import JobProcessor
from app.services.status_manager import MeasurementStatus, StatusManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/measurements", tags=["measurements"], route_class=AuditRoute)


def service_info() -> dict:
    """Service name and the main endpoints (served at / and /api/v1/measurements/)."""
    return {
        "service": "MaaS - Measurements as a Service",
        "version": "2.0",
        "architecture": "Distributed (Web Layer + Redis + Backend Workers)",
        "measurement_endpoints": {
            "start_count_rate": "POST /api/v1/measurements/count-rate",
            "start_count_rate_live": "POST /api/v1/measurements/count-rate-live",
            "start_correlation": "POST /api/v1/measurements/correlation",
            "start_correlation_live": "POST /api/v1/measurements/correlation-live",
            "start_coincidences": "POST /api/v1/measurements/coincidences",
            "start_coincidences_live": "POST /api/v1/measurements/coincidences-live",
            "start_startstop_live": "POST /api/v1/measurements/startstop-live",
            "start_histogram_live": "POST /api/v1/measurements/histogram-live",
            "start_save_raw_tags": "POST /api/v1/measurements/save-raw-tags",
            "get_status": "GET /api/v1/measurements/{measurement_id}/status",
            "stop_measurement": "DELETE /api/v1/measurements/{measurement_id}",
            "stream": "WS /api/v1/measurements/stream/{measurement_id}",
        },
        "channel_endpoints": {
            "list_channels": "GET /api/v1/channels/",
            "list_available": "GET /api/v1/channels/available",
            "channel_parameters": "GET /api/v1/channels/parameters",
            "book_channels": "POST /api/v1/channels/book",
            "release_channels": "POST /api/v1/channels/release/{user_name}",
        },
        "parameter_endpoints": {
            "start_set_parameters": "POST /api/v1/set-parameters",
        },
        "docs": "GET /docs",
        "health": "GET /health",
    }


def enqueue_measurement(
    request,
    channels: list[int],
    processor: JobProcessor,
    status_manager: StatusManager,
    file_logger: Optional[FileLogger],
) -> MeasurementResponse:
    """Check the channel booking, create the status record and queue the job.

    Shared by every measurement endpoint and by set-parameters. ``request`` is
    any measurement request model (it has ``measurement_type``, ``metadata`` and,
    for most types, ``duration_seconds``).

    Raises:
        HTTPException 400: a channel number is invalid
        HTTPException 403: a channel is not booked by metadata.user_name
        HTTPException 500: anything else went wrong
    """
    measurement_type = request.measurement_type.value
    name = measurement_type.replace("_", "-")
    duration_seconds = getattr(request, "duration_seconds", None)
    metadata = request.metadata.model_dump()
    user_name = request.metadata.user_name

    try:
        status_id = str(uuid.uuid4())
        logger.info(f"[{status_id}] Received {name} measurement request: {metadata}")

        try:
            status_manager.validate_channels(channels)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        booked = status_manager.get_booked_channels()
        for channel in channels:
            if booked.get(channel) != user_name:
                raise HTTPException(
                    status_code=403,
                    detail=f"Channel {channel} is not booked by user '{user_name}'",
                )

        status_manager.create_status(
            status_id=status_id,
            measurement_type=measurement_type,
            duration_seconds=duration_seconds,
            metadata=metadata,
        )
        processor.enqueue_job(
            status_id=status_id,
            measurement_type=measurement_type,
            duration_seconds=duration_seconds,
            metadata=metadata,
        )
        logger.info(f"[{status_id}] {name} measurement enqueued")

        if file_logger:
            try:
                file_logger.log_measurement_request(
                    measurement_id=status_id,
                    measurement_type=measurement_type,
                    duration_seconds=duration_seconds,
                    metadata=metadata,
                    timestamp=datetime.utcnow(),
                )
            except Exception as e:
                logger.error(f"[{status_id}] Failed to log measurement request: {e}", exc_info=True)

        return MeasurementResponse(
            measurement_id=status_id,
            measurement_type=request.measurement_type,
            status=MeasurementStatus.QUEUED.value,
            started_at=datetime.utcnow(),
            message=(
                f"{name.capitalize()} measurement queued with channels {channels}. "
                f"Use ID '{status_id}' to query status or stop."
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enqueue {name} measurement: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ========== START ENDPOINTS ==========


@router.post("/count-rate", response_model=MeasurementResponse, status_code=201)
def start_count_rate_measurement(
    request: CountRateMeasurementRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """Count events on `channels` for `duration_seconds` and save the counts to a file."""
    return enqueue_measurement(request, request.metadata.channels, processor, status_manager, file_logger)


@router.post("/count-rate-live", response_model=MeasurementResponse, status_code=201)
def start_count_rate_live_measurement(
    request: CountRateLiveMeasurementRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """Stream counts on `channels` to `measurement:data:<id>` until stopped (or for duration_seconds)."""
    return enqueue_measurement(request, request.metadata.channels, processor, status_manager, file_logger)


@router.post("/save-raw-tags", response_model=MeasurementResponse, status_code=201)
def start_save_raw_tags_measurement(
    request: SaveRawTagsMeasurmentRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """Write every time tag on `channel_list` to a .ttbin file for `duration_seconds`."""
    return enqueue_measurement(request, request.metadata.channel_list, processor, status_manager, file_logger)


@router.post("/correlation", response_model=MeasurementResponse, status_code=201)
def start_correlation_measurement(
    request: CorrelationMeasurementRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """Histogram the time differences between channel1 and channel2 and save it to a file."""
    channels = [request.metadata.channel1, request.metadata.channel2]
    return enqueue_measurement(request, channels, processor, status_manager, file_logger)


@router.post("/correlation-live", response_model=MeasurementResponse, status_code=201)
def start_correlation_live_measurement(
    request: CorrelationLiveMeasurementRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """Stream a correlation histogram of channel1 and channel2 until stopped."""
    return enqueue_measurement(request, request.channels, processor, status_manager, file_logger)


@router.post("/coincidences", response_model=MeasurementResponse, status_code=201)
@router.post("/coincidence", response_model=MeasurementResponse, status_code=201)
def start_coincidences_measurement(
    request: CoincidencesMeasurementRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """Count coincidences of each channel group for `duration_seconds` and save them to a file."""
    return enqueue_measurement(request, request.metadata.unique_channels, processor, status_manager, file_logger)


@router.post("/coincidences-live", response_model=MeasurementResponse, status_code=201)
@router.post("/coincidence-live", response_model=MeasurementResponse, status_code=201)
def start_coincidences_live_measurement(
    request: CoincidencesLiveMeasurementRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """Stream coincidence counts of each channel group until stopped (or for duration_seconds)."""
    return enqueue_measurement(request, request.metadata.unique_channels, processor, status_manager, file_logger)


@router.post("/startstop-live", response_model=MeasurementResponse, status_code=201)
def start_startstop_live_measurement(
    request: StartStopLiveMeasurementRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """Stream a start-stop histogram (start_channel -> click_channel) until stopped."""
    return enqueue_measurement(request, request.channels, processor, status_manager, file_logger)


@router.post("/histogram-live", response_model=MeasurementResponse, status_code=201)
def start_histogram_live_measurement(
    request: HistogramLiveMeasurementRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """Stream a time histogram (start_channel -> click_channel, n_bins bins) until stopped."""
    return enqueue_measurement(request, request.channels, processor, status_manager, file_logger)


# ========== STATUS, STOP AND STREAM ==========


@router.get("/", response_model=dict)
def list_measurements(
    status_manager: StatusManager = Depends(get_status_manager),
) -> dict:
    """Service information, Redis health and the available endpoints."""
    try:
        redis_healthy = status_manager.health_check()
    except Exception as e:
        logger.error(f"Failed to get system info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return {**service_info(), "redis_status": "healthy" if redis_healthy else "unhealthy"}


@router.get("/{measurement_id}/status", response_model=MeasurementStatusResponse)
def get_measurement_status(
    measurement_id: str,
    status_manager: StatusManager = Depends(get_status_manager),
) -> MeasurementStatusResponse:
    """Current status, metadata and (once finished) results of a measurement.

    Raises:
        404: measurement not found (or its status has expired after 1 hour)
    """
    try:
        status_obj = status_manager.get_status(measurement_id)
        if not status_obj:
            raise HTTPException(status_code=404, detail=f"Measurement '{measurement_id}' not found")

        started_at = datetime.fromisoformat(status_obj["started_at"])
        return MeasurementStatusResponse(
            measurement_id=measurement_id,
            measurement_type=status_obj["measurement_type"],
            status=status_obj["status"],
            started_at=started_at,
            duration_so_far=max(0, (datetime.utcnow() - started_at).total_seconds()),
            metadata=status_manager.get_metadata(measurement_id),
            results=status_manager.get_results(measurement_id),
            message=status_obj.get("message"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{measurement_id}] Failed to get measurement status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{measurement_id}", response_model=MeasurementResponse)
def stop_measurement(
    measurement_id: str,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
) -> MeasurementResponse:
    """Stop a queued or active measurement and delete any data file it has written.

    Its channels stay booked; release them with POST /api/v1/channels/release.
    A measurement that has already finished is returned unchanged.

    Raises:
        404: measurement not found
    """
    logger.info(f"[{measurement_id}] Received stop request")
    try:
        status_obj = status_manager.get_status(measurement_id)
        if not status_obj:
            raise HTTPException(status_code=404, detail=f"Measurement '{measurement_id}' not found")

        current_status = status_obj["status"]
        acknowledged = None
        if current_status in (MeasurementStatus.QUEUED.value, MeasurementStatus.ACTIVE.value):
            processor.stop_job(measurement_id)
            acknowledged = bool(
                processor.wait_for_stop_ack(measurement_id, STOP_ACK_TIMEOUT_SECONDS)
            )
            if acknowledged:
                logger.info(f"[{measurement_id}] Worker confirmed the measurement has ended")
            else:
                logger.warning(
                    f"[{measurement_id}] Worker did not confirm the stop within "
                    f"{STOP_ACK_TIMEOUT_SECONDS}s; it will still stop when the worker "
                    "next checks its stop flag"
                )
        else:
            logger.info(f"[{measurement_id}] Job already {current_status}, nothing to stop")

        updated = status_manager.get_status(measurement_id)
        message = f"Measurement {updated['status']}. {updated['message']}"
        if acknowledged is True:
            message += " Worker confirmed the measurement has ended."
        elif acknowledged is False:
            message += (
                f" Worker has not confirmed the stop yet (waited {STOP_ACK_TIMEOUT_SECONDS:g}s)."
            )
        return MeasurementResponse(
            measurement_id=measurement_id,
            measurement_type=updated["measurement_type"],
            status=updated["status"],
            started_at=datetime.fromisoformat(updated["started_at"]),
            message=message,
            stop_acknowledged=acknowledged,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{measurement_id}] Failed to stop measurement: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/stream/{measurement_id}")
async def stream_measurement_data(websocket: WebSocket, measurement_id: str):
    """Forward a live measurement's updates from Redis pub/sub to the client.

    Requires the same JWT as the REST API, sent either as an
    ``Authorization: Bearer <token>`` header or as a ``?token=<token>`` query
    parameter (for clients that cannot set WebSocket headers). Connections
    without a valid token are closed with code 1008 (policy violation).
    """
    auth_header = websocket.headers.get("authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else websocket.query_params.get("token")
    if not token:
        logger.warning(f"Rejected unauthenticated WebSocket connection for {measurement_id}")
        await websocket.close(code=1008, reason="Not authenticated")
        return
    try:
        decode_access_token(token)
    except jwt.ExpiredSignatureError:
        await websocket.close(code=1008, reason="Token expired")
        return
    except jwt.InvalidTokenError:
        await websocket.close(code=1008, reason="Invalid token")
        return

    await websocket.accept()

    redis_client = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    pubsub = redis_client.pubsub()
    channel_name = f"measurement:data:{measurement_id}"

    async def forward_messages():
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is not None:
                await websocket.send_text(message["data"])
            await asyncio.sleep(0.01)

    async def wait_for_disconnect():
        # The forwarding loop never reads from the socket, so on its own it
        # would not notice a client disconnect or server shutdown while no
        # data is being published (e.g. after the measurement has stopped).
        # Uvicorn then waits forever for this handler on Ctrl+C.
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return

    try:
        await pubsub.subscribe(channel_name)
        logger.info(f"WebSocket client connected and subscribed to {channel_name}")

        forward_task = asyncio.create_task(forward_messages())
        disconnect_task = asyncio.create_task(wait_for_disconnect())
        done, pending = await asyncio.wait(
            {forward_task, disconnect_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task.result()  # re-raise anything the finished task hit
        logger.info(f"WebSocket client disconnected from {channel_name}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected from {channel_name}")
    except Exception as e:
        logger.error(f"WebSocket error on {channel_name}: {e}", exc_info=True)
    finally:
        await pubsub.unsubscribe(channel_name)
        await redis_client.aclose()
