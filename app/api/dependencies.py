"""Services shared by the API endpoints.

main.py creates them at startup and registers them with :func:`set_services`;
endpoints receive them through ``Depends(get_...)``, which tests override.
"""

from typing import Optional

from app.services.file_logger import FileLogger
from app.services.job_processor import JobProcessor
from app.services.status_manager import StatusManager

_job_processor: Optional[JobProcessor] = None
_status_manager: Optional[StatusManager] = None
_file_logger: Optional[FileLogger] = None


def set_services(
    job_processor: JobProcessor,
    status_manager: StatusManager,
    file_logger: Optional[FileLogger] = None,
) -> None:
    """Register the services the endpoints use."""
    global _job_processor, _status_manager, _file_logger
    _job_processor = job_processor
    _status_manager = status_manager
    _file_logger = file_logger


def get_job_processor() -> JobProcessor:
    if _job_processor is None:
        raise RuntimeError("Job processor not initialized")
    return _job_processor


def get_status_manager() -> StatusManager:
    if _status_manager is None:
        raise RuntimeError("Status manager not initialized")
    return _status_manager


def get_file_logger() -> Optional[FileLogger]:
    return _file_logger
