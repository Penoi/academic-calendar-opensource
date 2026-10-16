from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cookies import clear_session_cookie, set_session_cookie
from app.db import get_db
from app.deps import get_admin_user, get_current_user, get_optional_user
from app.errors import AppError, Conflict
from app.models import User
from app.ratelimit import LOGIN_LIMIT, limiter
from app.schemas import Credentials, EventIn, FeedbackIn, SubjectIn, friendly_error, normalize_code
from app.security import SESSION_COOKIE
from app.services import auth as auth_service
from app.services import calendar as calendar_service
from app.services import events as event_service
from app.services import feedback as feedback_service
from app.services import subjects as subject_service
from app.templating import alert, render

router = APIRouter(include_in_schema=False)

COLORS = ["#f07b1d", "#2563c9", "#e4572e", "#3a9bdc", "#f2a922", "#1d3557",
          "#0f8b8d", "#d1495b", "#6a4c93", "#8ab17d", "#b5651d", "#5c6f86"]

EVENTS_CHANGED = {"HX-Trigger": "eventsChanged"}
SUBS_CHANGED = {"HX-Trigger": "subscriptionsChanged"}


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def redirect(request: Request, url: str) -> Response:
    if is_htmx(request):
        return Response(status_code=200, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


def retarget_panel(headers: dict | None = None) -> dict:
    return {"HX-Retarget": "#panel", "HX-Reswap": "innerHTML", **(headers or {})}


def parse_event_form(title: str, date_: str, start_time: str, end_time: str, description: str) -> EventIn:
    return EventIn.model_validate({
        "title": title, "date": date_, "description": description or None,
        "start_time": start_time or None, "end_time": end_time or None,
    })


# ---------------------------------------------------------------- auth

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user: User | None = Depends(get_optional_user)):
    if user:
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html")


@router.post("/login")
@limiter.limit(LOGIN_LIMIT)
async def login_submit(request: Request, email: str = Form(""), password: str = Form(""),
                       db: AsyncSession = Depends(get_db)):
    user = await auth_service.authenticate(db, email, password)
    if user is None:
        msg = "Email ou senha inválidos."
        if is_htmx(request):
            return alert(msg)
        return render(request, "login.html", {"error": msg, "email": email}, status_code=422)
    response = redirect(request, "/")
    set_session_cookie(response, await auth_service.create_session(db, user))
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, user: User | None = Depends(get_optional_user)):
    if user:
        return RedirectResponse("/", status_code=303)
    return render(request, "register.html")


@router.post("/register")
@limiter.limit(LOGIN_LIMIT)
async def register_submit(request: Request, email: str = Form(""), password: str = Form(""),
                          password2: str = Form(""), db: AsyncSession = Depends(get_db)):
    try:
        if password != password2:
            raise AppError("As senhas não são iguais.")
        user = await auth_service.register(db, Credentials(email=email, password=password))
    except ValidationError as exc:
        msg = friendly_error(exc)
    except AppError as exc:
        msg = exc.message
    else:
        response = redirect(request, "/")
        set_session_cookie(response, await auth_service.create_session(db, user))
        return response
    if is_htmx(request):
        return alert(msg)
    return render(request, "register.html", {"error": msg, "email": email}, status_code=422)


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    if token := request.cookies.get(SESSION_COOKIE):
        await auth_service.delete_session(db, token)
    response = redirect(request, "/login")
    clear_session_cookie(response)
    return response


# ---------------------------------------------------------------- calendário principal

def _valid_month(y: int | None, m: int | None) -> tuple[int, int]:
    t = calendar_service.today()
    if y is None or m is None or not (1 <= m <= 12) or not (1900 <= y <= 2999):
        return t.year, t.month
    return y, m


async def _sidebar_ctx(db: AsyncSession, user: User) -> dict:
    return {"subs": await subject_service.list_subscriptions(db, user)}


async def _month_ctx(db: AsyncSession, user: User, y: int | None, m: int | None) -> dict:
    y, m = _valid_month(y, m)
    return {"month": await calendar_service.build_month(db, user, y, m), "today": calendar_service.today()}


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, y: int | None = None, m: int | None = None,
               db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    ctx = {"user": user, **await _sidebar_ctx(db, user), **await _month_ctx(db, user, y, m)}
    return render(request, "calendar.html", ctx)


