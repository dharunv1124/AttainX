from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.db.base import Base
import app.db.models  # load all models into Base.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# Override sqlalchemy.url with runtime settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    if configuration is None:
        configuration = {}
    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        current_revision = context.get_context().get_current_revision()
        batch_migration = (
            connection.dialect.name == "sqlite"
            and current_revision == "015_course_obe_section_scope"
            and bool(os.environ.get("OBE_DB_BACKUP_PATH"))
        )
        if batch_migration:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")

        try:
            with context.begin_transaction():
                context.run_migrations()
        finally:
            if batch_migration:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
                if violations:
                    raise RuntimeError(f"SQLite foreign-key violations after migration: {violations[:10]}")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
