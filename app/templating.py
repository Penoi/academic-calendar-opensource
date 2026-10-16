from datetime import date, datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.security import SESSION_COOKIE, csrf_token_for
from app.services.calendar import MONTHS, WEEKDAYS
from app.services.events import to_local

WEEKDAYS_LONG = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
FIELD_LABELS = {"title": "título", "description": "descrição", "starts_at": "data/início",
                "ends_at": "fim", "all_day": "dia inteiro"}

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def _as_date(value: date | datetime) -> date:
    return to_local(value).date() if isinstance(value, datetime) else value


def long_date(value: date | datetime) -> str:
    d = _as_date(value)
    return f"{WEEKDAYS_LONG[d.weekday()]}, {d.day} de {MONTHS[d.month - 1].lower()}"


def short_date(value: date | datetime) -> str:
    d = _as_date(value)
    return d.strftime("%d/%m/%Y")


def local_date(value: datetime) -> str:
    return to_local(value).date().isoformat()


def hm(value: datetime | None) -> str:
    return to_local(value).strftime("%H:%M") if value else ""


def short_dt(value: datetime) -> str:
    return to_local(value).strftime("%d/%m/%Y às %H:%M")


def month_abbr(value: date | datetime) -> str:
    return MONTHS[_as_date(value).month - 1][:3].lower()


def when(event) -> str:
    """'Sexta, 16 de outubro · 14:00–16:00' ou '... · Dia inteiro'."""
    base = long_date(event.starts_at)
    if event.all_day:
        return f"{base} · Dia inteiro"
    end = f"–{hm(event.ends_at)}" if event.ends_at else ""
    return f"{base} · {hm(event.starts_at)}{end}"


def _fmt_snapshot_value(key: str, value, snap: dict) -> str:
    if value is None:
        return "—"
    if key == "starts_at":
        dt = datetime.fromisoformat(value)
        return short_date(dt) if snap.get("all_day") else f"{short_date(dt)} {hm(dt)}"
    if key == "ends_at":
        return hm(datetime.fromisoformat(value))
    if key == "all_day":
        return "sim" if value else "não"
    return str(value)


def audit_changes(entry) -> list[str]:
    """Lista legível do que mudou num UPDATE: 'título: A → B'."""
    before, after = entry.before or {}, entry.after or {}
    changes = []
    for key, label in FIELD_LABELS.items():
        if key == "all_day":
            continue
        if before.get(key) != after.get(key):
            changes.append(f"{label}: {_fmt_snapshot_value(key, before.get(key), before)} → "
                           f"{_fmt_snapshot_value(key, after.get(key), after)}")
    return changes


def snapshot_when(snap: dict) -> str:
    return _fmt_snapshot_value("starts_at", snap.get("starts_at"), snap)


env = templates.env
env.filters.update(local_date=local_date, long_date=long_date, short_date=short_date, hm=hm, short_dt=short_dt,
                   month_abbr=month_abbr, when=when, snapshot_when=snapshot_when)
env.globals.update(WEEKDAYS=WEEKDAYS, audit_changes=audit_changes)


def render(request: Request, name: str, ctx: dict | None = None, status_code: int = 200,
           headers: dict | None = None) -> HTMLResponse:
    token = request.cookies.get(SESSION_COOKIE)
    context = {"csrf_token": csrf_token_for(token) if token else "", **(ctx or {})}
    return templates.TemplateResponse(request, name, context, status_code=status_code, headers=headers)


def alert(message: str, status_code: int = 422, kind: str = "error", headers: dict | None = None) -> HTMLResponse:
    from markupsafe import escape
    return HTMLResponse(f'<div class="alert alert-{kind}" role="alert">{escape(message)}</div>',
                        status_code=status_code, headers=headers)
