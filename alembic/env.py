import asyncio

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401 -- registers all tables
from alembic import context
from app.core.config import settings
from app.db.session import Base

target_metadata = Base.metadata


def configure(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        version_table_schema=context.config.attributes.get("version_table_schema"),
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    engine = create_async_engine(settings.database_url, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(configure)
    await engine.dispose()


if context.config.attributes.get("connection") is not None:
    configure(context.config.attributes["connection"])
elif context.is_offline_mode():
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
