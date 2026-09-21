"""Disposable-data cleanup for the Task 1-4 environment (guide step A3).

Dry run by default; pass ``--apply`` to delete. Three buckets, nothing else:

  1. demo scope      — every ``is_demo`` row (cases live in their own scope) and
                       everything under ``data/demo_cases/`` (via reset_all()).
  2. disposable real cases — ``case_number`` starting with a test prefix
                       (T2-, T3-, T14-, CLI-, VERIFY-, A11-, MANUAL- by default;
                       add more with ``--prefix``), plus their files under
                       ``data/cases/<case_number>/`` and any same-prefix orphan
                       directories that have no database row.
  3. non-seed users  — every user except the six seeded @nyayaos.dev accounts
                       (``--keep-users`` skips this bucket).

Never touched: schema, tables, migrations/alembic_version, the six seed users,
``data/cases/`` for cases outside the disposable prefixes.

Hard guard: refuses to run unless the connected PostgreSQL database name ends
with ``_rbac``, so the legacy ``nyayaos`` database can never be targeted.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
from typing import List, Sequence

from sqlalchemy import delete, select, text

import db
import db_models
from db_repository import DbRepository
from paths import DATA_ROOT, DEMO_DATA_ROOT
from seed import SEED_USERS

DISPOSABLE_CASE_PREFIXES: Sequence[str] = (
    "T2-",
    "T3-",
    "T14-",
    "CLI-",
    "VERIFY-",
    "A11-",
    "MANUAL-",
)

SEED_EMAILS = {email for email, _role in SEED_USERS}


class GuardError(RuntimeError):
    pass


async def _require_rbac_database(session) -> str:
    name = (await session.execute(text("SELECT current_database()"))).scalar_one()
    if not str(name).endswith("_rbac"):
        raise GuardError(
            f"refusing to clean database '{name}': name does not end with '_rbac'. "
            "This script only ever touches the Task 1-4 database."
        )
    return str(name)


async def _collect(session, prefixes: Sequence[str]):
    demo_cases = (
        await session.execute(
            select(db_models.Case.case_number)
            .where(db_models.Case.is_demo.is_(True))
            .order_by(db_models.Case.case_number)
        )
    ).scalars().all()

    real_cases = [
        cid
        for (cid,) in (
            await session.execute(
                select(db_models.Case.case_number)
                .where(db_models.Case.is_demo.is_(False))
                .order_by(db_models.Case.case_number)
            )
        ).all()
        if any(cid.startswith(p) for p in prefixes)
    ]

    users = (
        await session.execute(
            select(db_models.User.email, db_models.User.system_role)
            .where(db_models.User.email.notin_(SEED_EMAILS))
            .order_by(db_models.User.email)
        )
    ).all()

    known = {
        cid
        for (cid,) in (
            await session.execute(
                select(db_models.Case.case_number).where(
                    db_models.Case.is_demo.is_(False)
                )
            )
        ).all()
    }
    orphan_dirs = [
        d.name
        for d in sorted(DATA_ROOT.iterdir()) if d.is_dir()
    ] if DATA_ROOT.exists() else []
    orphan_dirs = [
        name
        for name in orphan_dirs
        if name not in known and any(name.startswith(p) for p in prefixes)
    ]

    return demo_cases, real_cases, users, orphan_dirs


async def run(args: argparse.Namespace) -> int:
    if db.AsyncSessionLocal is None:
        raise GuardError("DATABASE_URL is not configured; nothing to clean.")

    prefixes: List[str] = list(DISPOSABLE_CASE_PREFIXES)
    for p in args.prefix or []:
        p = p.upper()
        if not p.endswith("-"):
            p = p + "-"
        prefixes.append(p)

    repo_real = DbRepository(demo=False)
    repo_demo = DbRepository(demo=True)

    async with db.AsyncSessionLocal() as session:
        dbname = await _require_rbac_database(session)
        demo_cases, real_cases, users, orphan_dirs = await _collect(session, prefixes)

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"[{mode}] database: {dbname}")
    print(f"[{mode}] disposable case prefixes: {', '.join(prefixes)}")

    if not args.demo_only:
        print(f"[{mode}] demo scope: {len(demo_cases)} demo case(s)"
              + (f" -> {', '.join(demo_cases)}" if demo_cases else ""))
        print(f"[{mode}] disposable real cases: {len(real_cases)}"
              + (f" -> {', '.join(real_cases)}" if real_cases else ""))
        if orphan_dirs:
            print(f"[{mode}] same-prefix orphan dirs without a DB row: "
                  f"{len(orphan_dirs)} -> {', '.join(orphan_dirs)}")
        if args.keep_users:
            print(f"[{mode}] non-seed users: kept (--keep-users)")
        else:
            print(f"[{mode}] non-seed users: {len(users)}"
                  + (f" -> {', '.join(f'{e} ({r.value})' for e, r in users)}" if users else ""))
            print("        (deleting a user also removes their case assignments "
                  "and any submissions they made)")
    else:
        print(f"[{mode}] demo-only mode: real cases and users are left untouched")
        print(f"[{mode}] demo scope: {len(demo_cases)} demo case(s)"
              + (f" -> {', '.join(demo_cases)}" if demo_cases else ""))

    print(f"[{mode}] always preserved: schema, alembic_version, "
          f"seed users {sorted(SEED_EMAILS)}")

    if not args.apply:
        print("\nNothing was deleted. Re-run with --apply to execute.")
        return 0

    await repo_demo.reset_all()
    print(f"deleted: all demo-scope rows + {DEMO_DATA_ROOT}")

    if not args.demo_only:
        for cid in real_cases:
            await repo_real.delete_case_dir(cid)
        print(f"deleted: {len(real_cases)} disposable real case(s) with their files")
        for name in orphan_dirs:
            shutil.rmtree(DATA_ROOT / name, ignore_errors=True)
        if orphan_dirs:
            print(f"deleted: {len(orphan_dirs)} orphan director(ies)")
        if not args.keep_users and users:
            async with db.AsyncSessionLocal() as session:
                await session.execute(
                    delete(db_models.User).where(
                        db_models.User.email.in_([email for email, _role in users])
                    )
                )
                await session.commit()
            print(f"deleted: {len(users)} non-seed user(s)")

    print("\ncleanup complete. Seed users remain; log in and continue.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="execute the deletions")
    parser.add_argument("--demo-only", action="store_true",
                        help="only wipe demo scope; keep real cases and users")
    parser.add_argument("--keep-users", action="store_true",
                        help="keep non-seed users")
    parser.add_argument("--prefix", action="append",
                        help="extra disposable real-case prefix (repeatable)")
    args = parser.parse_args()
    try:
        return asyncio.run(run(args))
    except GuardError as exc:
        print(f"ABORTED: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
