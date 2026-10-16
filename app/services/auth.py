from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.config import settings
from app.errors import Conflict
from app.models import Session, User
from app.schemas import Credentials


async def register(db: AsyncSession, data: Credentials) -> User:
    user = User(email=data.email, password_hash=security.hash_password(data.password))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise Conflict("Este email já está cadastrado.") from None
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    user = await db.scalar(select(User).where(User.email == email.strip().lower()))
    ok = security.verify_password(user.password_hash if user else None, password)
    return user if ok else None


async def create_session(db: AsyncSession, user: User) -> str:
    token = security.new_session_token()
    db.add(Session(
        token_hash=security.hash_token(token),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.session_days),
    ))
    await db.commit()
    return token


async def user_from_token(db: AsyncSession, token: str) -> User | None:
    session = await db.get(Session, security.hash_token(token))
    if session is None:
        return None
    if session.expires_at <= datetime.now(UTC):
        await db.delete(session)
        await db.commit()
        return None
    return session.user


async def delete_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(Session).where(Session.token_hash == security.hash_token(token)))
    await db.commit()
