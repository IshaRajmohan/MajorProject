"""
File-based persistent repository for NyayaOS cases.

Layout:
  data/cases/{case_id}/
    case.json
    documents.json
    observations.json   # append-only memory — never delete entries
    facts.json          # Digital Twin current state only
    history.json        # every CAMS decision
    conflicts.json      # unresolved / abstained facts
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
DATA_ROOT = ROOT / "data" / "cases"

_lock = threading.RLock()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not JSON serializable: {type(obj)}")


class FileRepository:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else DATA_ROOT
        self.root.mkdir(parents=True, exist_ok=True)

    def _case_dir(self, case_id: str) -> Path:
        d = self.root / case_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _path(self, case_id: str, name: str) -> Path:
        return self._case_dir(case_id) / name

    def _read(self, case_id: str, name: str, default: Any) -> Any:
        path = self._path(case_id, name)
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, case_id: str, name: str, data: Any) -> None:
        path = self._path(case_id, name)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=_json_default)
        tmp.replace(path)

    def exists(self, case_id: str) -> bool:
        return (self.root / case_id / "case.json").exists()

    def list_cases(self) -> List[Dict[str, Any]]:
        cases = []
        if not self.root.exists():
            return cases
        for p in sorted(self.root.iterdir()):
            if p.is_dir() and (p / "case.json").exists():
                cases.append(self._read(p.name, "case.json", {}))
        return cases

    def create_case(
        self,
        case_id: Optional[str] = None,
        title: str = "Untitled case",
        description: str = "",
    ) -> Dict[str, Any]:
        with _lock:
            cid = case_id or f"CASE-{uuid4().hex[:8].upper()}"
            if self.exists(cid):
                return self.get_case(cid)
            meta = {
                "case_id": cid,
                "title": title,
                "description": description,
                "created_at": _utcnow(),
            }
            self._case_dir(cid)
            self._write(cid, "case.json", meta)
            self._write(cid, "documents.json", [])
            self._write(cid, "observations.json", [])
            self._write(cid, "facts.json", {})
            self._write(cid, "history.json", [])
            self._write(cid, "conflicts.json", {})
            return meta

    def get_case(self, case_id: str) -> Dict[str, Any]:
        if not self.exists(case_id):
            raise KeyError(f"case not found: {case_id}")
        return self._read(case_id, "case.json", {})

    def ensure_case(self, case_id: str, title: str = "", description: str = "") -> Dict[str, Any]:
        if self.exists(case_id):
            return self.get_case(case_id)
        return self.create_case(case_id=case_id, title=title or case_id, description=description)

    # ---- documents (append-only) ----

    def append_document(self, case_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        with _lock:
            self.ensure_case(case_id)
            docs = self._read(case_id, "documents.json", [])
            docs.append(doc)
            self._write(case_id, "documents.json", docs)
            return doc

    def get_documents(self, case_id: str) -> List[Dict[str, Any]]:
        self.ensure_case(case_id)
        return list(self._read(case_id, "documents.json", []))

    def get_document(self, case_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        for d in self.get_documents(case_id):
            if d.get("document_id") == document_id:
                return d
        return None

    # ---- observations (append-only — NEVER delete) ----

    def append_observations(self, case_id: str, observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        with _lock:
            self.ensure_case(case_id)
            existing = self._read(case_id, "observations.json", [])
            existing.extend(observations)
            self._write(case_id, "observations.json", existing)
            return observations

    def get_observations(self, case_id: str, fact_key: Optional[str] = None) -> List[Dict[str, Any]]:
        self.ensure_case(case_id)
        obs = list(self._read(case_id, "observations.json", []))
        if fact_key is not None:
            obs = [o for o in obs if o.get("fact_key") == fact_key]
        return obs

    # ---- facts (Digital Twin current state — may update in place) ----

    def get_facts(self, case_id: str) -> Dict[str, Any]:
        self.ensure_case(case_id)
        return dict(self._read(case_id, "facts.json", {}))

    def set_fact(self, case_id: str, fact_key: str, fact: Dict[str, Any]) -> None:
        with _lock:
            self.ensure_case(case_id)
            facts = self._read(case_id, "facts.json", {})
            facts[fact_key] = fact
            self._write(case_id, "facts.json", facts)

    def get_fact_value(self, case_id: str, fact_key: str) -> Any:
        facts = self.get_facts(case_id)
        f = facts.get(fact_key)
        if not f or f.get("status") != "resolved":
            return None
        return f.get("value")

    # ---- history (append-only) ----

    def append_history(self, case_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        with _lock:
            self.ensure_case(case_id)
            hist = self._read(case_id, "history.json", [])
            hist.append(entry)
            self._write(case_id, "history.json", hist)
            return entry

    def get_history(self, case_id: str) -> List[Dict[str, Any]]:
        self.ensure_case(case_id)
        return list(self._read(case_id, "history.json", []))

    # ---- conflicts ----

    def get_conflicts(self, case_id: str) -> Dict[str, Any]:
        self.ensure_case(case_id)
        return dict(self._read(case_id, "conflicts.json", {}))

    def set_conflict(self, case_id: str, fact_key: str, conflict: Dict[str, Any]) -> None:
        with _lock:
            self.ensure_case(case_id)
            conflicts = self._read(case_id, "conflicts.json", {})
            conflicts[fact_key] = conflict
            self._write(case_id, "conflicts.json", conflicts)

    def clear_conflict(self, case_id: str, fact_key: str) -> None:
        with _lock:
            self.ensure_case(case_id)
            conflicts = self._read(case_id, "conflicts.json", {})
            if fact_key in conflicts:
                del conflicts[fact_key]
                self._write(case_id, "conflicts.json", conflicts)

    def delete_case_dir(self, case_id: str) -> None:
        """Test helper only — removes a case folder. Not used by the API for observations."""
        import shutil

        d = self.root / case_id
        if d.exists():
            shutil.rmtree(d)

    def reset_all(self) -> None:
        """Test / demo helper — wipe all cases under this root."""
        import shutil

        with _lock:
            if self.root.exists():
                shutil.rmtree(self.root)
            self.root.mkdir(parents=True, exist_ok=True)


# Default singleton (production data path)
repo = FileRepository()
