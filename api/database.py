"""
Async database setup for PostgreSQL / SQLite via SQLAlchemy.

Uses centralised settings for configuration and supports connection pooling
for PostgreSQL. Falls back to NullPool for SQLite.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from .models import Base
from .settings import settings

# Build engine kwargs based on backend
_engine_kwargs: dict = {"echo": settings.debug}

if settings.is_sqlite:
    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs["poolclass"] = QueuePool
    _engine_kwargs["pool_size"] = settings.db_pool_size
    _engine_kwargs["max_overflow"] = settings.db_max_overflow
    _engine_kwargs["pool_recycle"] = settings.db_pool_recycle
    _engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(settings.async_database_url, **_engine_kwargs)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create all tables (for development — use Alembic migrations in production)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """FastAPI dependency for database sessions.

    Uses an async context manager to ensure the session is properly closed.
    """
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
