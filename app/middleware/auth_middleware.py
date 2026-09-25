import jwt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.services.auth_service import decode_access_token

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # We only protect /api/v1/ and /auth/users
        # Other paths like /docs, /redoc, /health, /auth/login should be allowed
        if path.startswith("/api/v1/") or path == "/auth/users":
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
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
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Token expired"}
                )
            except jwt.InvalidTokenError:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid token"}
                )
                
        # Proceed with request
        response = await call_next(request)
        return response
