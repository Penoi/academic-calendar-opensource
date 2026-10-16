"""Promove (ou rebaixa) um usuário a administrador.

    uv run python -m app.admin pedro@exemplo.com
    uv run python -m app.admin pedro@exemplo.com --remove
"""
import asyncio
import sys

from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import User


async def set_admin(email: str, value: bool) -> bool:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None:
            return False
        user.is_admin = value
        await db.commit()
    await engine.dispose()
    return True


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--remove"]
    if len(args) != 1:
        sys.exit(__doc__)
    value = "--remove" not in sys.argv
    if not asyncio.run(set_admin(args[0], value)):
        sys.exit(f"Usuário {args[0]} não encontrado.")
    print(f"{args[0]} {'agora é' if value else 'não é mais'} administrador.")


if __name__ == "__main__":
    main()
