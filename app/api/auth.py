from fastapi import APIRouter, HTTPException, Request, Depends, status
from pydantic import BaseModel
import time

from app.db.database import get_user_by_username, get_role_by_name, create_user, delete_user, update_user_password, get_user_by_id
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
    role_id: int

class AdminResetPasswordRequest(BaseModel):
    new_password: str

class UpdatePasswordRequest(BaseModel):
    old_password: str
    new_password: str

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
        
    hashed_password = get_password_hash(req.username)
    user_id = create_user(req.username, hashed_password, req.role_id)
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists or invalid role"
        )
        
    return {"message": "User created successfully", "user_id": user_id}

@auth_router.delete("/users/{username}", status_code=status.HTTP_200_OK)
async def delete_existing_user(username: str, request: Request):
    if not hasattr(request.state, "role") or request.state.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    success = delete_user(username)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return {"message": "User deleted successfully"}

@auth_router.put("/users/{username}/password", status_code=status.HTTP_200_OK)
async def admin_reset_password(username: str, req: AdminResetPasswordRequest, request: Request):
    if not hasattr(request.state, "role") or request.state.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    user_row = get_user_by_username(username)
    if not user_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    hashed_password = get_password_hash(req.new_password)
    update_user_password(username, hashed_password)
    return {"message": "Password updated successfully"}

@auth_router.put("/password", status_code=status.HTTP_200_OK)
async def update_own_password(req: UpdatePasswordRequest, request: Request):
    if not hasattr(request.state, "user_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
        
    user_row = get_user_by_id(request.state.user_id)
    if not user_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    is_valid = verify_password(req.old_password, user_row["password_hash"])
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid current password"
        )
        
    hashed_password = get_password_hash(req.new_password)
    update_user_password(user_row["username"], hashed_password)
    return {"message": "Password updated successfully"}
