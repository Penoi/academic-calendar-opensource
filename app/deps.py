from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errors import NotAuthenticated
from app.models import User
from app.security import SESSION_COOKIE
from app.services import auth as auth_service


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user = await auth_service.user_from_token(db, token) if token else None
    if user is None:
        raise NotAuthenticated()
    return user


async def get_optional_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    return await auth_service.user_from_token(db, token) if token else None
