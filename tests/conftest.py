from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client(tmp_path):  # type: ignore[no-untyped-def]
    settings = Settings(
        environment="test",
        debug=True,
        database_url=f"sqlite:///{tmp_path / 'redlake-test.db'}",
        storage_backend="filesystem",
        storage_root=tmp_path / "objects",
        auto_create_schema=True,
        max_upload_bytes=1024,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client
