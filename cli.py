#!/usr/bin/env python3
"""
Interactive NyayaOS CLI — same case folders as the web dashboard.

Talks to Pipeline directly (no HTTP). console_log prints live CAMS reasoning
in this terminal. Real case data: data/cases/<case_id>/ only.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import console_log as clog
from db_repository import DbRepository
from paths import DATA_ROOT
from pipeline import Pipeline

repo = DbRepository(demo=False)
pipe = Pipeline(repository=repo)
ACTIVE: str | None = None
_runner = asyncio.Runner()


def wait(coro):
    return _runner.run(coro)


def case_path(case_id: str) -> Path:
    return DATA_ROOT / case_id


def show_active() -> None:
    clog.banner("ACTIVE CASE")
    if not ACTIVE:
        clog.kv("case_id", "(none — create or select a case first)")
        clog.kv("real_cases_root", str(DATA_ROOT.resolve()))
        return
    path = case_path(ACTIVE)
    clog.kv("case_id", ACTIVE)
    clog.kv("folder", str(path.resolve()))
    clog.detail("This action only touches this folder under data/cases/ (not data/demo_cases/).")


def menu() -> None:
    print(
        """
------------------------------------------------------------
  NyayaOS CLI  |  real cases → data/cases/
------------------------------------------------------------
  1) Create a case
  2) Select / open existing case
  3) Add text document (extract → CAMS → twin)
  4) Ingest file (PDF / image / .txt — OCR → CAMS)
  5) View Justice Twin (current facts + confidence)
  6) View unresolved conflicts
  7) View full case history / timeline
  8) List cases on disk
  0) Quit
