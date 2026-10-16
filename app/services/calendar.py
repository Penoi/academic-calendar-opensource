import calendar as pycal
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Event, User
from app.services import events as event_service
from app.services import subjects as subject_service

MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
          "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
WEEKDAYS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]

_cal = pycal.Calendar(firstweekday=pycal.SUNDAY)


@dataclass
class Day:
    date: date
    in_month: bool
    is_today: bool
    events: list[Event] = field(default_factory=list)


@dataclass
class Month:
    year: int
    month: int
    weeks: list[list[Day]]

    @property
    def title(self) -> str:
        return f"{MONTHS[self.month - 1]} {self.year}"

    @property
    def prev(self) -> tuple[int, int]:
        return (self.year - 1, 12) if self.month == 1 else (self.year, self.month - 1)

    @property
    def next(self) -> tuple[int, int]:
        return (self.year + 1, 1) if self.month == 12 else (self.year, self.month + 1)


def today() -> date:
    return datetime.now(settings.tz).date()


def day_bounds(start: date, end_exclusive: date) -> tuple[datetime, datetime]:
    """Intervalo de datas locais -> intervalo em UTC para consultar o banco."""
    return event_service.local_to_utc(start, None), event_service.local_to_utc(end_exclusive, None)


async def active_subject_ids(db: AsyncSession, user: User) -> list[int]:
    return [s.subject_id for s in await subject_service.list_subscriptions(db, user) if s.active]


async def user_events(db: AsyncSession, user: User, start: date, end_exclusive: date) -> list[Event]:
    """Calendário principal: eventos de todas as matérias ATIVAS do usuário no intervalo."""
    ids = await active_subject_ids(db, user)
    return await event_service.in_range(db, ids, *day_bounds(start, end_exclusive))


async def build_month(db: AsyncSession, user: User, year: int, month: int) -> Month:
    weeks = _cal.monthdatescalendar(year, month)
    first, last = weeks[0][0], weeks[-1][-1]
    by_day: dict[date, list[Event]] = defaultdict(list)
    for ev in await user_events(db, user, first, last + timedelta(days=1)):
        by_day[event_service.to_local(ev.starts_at).date()].append(ev)
    t = today()
    return Month(year, month, [
        [Day(d, d.month == month, d == t, by_day.get(d, [])) for d in week] for week in weeks
    ])
