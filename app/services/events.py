from datetime import UTC, date, datetime, time

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import Conflict, Invalid, NotFound
from app.models import AuditLog, Event, Subject, User, utcnow
from app.schemas import EventIn, EventOut, SubjectOut

# campos do evento guardados no histórico (permitem restaurar um evento apagado)
SNAPSHOT_FIELDS = ("title", "description", "starts_at", "ends_at", "all_day")


def local_to_utc(d: date, t: time | None) -> datetime:
    return datetime.combine(d, t or time(0), tzinfo=settings.tz).astimezone(UTC)


def to_local(dt: datetime) -> datetime:
    return dt.astimezone(settings.tz)


def _fields(data: EventIn) -> dict:
    return {
        "title": data.title,
        "description": data.description,
        "starts_at": local_to_utc(data.date, data.start_time),
        "ends_at": local_to_utc(data.date, data.end_time) if data.end_time else None,
        "all_day": data.start_time is None,
    }


def snapshot(event: Event) -> dict:
    snap = {f: getattr(event, f) for f in SNAPSHOT_FIELDS}
    for key in ("starts_at", "ends_at"):
        if snap[key] is not None:
            snap[key] = snap[key].isoformat()
    return snap


def to_out(event: Event) -> EventOut:
    return EventOut(
        id=event.id,
        subject=SubjectOut.model_validate(event.subject),
        title=event.title,
        description=event.description,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        all_day=event.all_day,
        version=event.version,
        updated_by=event.editor.email,
        updated_at=event.updated_at,
    )


def _log(db: AsyncSession, user: User, subject_id: int, event_id: int | None, action: str,
         before: dict | None, after: dict | None) -> None:
    db.add(AuditLog(user_id=user.id, subject_id=subject_id, event_id=event_id,
                    action=action, before=before, after=after))


async def get(db: AsyncSession, event_id: int) -> Event:
    event = await db.scalar(select(Event).where(Event.id == event_id).execution_options(populate_existing=True))
    if event is None:
        raise NotFound("Este evento não existe mais.")
    return event


async def create(db: AsyncSession, user: User, subject: Subject, data: EventIn) -> Event:
    event = Event(subject_id=subject.id, updated_by=user.id, **_fields(data))
    db.add(event)
    await db.flush()
    _log(db, user, subject.id, event.id, "CREATE", None, snapshot(event))
    await db.commit()
    return await get(db, event.id)


async def update_event(db: AsyncSession, user: User, event_id: int, data: EventIn, version: int) -> Event:
    event = await get(db, event_id)
    before = snapshot(event)
    # o UPDATE só acontece se ninguém salvou antes (version igual à que o usuário viu)
    result = await db.execute(
        update(Event)
        .where(Event.id == event_id, Event.version == version)
        .values(**_fields(data), version=Event.version + 1, updated_by=user.id, updated_at=utcnow())
    )
    if result.rowcount == 0:
        await db.rollback()
        raise Conflict("Outra pessoa alterou este evento enquanto você editava. Confira a versão atual.")
    event = await get(db, event_id)
    _log(db, user, event.subject_id, event.id, "UPDATE", before, snapshot(event))
    await db.commit()
    return event


async def delete_event(db: AsyncSession, user: User, event_id: int) -> None:
    event = await get(db, event_id)
    _log(db, user, event.subject_id, event.id, "DELETE", snapshot(event), None)
    await db.delete(event)
    await db.commit()


async def restore(db: AsyncSession, user: User, audit_id: int) -> Event:
    """Recria um evento apagado a partir do histórico."""
    entry = await db.get(AuditLog, audit_id)
    if entry is None or entry.action != "DELETE" or not entry.before:
        raise Invalid("Só é possível restaurar eventos apagados.")
    if await db.scalar(select(AuditLog.id).where(AuditLog.action == "RESTORE", AuditLog.event_id == entry.event_id)):
        raise Conflict("Este evento já foi restaurado.")
    data = dict(entry.before)
    for key in ("starts_at", "ends_at"):
        if data[key] is not None:
            data[key] = datetime.fromisoformat(data[key])
    event = Event(subject_id=entry.subject_id, updated_by=user.id, **data)
    db.add(event)
    await db.flush()
    # event_id aponta para o evento original, para saber que aquele DELETE já foi desfeito
    _log(db, user, entry.subject_id, entry.event_id, "RESTORE", None, {**snapshot(event), "new_id": event.id})
    await db.commit()
    return await get(db, event.id)


async def in_range(db: AsyncSession, subject_ids: list[int], start: datetime, end: datetime) -> list[Event]:
    if not subject_ids:
        return []
    stmt = (
        select(Event)
        .where(Event.subject_id.in_(subject_ids), Event.starts_at >= start, Event.starts_at < end)
        .order_by(Event.starts_at, Event.all_day.desc(), Event.title)
    )
    return list(await db.scalars(stmt))


async def for_subject(db: AsyncSession, subject: Subject) -> list[Event]:
    stmt = select(Event).where(Event.subject_id == subject.id).order_by(Event.starts_at)
    return list(await db.scalars(stmt))


async def history(db: AsyncSession, subject: Subject, limit: int = 50) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.subject_id == subject.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    return list(await db.scalars(stmt))


async def restored_ids(db: AsyncSession, subject: Subject) -> set[int]:
    """event_ids originais que já foram restaurados (para esconder o botão)."""
    stmt = select(AuditLog.event_id).where(AuditLog.subject_id == subject.id, AuditLog.action == "RESTORE")
    return {i for i in await db.scalars(stmt) if i is not None}
