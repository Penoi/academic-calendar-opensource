from app.ratelimit import limiter
from app.security import SESSION_COOKIE
from tests.conftest import make_client


async def test_health():
    async with make_client() as c:
        assert (await c.get("/health")).json() == {"status": "ok"}


async def test_register_login_logout(ana):
    me = await ana.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "ana@example.com"

    assert (await ana.post("/api/auth/logout")).status_code == 204
    assert (await ana.get("/api/auth/me")).status_code == 401

    resp = await ana.post("/api/auth/login", json={"email": "ANA@example.com", "password": "senha-segura"})
    assert resp.status_code == 200
    assert SESSION_COOKIE in ana.cookies


async def test_wrong_password_and_unknown_email_look_the_same(ana):
    async with make_client() as c:
        a = await c.post("/api/auth/login", json={"email": "ana@example.com", "password": "errada123"})
        b = await c.post("/api/auth/login", json={"email": "ninguem@example.com", "password": "errada123"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


async def test_duplicate_email(ana):
    async with make_client() as c:
        resp = await c.post("/api/auth/register", json={"email": "ana@example.com", "password": "outrasenha"})
    assert resp.status_code == 409


async def test_short_password_rejected():
    async with make_client() as c:
        resp = await c.post("/api/auth/register", json={"email": "x@example.com", "password": "123"})
    assert resp.status_code == 422


async def test_password_is_hashed(ana):
    from sqlalchemy import select
    from app.db import get_db
    from app.main import app
    from app.models import User
    async for db in app.dependency_overrides[get_db]():
        user = await db.scalar(select(User))
        assert user.password_hash.startswith("$argon2id$")
        assert "senha-segura" not in user.password_hash


async def test_protected_routes_require_login():
    async with make_client() as c:
        assert (await c.get("/api/subscriptions")).status_code == 401
        page = await c.get("/")
        assert page.status_code == 303 and page.headers["location"] == "/login"
        htmx = await c.get("/partials/sidebar", headers={"HX-Request": "true"})
        assert htmx.headers["HX-Redirect"] == "/login"


async def test_csrf_required_for_writes(ana):
    del ana.headers["X-CSRF-Token"]
    resp = await ana.post("/api/subjects", json={"code": "math01", "name": "Matemática", "color": "#6366f1"})
    assert resp.status_code == 403
    ana.headers["X-CSRF-Token"] = "token-falso"
    resp = await ana.post("/api/subjects", json={"code": "math01", "name": "Matemática", "color": "#6366f1"})
    assert resp.status_code == 403


async def test_login_rate_limit(ana):
    limiter.enabled = True
    async with make_client() as c:
        codes = [
            (await c.post("/api/auth/login", json={"email": "ana@example.com", "password": "errada123"})).status_code
            for _ in range(6)
        ]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429
