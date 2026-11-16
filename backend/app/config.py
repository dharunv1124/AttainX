"""
Application configuration loaded from environment variables.
"""

import os
from pathlib import Path


def _load_local_env_file() -> None:
    """Load a repository-level .env file when present so local development works without shell exports."""
    candidates = [
        Path.cwd() / ".env",
        Path.cwd() / ".env.local",
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parents[2] / ".env.local",
    ]

    for candidate in candidates:
        if not candidate.is_file():
            continue

        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"\'')

            os.environ.setdefault(key, value)


_load_local_env_file()


class Settings:
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]

    def __init__(self) -> None:
        if self.ENVIRONMENT == "development" and not self.DATABASE_URL:
            self.DATABASE_URL = "sqlite:///./backend/obe_db.sqlite"

        if self.ENVIRONMENT == "development" and not self.JWT_SECRET_KEY:
            self.JWT_SECRET_KEY = "dev_local_secret_key_change_me"

        if self.ENVIRONMENT == "development" and not self.CORS_ORIGINS:
            self.CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

        if not self.DATABASE_URL:
            raise RuntimeError("DATABASE_URL must be set in the environment.")
        if self.ENVIRONMENT == "production" and not self.DATABASE_URL.lower().startswith("postgresql"):
            raise RuntimeError("Production DATABASE_URL must use PostgreSQL.")
        if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY.lower().startswith(("dev_", "change_me", "replace_")):
            if self.ENVIRONMENT != "development":
                raise RuntimeError("JWT_SECRET_KEY must be set to a non-placeholder secret in the environment.")
        if self.ENVIRONMENT == "production" and not self.CORS_ORIGINS:
            raise RuntimeError("CORS_ORIGINS must include the deployed frontend origin in production.")


settings = Settings()
