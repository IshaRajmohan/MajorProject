"""
In-memory ObservationStore.

Observations are append-only (never deleted). Synchronized twin state and
sync history are stored separately from the observation log.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from models import (
    CaseMeta,
    CaseState,
    DocumentRecord,
    FactState,
    Observation,
    SyncHistoryEntry,
)


class ObservationStore:
    def __init__(self) -> None:
        self.cases: Dict[str, CaseMeta] = {}
        self.observations: Dict[str, List[Observation]] = {}
        self.documents: Dict[str, List[DocumentRecord]] = {}
        self.states: Dict[str, CaseState] = {}
        self.unresolved: Dict[str, set[str]] = {}
        self.history: Dict[str, List[SyncHistoryEntry]] = {}

    def create_case(
        self,
        case_id: Optional[str] = None,
        title: str = "Untitled case",
        description: str = "",
    ) -> CaseMeta:
        cid = case_id or f"CASE-{uuid4().hex[:8].upper()}"
        if cid in self.cases:
            return self.cases[cid]
        meta = CaseMeta(case_id=cid, title=title, description=description)
        self.cases[cid] = meta
        self.observations[cid] = []
        self.documents[cid] = []
        self.states[cid] = CaseState(case_id=cid)
        self.unresolved[cid] = set()
        self.history[cid] = []
        return meta

    def ensure_case(self, case_id: str) -> CaseMeta:
        if case_id not in self.cases:
            return self.create_case(case_id=case_id)
        return self.cases[case_id]

    def list_cases(self) -> List[CaseMeta]:
        return list(self.cases.values())

    def add_observation(self, obs: Observation) -> Observation:
        """Append-only: never updates or deletes prior observations."""
        self.ensure_case(obs.case_id)
        self.observations[obs.case_id].append(obs)
        return obs

    def add_document(self, doc: DocumentRecord) -> DocumentRecord:
        self.ensure_case(doc.case_id)
        self.documents[doc.case_id].append(doc)
        return doc

    def get_observations(self, case_id: str, fact_key: Optional[str] = None) -> List[Observation]:
        self.ensure_case(case_id)
        obs = list(self.observations.get(case_id, []))
        if fact_key is not None:
            obs = [o for o in obs if o.fact_key == fact_key]
        return obs

    def get_documents(self, case_id: str) -> List[DocumentRecord]:
        self.ensure_case(case_id)
        return list(self.documents.get(case_id, []))

    def get_state(self, case_id: str) -> CaseState:
        self.ensure_case(case_id)
        return deepcopy(self.states[case_id])

    def get_fact_value(self, case_id: str, fact_key: str) -> Any:
        state = self.ensure_case(case_id) and self.states[case_id]
        fact = state.facts.get(fact_key)
        if fact is None or not fact.resolved:
            return None
        return fact.value

    def set_fact(
        self,
        case_id: str,
        fact_key: str,
        value: Any,
        confidence: float,
        supporting_ids: List[str],
    ) -> None:
        self.ensure_case(case_id)
        self.states[case_id].facts[fact_key] = FactState(
            fact_key=fact_key,
            value=value,
            confidence=confidence,
            resolved=True,
            last_updated=datetime.now(timezone.utc),
            supporting_observation_ids=list(supporting_ids),
        )
        self.unresolved[case_id].discard(fact_key)

    def mark_unresolved(self, case_id: str, fact_key: str, retain_existing: bool = True) -> None:
        self.ensure_case(case_id)
        self.unresolved[case_id].add(fact_key)
        facts = self.states[case_id].facts
        if fact_key not in facts:
            facts[fact_key] = FactState(fact_key=fact_key, resolved=False)
        elif not retain_existing:
            facts[fact_key].resolved = False

    def get_unresolved(self, case_id: str) -> List[str]:
        self.ensure_case(case_id)
        return sorted(self.unresolved.get(case_id, set()))

    def append_history(self, entry: SyncHistoryEntry) -> SyncHistoryEntry:
        self.ensure_case(entry.case_id)
        self.history[entry.case_id].append(entry)
        return entry

    def get_history(self, case_id: str) -> List[SyncHistoryEntry]:
        self.ensure_case(case_id)
        return list(self.history.get(case_id, []))

    def timeline_event_times(self, case_id: str, exclude_obs_id: Optional[str] = None) -> List[datetime]:
        times: List[datetime] = []
        for o in self.get_observations(case_id):
            if exclude_obs_id and o.observation_id == exclude_obs_id:
                continue
            times.append(o.event_time)
        return times

    def reset(self) -> None:
        """Clear all in-memory data (tests / demos)."""
        self.cases.clear()
        self.observations.clear()
        self.documents.clear()
        self.states.clear()
        self.unresolved.clear()
        self.history.clear()


# Singleton used by the API and sync service
observation_store = ObservationStore()
