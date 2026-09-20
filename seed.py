"""Idempotent development user seed (Task 2).

Accounts (all share ``DEV_SEED_PASSWORD``, default ``NyayaOS-dev-2026!``):

  admin@nyayaos.dev      ADMIN
  court@nyayaos.dev      COURT
  police@nyayaos.dev     POLICE
  lawyer@nyayaos.dev     LAWYER
  forensic@nyayaos.dev   FORENSIC
  citizen@nyayaos.dev    CITIZEN

Existing rows are left unchanged (email match is enough). Development only.
"""

from __future__ import annotations

import os
from typing import List, Tuple

SEED_USERS: List[Tuple[str, str]] = [
    ("admin@nyayaos.dev", "ADMIN"),
    ("court@nyayaos.dev", "COURT"),
    ("police@nyayaos.dev", "POLICE"),
    ("lawyer@nyayaos.dev", "LAWYER"),
    ("forensic@nyayaos.dev", "FORENSIC"),
    ("citizen@nyayaos.dev", "CITIZEN"),
]

DEFAULT_DEV_SEED_PASSWORD = "NyayaOS-dev-2026!"


def seed_password() -> str:
    return os.getenv("DEV_SEED_PASSWORD") or DEFAULT_DEV_SEED_PASSWORD


async def seed_dev_users() -> int:
    """Insert missing seed users. Returns the number of rows inserted."""
    from sqlalchemy import select

    import db
    from db_models import SystemRole, User
    from security import hash_password

    if db.AsyncSessionLocal is None:
        return 0
    inserted = 0
    hashed = None
    async with db.AsyncSessionLocal() as session:
        for email, role_name in SEED_USERS:
            existing = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if existing is not None:
                continue
            if hashed is None:
                hashed = hash_password(seed_password())
            session.add(
                User(
                    email=email,
                    password_hash=hashed,
                    system_role=SystemRole[role_name],
                    is_active=True,
                )
            )
            inserted += 1
        await session.commit()
    return inserted


if __name__ == "__main__":
    import asyncio

    import db

    async def _run() -> None:
        if db.AsyncSessionLocal is None:
            raise SystemExit(
                "DATABASE_URL is not configured; cannot seed. See .env.example."
            )
        n = await seed_dev_users()
        print(
            f"seed complete: {n} inserted, {len(SEED_USERS) - n} already present "
            f"(password from DEV_SEED_PASSWORD)"
        )
        if db.engine is not None:
            await db.engine.dispose()

    asyncio.run(_run())
