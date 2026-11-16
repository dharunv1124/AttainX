"""
Authentication and User management API routes.
"""

from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.db.models import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserCreate, UserUpdate, UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user with username and password, returning JWT bearer token."""
    return AuthService(db).login(request)


@router.get("/me", response_model=UserRead)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Get current authenticated user's profile."""
    return current_user


@router.get("/users", response_model=List[UserRead])
def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List system users."""
    return AuthService(db).list_users(skip=skip, limit=limit)


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new user account with role assignment."""
    return AuthService(db).create_user(payload)


@router.put("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update user account."""
    return AuthService(db).update_user(user_id=user_id, payload=payload)
