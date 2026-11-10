"""Route class that writes an audit-log entry for every state-changing request."""

from typing import Callable

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.services.audit_logger import audit_target, log_audit_event

AUDITED_METHODS = {"POST", "PUT", "DELETE"}


class AuditRoute(APIRoute):
    """APIRoute that logs POST/PUT/DELETE requests (caller, target, outcome) to logs/audit.log."""

    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def audited_route_handler(request: Request) -> Response:
            status_code = 500
            message = "Internal Server Error"
            try:
                response = await original_route_handler(request)
                status_code = response.status_code
                message = "Success"
                return response
            except HTTPException as exc:
                status_code = exc.status_code
                message = exc.detail
                raise
            except RequestValidationError as exc:
                # FastAPI turns this into a 422 response; record the same status
                status_code = 422
                message = str(exc.errors())
                raise
            except Exception as exc:
                message = str(exc)
                raise
            finally:
                if request.method in AUDITED_METHODS:
                    log_audit_event(
                        user_id=getattr(request.state, "user_id", None),
                        role=getattr(request.state, "role", None),
                        action=request.url.path.strip("/").split("/")[-1],
                        target_hardware_id=audit_target(request.method, request.url.path),
                        http_method=request.method,
                        http_path=request.url.path,
                        status=status_code,
                        message=message,
                    )

        return audited_route_handler
