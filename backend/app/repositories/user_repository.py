"""
User repository for persistence operations on users.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from app.db.models import User, UserRole
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, db: Session):
        super().__init__(User, db)

    def get_by_username(self, username: str) -> Optional[User]:
        return self.db.query(User).filter(User.username == username).first()

    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email).first()

    def get_by_role(self, role: UserRole) -> List[User]:
        return self.db.query(User).filter(User.role == role).all()

    def create(self, username: str, email: str, hashed_password: str, full_name: str, role: UserRole) -> User:
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update(
        self,
        user: User,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        role: Optional[UserRole] = None,
        hashed_password: Optional[str] = None,
    ) -> User:
        if email is not None:
            user.email = email
        if full_name is not None:
            user.full_name = full_name
        if role is not None:
            user.role = role
        if hashed_password is not None:
            user.hashed_password = hashed_password
        self.db.commit()
        self.db.refresh(user)
        return user
