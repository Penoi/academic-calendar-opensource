import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import models  # noqa: F401
from app.db import Base, get_db, make_engine
from app.main import app
from app.ratelimit import limiter
from app.security import CSRF_HEADER, SESSION_COOKIE, csrf_token_for


@pytest.fixture(autouse=True)
async def db(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def override():
        async with sessions() as s:
            yield s

    app.dependency_overrides[get_db] = override
    limiter.enabled = False
    limiter.reset()
    yield
    app.dependency_overrides.clear()
    await engine.dispose()


def make_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def login_as(email: str = "ana@example.com", password: str = "senha-segura") -> AsyncClient:
    """Cliente já cadastrado e logado, com o header CSRF configurado."""
    client = make_client()
    resp = await client.post("/api/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    client.headers[CSRF_HEADER] = csrf_token_for(client.cookies[SESSION_COOKIE])
    return client


@pytest.fixture
async def ana():
    client = await login_as("ana@example.com")
    yield client
    await client.aclose()


@pytest.fixture
async def bruno():
    client = await login_as("bruno@example.com")
    yield client
    await client.aclose()
