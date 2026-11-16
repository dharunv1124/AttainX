"""
API dependencies for database sessions and authentication.
"""

from typing import Generator, Optional, List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import User, UserRole
from app.repositories.user_repository import UserRepository
from app.security.auth import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_db() -> Generator[Session, None, None]:
    """Provide transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Require a valid bearer token for protected API routes."""
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = UserRepository(db).get_by_username(payload.sub)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(
    token: Optional[str] = Depends(optional_oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Allow the current OBE workflow to operate without authentication."""
    if not token:
        return None

    payload = decode_access_token(token)
    if payload is None:
        return None
    return UserRepository(db).get_by_username(payload.sub)


def require_roles(allowed_roles: List[UserRole]):
    """
    Role-checking dependency factory.
    Detailed permission matrix remains UNRESOLVED per Phase 2 decisions.
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden for role '{current_user.role.value}'",
            )
        return current_user
    return role_checker
