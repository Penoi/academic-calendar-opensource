from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Feedback, User
from app.schemas import FeedbackIn


async def create(db: AsyncSession, user: User, data: FeedbackIn, page: str | None) -> Feedback:
    fb = Feedback(user_id=user.id, message=data.message, page=(page or None) and page[:200])
    db.add(fb)
    await db.commit()
    return fb


async def list_all(db: AsyncSession) -> list[Feedback]:
    return list(await db.scalars(select(Feedback).order_by(Feedback.created_at.desc(), Feedback.id.desc())))
