"""Migration metadata and environment-only connection configuration."""

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.database import Base
from app import models  # noqa: F401 -- register all tables

target_metadata = Base.metadata

if context.is_offline_mode():
    # SQL generation needs no credentials or running database.
    context.configure(
        dialect_name="postgresql", target_metadata=target_metadata,
        literal_binds=True, dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(
        get_settings().database_url.get_secret_value(),
        poolclass=pool.NullPool, hide_parameters=True,
    )
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
