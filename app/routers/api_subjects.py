from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errors import Invalid
from app.deps import get_current_user
from app.models import User
from app.schemas import (AuditOut, EventIn, EventOut, EventUpdate, SubjectIn, SubjectOut,
                         SubscriptionIn, SubscriptionOut, SubscriptionPatch)
from app.services import calendar as calendar_service
from app.services import events as event_service
from app.services import subjects as subject_service

router = APIRouter(prefix="/api", tags=["api"])


# ---------- matérias ----------

@router.get("/subjects", response_model=list[SubjectOut])
async def search_subjects(q: str = "", db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await subject_service.search(db, q)


@router.post("/subjects", response_model=SubjectOut, status_code=201)
async def create_subject(data: SubjectIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await subject_service.create(db, user, data)


@router.get("/subjects/{code}")
async def get_subject(code: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    subject = await subject_service.get_by_code(db, code)
    return {
        "subject": SubjectOut.model_validate(subject),
        "subscribers": await subject_service.subscriber_count(db, subject),
        "events": [event_service.to_out(e) for e in await event_service.for_subject(db, subject)],
    }


@router.get("/subjects/{code}/history", response_model=list[AuditOut])
async def subject_history(code: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    subject = await subject_service.get_by_code(db, code)
    return [
        AuditOut(id=a.id, user=a.user.email, event_id=a.event_id, action=a.action,
                 before=a.before, after=a.after, created_at=a.created_at)
        for a in await event_service.history(db, subject)
    ]


@router.post("/subjects/{code}/events", response_model=EventOut, status_code=201)
async def create_event(code: str, data: EventIn, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    subject = await subject_service.get_by_code(db, code)
    return event_service.to_out(await event_service.create(db, user, subject, data))


# ---------- eventos ----------

@router.patch("/events/{event_id}", response_model=EventOut)
async def update_event(event_id: int, data: EventUpdate, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    return event_service.to_out(await event_service.update_event(db, user, event_id, data, data.version))


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(event_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await event_service.delete_event(db, user, event_id)


@router.post("/audit/{audit_id}/restore", response_model=EventOut, status_code=201)
async def restore_event(audit_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return event_service.to_out(await event_service.restore(db, user, audit_id))


# ---------- inscrições ----------

@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await subject_service.list_subscriptions(db, user)


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=201)
async def subscribe(data: SubscriptionIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await subject_service.subscribe(db, user, data.code)


@router.patch("/subscriptions/{subject_id}", response_model=SubscriptionOut)
async def set_active(subject_id: int, data: SubscriptionPatch, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    return await subject_service.set_active(db, user, subject_id, data.active)


@router.delete("/subscriptions/{subject_id}", status_code=204)
async def unsubscribe(subject_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await subject_service.unsubscribe(db, user, subject_id)


# ---------- calendário principal ----------

@router.get("/calendar", response_model=list[EventOut])
async def my_calendar(
    from_: date = Query(alias="from"),
    to: date = Query(description="data final (inclusiva)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if to < from_ or (to - from_).days > 400:
        raise Invalid("Intervalo inválido: 'to' deve ser >= 'from' e o intervalo no máximo 400 dias.")
    events = await calendar_service.user_events(db, user, from_, to + timedelta(days=1))
    return [event_service.to_out(e) for e in events]
