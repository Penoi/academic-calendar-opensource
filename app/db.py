from collections.abc import AsyncIterator
from uuid import uuid4

from sqlalchemy import URL, event, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings

SSL_MODES = {"require", "verify-ca", "verify-full"}


def _is_pooler(url: URL) -> bool:
    """Neon (host com -pooler) e Supabase (pooler.supabase.com / porta 6543) usam PgBouncer/Supavisor."""
    host = url.host or ""
    return "-pooler." in host or "pooler.supabase.com" in host or url.port == 6543


def normalize_url(raw: str) -> tuple[URL, dict]:
    """Converte a URL do Neon/Supabase para asyncpg e devolve (url, connect_args).

    O asyncpg não entende sslmode/channel_binding na query: o SSL vai em connect_args.
    """
    for prefix in ("postgres://", "postgresql://"):
        if raw.startswith(prefix):
            raw = "postgresql+asyncpg://" + raw.removeprefix(prefix)
    url = make_url(raw)
    connect_args: dict = {}
    if url.drivername != "postgresql+asyncpg":
        return url, connect_args

    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    if sslmode in SSL_MODES:
        connect_args["ssl"] = sslmode  # o asyncpg aceita o mesmo modo do libpq ("require" etc.)
    if _is_pooler(url):
        # pooler em modo transação não guarda prepared statements entre requisições
        query["prepared_statement_cache_size"] = "0"
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_name_func"] = lambda: f"__asyncpg_{uuid4()}__"
    return url.set(query=query), connect_args


def make_engine(raw_url: str) -> AsyncEngine:
    url, connect_args = normalize_url(raw_url)
    if url.get_backend_name() == "postgresql":
        # serverless: cada invocação abre e fecha a conexão, sem pool local que fique órfão
        return create_async_engine(url, connect_args=connect_args, poolclass=NullPool)

    engine = create_async_engine(url)
    if engine.dialect.name == "sqlite":
        # SQLite só respeita ON DELETE CASCADE com esta pragma ligada
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_fks(dbapi_conn, _record) -> None:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


engine = make_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
