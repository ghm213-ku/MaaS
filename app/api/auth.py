from fastapi import APIRouter, HTTPException, Request, Depends, status
from pydantic import BaseModel
import time

from app.db.database import get_user_by_username, get_role_by_name, create_user
from app.services.auth_service import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_SECONDS

auth_router = APIRouter(prefix="/auth", tags=["Auth"])

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str
    expires_in: int

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role_id: int

@auth_router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    user_row = get_user_by_username(req.username)
    
    # We want consistent timing whether the user exists or not
    # So if the user doesn't exist, we still verify a dummy password
    if not user_row:
        # Dummy hash for constant time
        dummy_hash = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjIQqiRQYq" 
        verify_password(req.password, dummy_hash)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
        
    if not user_row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
        
    is_valid = verify_password(req.password, user_row["password_hash"])
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
        
    token = create_access_token(user_id=user_row["id"], role=user_row["role_name"])
    
    return LoginResponse(
        token=token,
        expires_in=ACCESS_TOKEN_EXPIRE_SECONDS
    )

@auth_router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_new_user(req: CreateUserRequest, request: Request):
    # This endpoint is protected by the auth middleware and requires 'admin' role
    # The middleware will set request.state.role and request.state.user_id
    
    # Just an extra safety check although middleware handles it
    if not hasattr(request.state, "role") or request.state.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
        
    hashed_password = get_password_hash(req.password)
    user_id = create_user(req.username, hashed_password, req.role_id)
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists or invalid role"
        )
        
    return {"message": "User created successfully", "user_id": user_id}
