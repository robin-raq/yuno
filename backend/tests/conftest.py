"""Shared test fixtures."""
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Use in-memory SQLite for all tests
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("GOOSE_MODEL", "claude-sonnet-4-5")


def pytest_collection_modifyitems(config, items):
    """Skip @pytest.mark.live tests unless -m live is explicitly passed."""
    if config.getoption("-m", default="") == "live":
        return
    skip_live = pytest.mark.skip(reason="Live tests require running Goose + ANTHROPIC_API_KEY. Run: pytest -m live")
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip_live)


@pytest_asyncio.fixture
async def db():
    from app.database import engine, AsyncSessionLocal
    from app.models import metadata
    # Finding #14: drop + recreate all tables for each test so no state leaks between tests.
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db):
    from app.main import app
    from app.database import get_db

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
