from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import Conflict, NotFound
from app.models import Subject, Subscription, User
from app.schemas import SubjectIn, normalize_code


async def get_by_code(db: AsyncSession, raw_code: str) -> Subject:
    code = normalize_code(raw_code)
    subject = await db.scalar(select(Subject).where(Subject.code == code))
    if subject is None:
        raise NotFound(f"A matéria #{code} não existe.")
    return subject


async def search(db: AsyncSession, q: str, limit: int = 8) -> list[Subject]:
    q = normalize_code(q) if q.strip().startswith("#") else q.strip().lower()
    q = q.replace("\\", "").replace("%", "")
    if not q:
        return []
    like = f"%{q.replace('_', r'\_')}%"
    stmt = (
        select(Subject)
        .where(or_(Subject.code.like(like, escape="\\"), func.lower(Subject.name).like(like, escape="\\")))
        .order_by(Subject.code)
        .limit(limit)
    )
    return list(await db.scalars(stmt))


async def create(db: AsyncSession, user: User, data: SubjectIn) -> Subject:
    """Cria a matéria e já inscreve quem criou."""
    subject = Subject(code=data.code, name=data.name, color=data.color.lower(), created_by=user.id)
    db.add(subject)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise Conflict(f"O código #{data.code} já está em uso.") from None
    db.add(Subscription(user_id=user.id, subject_id=subject.id, active=True))
    await db.commit()
    return subject


async def subscriber_count(db: AsyncSession, subject: Subject) -> int:
    return await db.scalar(select(func.count()).where(Subscription.subject_id == subject.id)) or 0


async def list_subscriptions(db: AsyncSession, user: User) -> list[Subscription]:
    stmt = (
        select(Subscription)
        .join(Subscription.subject)
        .where(Subscription.user_id == user.id)
        .order_by(Subject.code)
    )
    return list(await db.scalars(stmt))


async def get_subscription(db: AsyncSession, user: User, subject_id: int) -> Subscription | None:
    stmt = (
        select(Subscription)
        .where(Subscription.user_id == user.id, Subscription.subject_id == subject_id)
        .execution_options(populate_existing=True)  # garante a matéria carregada junto
    )
    return await db.scalar(stmt)


async def subscribe(db: AsyncSession, user: User, raw_code: str) -> Subscription:
    """Entra na matéria. Se já estava inscrito, só reativa."""
    subject = await get_by_code(db, raw_code)
    sub = await get_subscription(db, user, subject.id)
    if sub is None:
        sub = Subscription(user_id=user.id, subject_id=subject.id, active=True)
        db.add(sub)
    else:
        sub.active = True
    await db.commit()
    return await get_subscription(db, user, subject.id)


async def set_active(db: AsyncSession, user: User, subject_id: int, active: bool) -> Subscription:
    sub = await get_subscription(db, user, subject_id)
    if sub is None:
        raise NotFound("Você não está inscrito nesta matéria.")
    sub.active = active
    await db.commit()
    return await get_subscription(db, user, subject_id)


async def unsubscribe(db: AsyncSession, user: User, subject_id: int) -> None:
    sub = await get_subscription(db, user, subject_id)
    if sub is None:
        raise NotFound("Você não está inscrito nesta matéria.")
    await db.delete(sub)
    await db.commit()
