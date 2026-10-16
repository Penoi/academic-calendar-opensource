from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.cookies import clear_session_cookie, set_session_cookie
from app.db import get_db
from app.deps import get_current_user
from app.errors import AppError
from app.models import User
from app.ratelimit import LOGIN_LIMIT, limiter
from app.schemas import Credentials, UserOut
from app.security import CSRF_HEADER, SESSION_COOKIE, csrf_token_for
from app.services import auth as auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class InvalidLogin(AppError):
    status_code = 401


def _start_session(response: Response, token: str) -> None:
    set_session_cookie(response, token)
    response.headers[CSRF_HEADER] = csrf_token_for(token)


@router.post("/register", response_model=UserOut, status_code=201)
async def register(data: Credentials, response: Response, db: AsyncSession = Depends(get_db)):
    user = await auth_service.register(db, data)
    _start_session(response, await auth_service.create_session(db, user))
    return user


@router.post("/login", response_model=UserOut)
@limiter.limit(LOGIN_LIMIT)
async def login(request: Request, data: Credentials, response: Response, db: AsyncSession = Depends(get_db)):
    user = await auth_service.authenticate(db, data.email, data.password)
    if user is None:
        raise InvalidLogin("Email ou senha inválidos.")
    _start_session(response, await auth_service.create_session(db, user))
    return user


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    if token := request.cookies.get(SESSION_COOKIE):
        await auth_service.delete_session(db, token)
    clear_session_cookie(response)


@router.get("/me", response_model=UserOut)
async def me(request: Request, response: Response, user: User = Depends(get_current_user)):
    response.headers[CSRF_HEADER] = csrf_token_for(request.cookies[SESSION_COOKIE])
    return user
