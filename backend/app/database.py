"""Database engine, session factory, and schema creation."""
import os
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

# Default DB lives at project root/data/yuno.db (absolute so CWD-independent)
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_DB = f"sqlite+aiosqlite:///{_PROJECT_ROOT}/data/yuno.db"
_raw_url = os.getenv("DATABASE_URL", _DEFAULT_DB)

# Resolve relative sqlite paths to absolute using the project root
if _raw_url.startswith("sqlite") and ":///./" in _raw_url:
    _rel = _raw_url.split("///./", 1)[1]
    _abs = _PROJECT_ROOT / _rel
    DATABASE_URL = f"sqlite+aiosqlite:///{_abs}"
else:
    DATABASE_URL = _raw_url

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create all tables and apply WAL pragma."""
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(_create_all_tables)


def _create_all_tables(connection) -> None:
    from app.models import metadata
    metadata.create_all(connection)