------------------------------------------------------------
"""
    )


def action_create() -> None:
    global ACTIVE
    show_active()
    case_id = input("Case ID (blank = auto): ").strip() or None
    title = input("Title (optional): ").strip() or (case_id or "Untitled case")
    meta = wait(pipe.create_case(case_id=case_id, title=title, description="Created via cli.py"))
    ACTIVE = meta["case_id"]
    show_active()
    clog.done(f"case ready at {case_path(ACTIVE).resolve()}")


def action_select() -> None:
    global ACTIVE
    show_active()
    cases = wait(repo.list_cases())
    if not cases:
        clog.detail("No cases on disk yet — create one first.")
        return
    clog.banner("CASES ON DISK")
    for c in cases:
        cid = c.get("case_id")
        clog.detail(f"{cid}  →  {case_path(cid).resolve()}")
    case_id = input("Case ID to open: ").strip()
    if not case_id:
        clog.detail("Cancelled.")
        return
    try:
        wait(repo.get_case(case_id))
    except KeyError:
        clog.detail(f"Case not found: {case_id}")
        return
    ACTIVE = case_id
    show_active()
    action_view_twin()


def action_add_text() -> None:
    global ACTIVE
    show_active()
    if not ACTIVE:
        ACTIVE = input("No active case. Enter Case ID to open/create: ").strip()
        if not ACTIVE:
            clog.detail("Cancelled.")
            return
        wait(pipe.create_case(case_id=ACTIVE, title=ACTIVE))
    show_active()
    source = input("Source ID [police-ps12]: ").strip() or "police-ps12"
    source_type = input("Source type [police]: ").strip() or "police"
    print("Paste document text. End with a single line containing only END")
    lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    text = "\n".join(lines).strip()
    if not text:
        clog.detail("Empty text — nothing to do.")
        return
    force = input("Force rule-based fallback? [y/N]: ").strip().lower().startswith("y")
    show_active()
    wait(
        pipe.ingest_text(
            ACTIVE,
            text=text,
            source=source,
            source_type=source_type,
            force_fallback=force,
        )
    )
    action_view_twin()


def action_ingest_file() -> None:
    global ACTIVE
    show_active()
    if not ACTIVE:
        ACTIVE = input("No active case. Enter Case ID to open/create: ").strip()
        if not ACTIVE:
            clog.detail("Cancelled.")
            return
        wait(pipe.create_case(case_id=ACTIVE, title=ACTIVE))
    show_active()
    path_str = input("Path to file: ").strip()
    path = Path(path_str).expanduser()
    if not path.is_file():
        clog.detail(f"Not a file: {path}")
        return
    source = input("Source ID [police-ps12]: ").strip() or "police-ps12"
    source_type = input("Source type [police]: ").strip() or "police"
    force = input("Force rule-based fallback? [y/N]: ").strip().lower().startswith("y")
    show_active()
    data = path.read_bytes()
    wait(
        pipe.ingest_upload(
            ACTIVE,
            filename=path.name,
            data=data,
            source=source,
            source_type=source_type,
            force_fallback=force,
            title=path.name,
        )
    )
    action_view_twin()


def action_view_twin() -> None:
    show_active()
    if not ACTIVE:
        clog.detail("No active case.")
        return
    facts = wait(repo.get_facts(ACTIVE))
    conflicts = wait(repo.get_conflicts(ACTIVE))
    clog.banner("JUSTICE TWIN", ACTIVE)
    clog.kv("folder", str(case_path(ACTIVE).resolve()))
    if not facts and not conflicts:
        clog.detail("(empty)")
        return
    keys = sorted(set(facts) | set(conflicts))
    for k in keys:
        f = facts.get(k) or {}
        c = conflicts.get(k)
        unresolved = bool(c) or str(f.get("status") or "").lower() == "unresolved"
        status = "UNRESOLVED" if unresolved else "RESOLVED"
        clog.detail(
            f"{k}: value={f.get('value')!r}  status={status}  conf={f.get('confidence')}"
        )
        if c:
            clog.detail(f"  conflict: {c.get('explanation') or c.get('reason')}")
            clog.kv("previous_value", c.get("previous_value"), indent=4)
            clog.kv(
                "C1/C2/margin",
                f"{c.get('C1')} / {c.get('C2')} / {c.get('margin')}",
                indent=4,
            )


def action_view_conflicts() -> None:
    show_active()
    if not ACTIVE:
        clog.detail("No active case.")
        return
    conflicts = wait(repo.get_conflicts(ACTIVE))
    clog.banner("UNRESOLVED CONFLICTS", ACTIVE)
    clog.kv("folder", str(case_path(ACTIVE).resolve()))
    if not conflicts:
        clog.detail("(none)")
        return
    for k, c in conflicts.items():
        clog.detail(f"{k}: {c.get('explanation') or c.get('reason')}")
        clog.kv("previous_value", c.get("previous_value"), indent=4)
        clog.kv("C1/C2/margin", f"{c.get('C1')} / {c.get('C2')} / {c.get('margin')}", indent=4)


def action_view_history() -> None:
    show_active()
    if not ACTIVE:
        clog.detail("No active case.")
        return
    view = wait(pipe.full_case_view(ACTIVE))
    clog.banner("FULL CASE VIEW", ACTIVE)
    clog.kv("folder", view.get("storage_hint"))
    clog.kv("summary", view.get("summary"))
    clog.step("Timeline (oldest → newest):")
    for e in view.get("timeline") or []:
        if e.get("kind") == "document":
            clog.detail(
                f"[doc] {e.get('at')}  {e.get('source_type')}/{e.get('source')}  "
                f"{(e.get('preview') or '')[:100]}"
            )
        else:
            clog.detail(
                f"[cams] {e.get('at')}  {e.get('fact_key')}  {e.get('decision')}  "
                f"value={e.get('selected_value')!r}  C1={e.get('C1')} C2={e.get('C2')}"
            )
            if e.get("explanation"):
                clog.detail(f"       {e.get('explanation')}")


def action_list() -> None:
    show_active()
    cases = wait(repo.list_cases())
    clog.banner("CASES ON DISK")
    clog.kv("root", str(DATA_ROOT.resolve()))
    if not cases:
        clog.detail("(no cases yet)")
        return
    for c in cases:
        cid = c.get("case_id")
        clog.detail(f"{cid}  →  {case_path(cid).resolve()}")


def main() -> None:
    clog.banner("NyayaOS CLI")
    clog.kv("real_cases", str(DATA_ROOT.resolve()))
    clog.detail("Web dashboard (same folders): http://127.0.0.1:8000/?case=<case_id>")
    clog.detail("Demo/synthetic data lives separately under data/demo_cases/.")
    while True:
        menu()
        if ACTIVE:
            print(f"  Active case: {ACTIVE}")
            print(f"  Folder:      {case_path(ACTIVE).resolve()}")
        choice = input("Choose: ").strip()
        try:
            if choice == "1":
                action_create()
            elif choice == "2":
                action_select()
            elif choice == "3":
                action_add_text()
            elif choice == "4":
                action_ingest_file()
            elif choice == "5":
                action_view_twin()
            elif choice == "6":
                action_view_conflicts()
            elif choice == "7":
                action_view_history()
            elif choice == "8":
                action_list()
            elif choice == "0":
                clog.done("bye")
                return
            else:
                print("Unknown option.")
        except (EOFError, KeyboardInterrupt):
            print()
            clog.done("bye")
            return
        except Exception as exc:  # noqa: BLE001
            clog.banner("ERROR")
            clog.detail(f"{type(exc).__name__}: {exc}")


def run_smoke(case_id: str = "CLI-WEB-VERIFY") -> None:
    """Non-interactive: create case + one text observation (for e2e checks)."""
    global ACTIVE
    ACTIVE = case_id
    show_active()
    wait(pipe.create_case(case_id=ACTIVE, title="CLI↔web verify case"))
    show_active()
    wait(
        pipe.ingest_text(
            ACTIVE,
            text="Charge: IPC 302\nWeapon: knife\nLocation: Mumbai\n",
            source="police-ps12",
            source_type="police",
            force_fallback=True,
        )
    )
    show_active()
    action_view_twin()
    action_view_conflicts()
    clog.done(f"Open http://127.0.0.1:8000/?case={ACTIVE} to confirm the same twin.")


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--smoke":
            cid = sys.argv[2] if len(sys.argv) > 2 else "CLI-WEB-VERIFY"
            run_smoke(cid)
            sys.exit(0)
        main()
    finally:
        _runner.close()