@router.get("/partials/month", response_class=HTMLResponse)
async def month_partial(request: Request, y: int | None = None, m: int | None = None,
                        db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return render(request, "partials/month.html", await _month_ctx(db, user, y, m))


@router.get("/partials/sidebar", response_class=HTMLResponse)
async def sidebar_partial(request: Request, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    return render(request, "partials/sidebar.html", await _sidebar_ctx(db, user))


@router.get("/partials/search", response_class=HTMLResponse)
async def search_partial(request: Request, code: str = "", db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    results = await subject_service.search(db, code)
    subscribed = {s.subject_id for s in await subject_service.list_subscriptions(db, user)}
    return render(request, "partials/search_results.html",
                  {"results": results, "subscribed": subscribed, "q": normalize_code(code)})


@router.get("/partials/day", response_class=HTMLResponse)
async def day_partial(request: Request, d: date, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    return render(request, "partials/day_panel.html", await _day_ctx(db, user, d))


async def _day_ctx(db: AsyncSession, user: User, d: date) -> dict:
    subs = [s for s in await subject_service.list_subscriptions(db, user) if s.active]
    return {"day": d, "events": await calendar_service.user_events(db, user, d, d + timedelta(days=1)),
            "subs": subs}


# ---------------------------------------------------------------- inscrições

@router.post("/partials/subscriptions")
async def subscribe(request: Request, code: str = Form(""), db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    code = normalize_code(code)
    if not code:
        return alert("Digite o código da matéria, por exemplo #math01.")
    try:
        await subject_service.subscribe(db, user, code)
    except AppError as exc:
        return render(request, "partials/subscribe_error.html", {"message": exc.message, "code": code},
                      status_code=exc.status_code)
    return Response(status_code=204, headers=SUBS_CHANGED)


@router.post("/partials/subscriptions/{subject_id}/toggle")
async def toggle_subscription(subject_id: int, db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)):
    sub = await subject_service.get_subscription(db, user, subject_id)
    if sub is None:
        return alert("Você não está inscrito nesta matéria.", 404)
    await subject_service.set_active(db, user, subject_id, not sub.active)
    return Response(status_code=204, headers=SUBS_CHANGED)


@router.delete("/partials/subscriptions/{subject_id}")
async def unsubscribe(subject_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await subject_service.unsubscribe(db, user, subject_id)
    return Response(status_code=204, headers=SUBS_CHANGED)


# ---------------------------------------------------------------- matérias

@router.get("/subjects/new", response_class=HTMLResponse)
async def new_subject_page(request: Request, code: str = "", user: User = Depends(get_current_user)):
    return render(request, "subject_new.html", {"user": user, "code": normalize_code(code), "colors": COLORS})


@router.post("/subjects")
async def create_subject(request: Request, code: str = Form(""), name: str = Form(""), color: str = Form(""),
                         db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        subject = await subject_service.create(db, user, SubjectIn(code=code, name=name, color=color))
    except ValidationError as exc:
        return alert(friendly_error(exc))
    return redirect(request, f"/s/{subject.code}")


async def _subject_ctx(db: AsyncSession, user: User, code: str) -> dict:
    subject = await subject_service.get_by_code(db, code)
    return {
        "subject": subject,
        "sub": await subject_service.get_subscription(db, user, subject.id),
        "subscribers": await subject_service.subscriber_count(db, subject),
    }


async def _subject_events_ctx(db: AsyncSession, subject) -> dict:
    start_today = event_service.local_to_utc(calendar_service.today(), None)
    events = await event_service.for_subject(db, subject)
    return {"subject": subject,
            "upcoming": [e for e in events if e.starts_at >= start_today],
            "past": [e for e in events if e.starts_at < start_today][::-1]}


async def _history_ctx(db: AsyncSession, subject) -> dict:
    return {"subject": subject, "entries": await event_service.history(db, subject),
            "restored": await event_service.restored_ids(db, subject)}


@router.get("/s/{code}", response_class=HTMLResponse)
async def subject_page(request: Request, code: str, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    ctx = await _subject_ctx(db, user, code)
    ctx.update(await _subject_events_ctx(db, ctx["subject"]))
    ctx.update(await _history_ctx(db, ctx["subject"]))
    return render(request, "subject.html", {"user": user, "today": calendar_service.today(), **ctx})


@router.get("/partials/s/{code}/action", response_class=HTMLResponse)
async def subject_action(request: Request, code: str, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    return render(request, "partials/subject_action.html", await _subject_ctx(db, user, code))


@router.get("/partials/s/{code}/events", response_class=HTMLResponse)
async def subject_events(request: Request, code: str, db: AsyncSession = Depends(get_db),
                         _: User = Depends(get_current_user)):
    subject = await subject_service.get_by_code(db, code)
    return render(request, "partials/subject_events.html", await _subject_events_ctx(db, subject))


@router.get("/partials/s/{code}/history", response_class=HTMLResponse)
async def subject_history(request: Request, code: str, db: AsyncSession = Depends(get_db),
                          _: User = Depends(get_current_user)):
    subject = await subject_service.get_by_code(db, code)
    return render(request, "partials/history.html", await _history_ctx(db, subject))


# ---------------------------------------------------------------- eventos

@router.post("/s/{code}/events")
async def create_event_in_subject(
    request: Request, code: str,
    title: str = Form(""), date_: str = Form("", alias="date"), start_time: str = Form(""),
    end_time: str = Form(""), description: str = Form(""),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    subject = await subject_service.get_by_code(db, code)
    try:
        data = parse_event_form(title, date_, start_time, end_time, description)
    except ValidationError as exc:
        return alert(friendly_error(exc))
    await event_service.create(db, user, subject, data)
    return alert("Evento criado.", 200, kind="ok", headers=EVENTS_CHANGED)


@router.post("/events")
async def create_event_from_day(
    request: Request, subject_code: str = Form(""),
    title: str = Form(""), date_: str = Form("", alias="date"), start_time: str = Form(""),
    end_time: str = Form(""), description: str = Form(""),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    if not subject_code:
        return alert("Escolha a matéria do evento.")
    subject = await subject_service.get_by_code(db, subject_code)
    try:
        data = parse_event_form(title, date_, start_time, end_time, description)
    except ValidationError as exc:
        return alert(friendly_error(exc))
    await event_service.create(db, user, subject, data)
    return render(request, "partials/day_panel.html", await _day_ctx(db, user, data.date),
                  headers=retarget_panel(EVENTS_CHANGED))


@router.get("/partials/events/{event_id}", response_class=HTMLResponse)
async def event_panel(request: Request, event_id: int, db: AsyncSession = Depends(get_db),
                      _: User = Depends(get_current_user)):
    return render(request, "partials/event_panel.html", {"event": await event_service.get(db, event_id)})


@router.patch("/events/{event_id}")
async def update_event(
    request: Request, event_id: int,
    title: str = Form(""), date_: str = Form("", alias="date"), start_time: str = Form(""),
    end_time: str = Form(""), description: str = Form(""), version: int = Form(0),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    try:
        data = parse_event_form(title, date_, start_time, end_time, description)
    except ValidationError as exc:
        return alert(friendly_error(exc))
    try:
        event = await event_service.update_event(db, user, event_id, data, version)
    except Conflict as exc:
        event = await event_service.get(db, event_id)
        return render(request, "partials/event_panel.html", {"event": event, "conflict": exc.message},
                      status_code=409, headers=retarget_panel(EVENTS_CHANGED))
    return render(request, "partials/event_panel.html", {"event": event, "saved": True},
                  headers=retarget_panel(EVENTS_CHANGED))


@router.delete("/events/{event_id}")
async def delete_event(event_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await event_service.delete_event(db, user, event_id)
    return HTMLResponse("", headers=EVENTS_CHANGED)


@router.post("/audit/{audit_id}/restore")
async def restore_event(audit_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    event = await event_service.restore(db, user, audit_id)
    return alert(f"“{event.title}” foi restaurado.", 200, kind="ok", headers=EVENTS_CHANGED)


# ---------------------------------------------------------------- feedback

@router.post("/feedback")
async def send_feedback(request: Request, message: str = Form(""), page: str = Form(""),
                        db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        data = FeedbackIn(message=message)
    except ValidationError as exc:
        return alert(friendly_error(exc))
    await feedback_service.create(db, user, data, page)
    return alert("Obrigado! Seu feedback foi enviado.", 200, kind="ok")


@router.get("/admin/feedbacks", response_class=HTMLResponse)
async def admin_feedbacks(request: Request, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_admin_user)):
    return render(request, "admin_feedbacks.html", {"user": user, "feedbacks": await feedback_service.list_all(db)})
