"""
OWNER: Person A
Seed bootstrap admin, demo role users, and one demo case.

Usage (from MajorProject/):
  python -m app.seed
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.case import Case, Entity
from app.models.user import User

# Demo passwords are for local/dev only — change in production.
SEED_USERS = [
    {
        "name": "System Admin",
        "email": "admin@nyayaos.dev",
        "password": "AdminPass123!",
        "role": "admin",
        "org": "NyayaOS",
    },
    {
        "name": "Inspector Rao",
        "email": "police@nyayaos.dev",
        "password": "PolicePass123!",
        "role": "police",
        "org": "City Police",
    },
    {
        "name": "Judge Mehta",
        "email": "court@nyayaos.dev",
        "password": "CourtPass123!",
        "role": "court",
        "org": "District Court",
    },
    {
        "name": "Adv. Sharma",
        "email": "lawyer@nyayaos.dev",
        "password": "LawyerPass123!",
        "role": "lawyer",
        "org": "Legal Aid",
    },
    {
        "name": "Dr. Iyer",
        "email": "forensic@nyayaos.dev",
        "password": "ForensicPass123!",
        "role": "forensic",
        "org": "FSL",
    },
    {
        "name": "Citizen User",
        "email": "citizen@nyayaos.dev",
        "password": "CitizenPass123!",
        "role": "citizen",
        "org": None,
    },
]

DEMO_CASE = {
    "case_number": "NYA-2026-001",
    "title": "State vs. Demo Accused — Bail Status Sync",
    "status": "open",
}


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        for row in SEED_USERS:
            existing = await db.execute(select(User).where(User.email == row["email"]))
            if existing.scalar_one_or_none() is None:
                db.add(
                    User(
                        name=row["name"],
                        email=row["email"],
                        hashed_password=hash_password(row["password"]),
                        role=row["role"],
                        org=row["org"],
                    )
                )

        case_result = await db.execute(
            select(Case).where(Case.case_number == DEMO_CASE["case_number"])
        )
        case = case_result.scalar_one_or_none()
        if case is None:
            case = Case(**DEMO_CASE)
            db.add(case)
            await db.flush()
            db.add(
                Entity(
                    case_id=case.id,
                    entity_type="person",
                    label="Demo Accused",
                    attributes={"role_in_case": "accused", "age": 34},
                )
            )

        await db.commit()
        print("Seed complete: users + demo case NYA-2026-001")


if __name__ == "__main__":
    asyncio.run(seed())
