from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.errors import AppError, NotAuthenticated
from app.ratelimit import limiter
from app.routers import api_auth, api_subjects, pages
from app.security import CSRF_HEADER, SESSION_COOKIE, csrf_is_valid
from app.templating import alert, render

BASE_DIR = Path(__file__).parent
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# rotas onde o usuário ainda não está logado (pode haver um cookie de sessão velho)
CSRF_EXEMPT = {"/login", "/register", "/api/auth/login", "/api/auth/register"}

app = FastAPI(title="Calendário")
app.state.limiter = limiter
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(api_auth.router)
app.include_router(api_subjects.router)
app.include_router(pages.router)


def wants_json(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


@app.middleware("http")
async def csrf_protect(request: Request, call_next):
    """Toda escrita feita com cookie de sessão precisa do header X-CSRF-Token."""
    token = request.cookies.get(SESSION_COOKIE)
    if (request.method not in SAFE_METHODS and token and request.url.path not in CSRF_EXEMPT
            and not csrf_is_valid(token, request.headers.get(CSRF_HEADER))):
        msg = "Token CSRF inválido. Recarregue a página."
        if wants_json(request):
            return JSONResponse({"detail": msg}, status_code=403)
        return alert(msg, 403)
    return await call_next(request)


@app.exception_handler(NotAuthenticated)
async def not_authenticated(request: Request, _: NotAuthenticated):
    if wants_json(request):
        return JSONResponse({"detail": "Faça login."}, status_code=401)
    if is_htmx(request):
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(AppError)
async def app_error(request: Request, exc: AppError):
    if wants_json(request):
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)
    if is_htmx(request):
        return alert(exc.message, exc.status_code)
    return render(request, "error.html", {"message": exc.message}, status_code=exc.status_code)


@app.exception_handler(RateLimitExceeded)
async def rate_limited(request: Request, _: RateLimitExceeded):
    msg = "Muitas tentativas. Espere um minuto e tente de novo."
    if wants_json(request):
        return JSONResponse({"detail": msg}, status_code=429)
    if is_htmx(request):
        return alert(msg, 429)
    return render(request, "login.html", {"error": msg}, status_code=429)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}
