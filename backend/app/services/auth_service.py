"""
Authentication and User management service.
Handles credential verification, user registration, and token generation.
"""

from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import User, UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserCreate, UserUpdate
from app.security.auth import hash_password, verify_password, create_access_token


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)

    def login(self, request: LoginRequest) -> TokenResponse:
        user = self.user_repo.get_by_username(request.username)
        if not user or not verify_password(request.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = create_access_token(username=user.username, role=user.role)
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            username=user.username,
            full_name=user.full_name,
            role=user.role,
        )

    def get_user_by_username(self, username: str) -> Optional[User]:
        return self.user_repo.get_by_username(username)

    def list_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        return self.user_repo.get_all(skip=skip, limit=limit)

    def create_user(self, payload: UserCreate) -> User:
        if self.user_repo.get_by_username(payload.username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Username '{payload.username}' is already taken",
            )
        if self.user_repo.get_by_email(payload.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email '{payload.email}' is already registered",
            )

        hashed = hash_password(payload.password)
        return self.user_repo.create(
            username=payload.username,
            email=payload.email,
            hashed_password=hashed,
            full_name=payload.full_name,
            role=payload.role,
        )

    def update_user(self, user_id: int, payload: UserUpdate) -> User:
        user = self.user_repo.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        hashed = hash_password(payload.password) if payload.password else None
        return self.user_repo.update(
            user=user,
            email=payload.email,
            full_name=payload.full_name,
            role=payload.role,
            hashed_password=hashed,
        )
