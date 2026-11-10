"""Channel parameter endpoint: /api/v1/set-parameters."""

from typing import Optional

from fastapi import APIRouter, Depends

from app.api.audit_route import AuditRoute
from app.api.dependencies import get_file_logger, get_job_processor, get_status_manager
from app.api.measurements import enqueue_measurement
from app.models import MeasurementResponse, SetParametersRequest
from app.services.file_logger import FileLogger
from app.services.job_processor import JobProcessor
from app.services.status_manager import StatusManager

router = APIRouter(prefix="/api/v1/set-parameters", tags=["parameters"], route_class=AuditRoute)


@router.post("/", response_model=MeasurementResponse, status_code=201)
def start_set_parameters(
    request: SetParametersRequest,
    processor: JobProcessor = Depends(get_job_processor),
    status_manager: StatusManager = Depends(get_status_manager),
    file_logger: Optional[FileLogger] = Depends(get_file_logger),
) -> MeasurementResponse:
    """Queue a job that sets the input delay and/or trigger voltage of booked channels.

    Poll GET /api/v1/measurements/{id}/status with the returned ID to see when
    the values have been applied.
    """
    return enqueue_measurement(request, request.metadata.channels, processor, status_manager, file_logger)
