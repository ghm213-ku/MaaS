import jwt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.services.auth_service import decode_access_token
from app.services.audit_logger import log_audit_event

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # We only protect /api/v1/ and /auth/users, /auth/password
        # Other paths like /docs, /redoc, /health, /auth/login should be allowed
        if path.startswith("/api/v1/") or path.startswith("/auth/users") or path == "/auth/password":
            def _log_audit_401(msg: str):
                is_audit_method = request.method in ["POST", "PUT", "DELETE"]
                if is_audit_method:
                    action = path.strip("/").split("/")[-1]
                    target_hardware_id = "system"
                    if "measurements/" in path:
                        parts = path.split("/")
                        if parts[-1] not in ["count-rate", "correlation", "coincidences", "save-raw-tags"]:
                            target_hardware_id = parts[-1]
                    log_audit_event(None, None, action, target_hardware_id, request.method, path, 401, msg)

            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                _log_audit_401("Not authenticated")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Not authenticated"}
                )
            
            token = auth_header.split(" ")[1]
            try:
                payload = decode_access_token(token)
                request.state.user_id = payload.get("sub")
                request.state.role = payload.get("role")
                
                # Role Verification (AuthZ)
                # As per recent user instruction: "for now let's make all the users have permissions of all the APIs available"
                # We skip the role checking for GET/POST methods for /api/v1/*
                # The /auth/users endpoint role check is handled inside its route.
                
            except jwt.ExpiredSignatureError:
                _log_audit_401("Token expired")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Token expired"}
                )
            except jwt.InvalidTokenError:
                _log_audit_401("Invalid token")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid token"}
                )
                
        # Proceed with request
        response = await call_next(request)
        return response
