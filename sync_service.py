"""
Sync service: Document/Observation → CAMS → Digital Twin + history.

Keeps observations append-only; updates synchronized state separately.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cams import synchronize
from document_processor import process_document
from extractor import extract_facts
from models import (
    DecisionResult,
    DocumentIn,
    DocumentRecord,
    Observation,
    ObservationIn,
    SyncHistoryEntry,
)
from observation_store import ObservationStore, observation_store
from digital_twin import JusticeDigitalTwin, digital_twin


class SyncService:
    def __init__(
        self,
        store: ObservationStore | None = None,
        twin: JusticeDigitalTwin | None = None,
    ) -> None:
        self.store = store or observation_store
        self.twin = twin or digital_twin

    def create_case(
        self,
        case_id: Optional[str] = None,
        title: str = "Untitled case",
        description: str = "",
    ) -> Dict[str, Any]:
        meta = self.store.create_case(case_id=case_id, title=title, description=description)
        return meta.model_dump()

    def ingest_observation(
        self,
        case_id: str,
        body: ObservationIn,
        trigger_document_id: Optional[str] = None,
    ) -> DecisionResult:
        self.store.ensure_case(case_id)
        obs = Observation(
            case_id=case_id,
            fact_key=body.fact_key,
            value=body.value,
            source_id=body.source_id,
            source_type=body.source_type,
            event_time=body.event_time,
            ingestion_time=body.ingestion_time or datetime.now(timezone.utc),
            extraction_reliability=body.extraction_reliability,
        )
        self.store.add_observation(obs)
        return self._run_cams(
            case_id,
            body.fact_key,
            trigger_observation_id=obs.observation_id,
            trigger_document_id=trigger_document_id,
        )

    def ingest_document(self, case_id: str, body: DocumentIn) -> Dict[str, Any]:
        self.store.ensure_case(case_id)
        cleaned, notes = process_document(body.text)
        reliability = (
            body.extraction_reliability
            if body.extraction_reliability is not None
            else _default_reliability(body.source_type)
        )
        doc = DocumentRecord(
            case_id=case_id,
            source_id=body.source_id,
            source_type=body.source_type,
            title=body.title or f"{body.source_type}:{body.source_id}",
            raw_text=body.text,
            cleaned_text=cleaned,
            event_time=body.event_time,
            extraction_reliability=reliability,
        )
        self.store.add_document(doc)

        extracted = extract_facts(
            cleaned,
            default_event_time=body.event_time or doc.ingestion_time,
            base_reliability=reliability,
        )

        decisions: List[DecisionResult] = []
        created_obs: List[Observation] = []
        for fact in extracted:
            event_time = fact.event_time or body.event_time or doc.ingestion_time
            obs_in = ObservationIn(
                fact_key=fact.fact_key,
                value=fact.value,
                source_id=body.source_id,
                source_type=body.source_type,
                event_time=event_time,
                ingestion_time=doc.ingestion_time,
                extraction_reliability=fact.confidence,
            )
            decision = self.ingest_observation(
                case_id, obs_in, trigger_document_id=doc.document_id
            )
            decisions.append(decision)
            # last observation for this fact from this ingest
            all_obs = self.store.get_observations(case_id, fact.fact_key)
            if all_obs:
                created_obs.append(all_obs[-1])

        return {
            "document": doc.model_dump(),
            "processing_notes": notes,
            "extracted_facts": [f.model_dump() for f in extracted],
            "observations": [o.model_dump() for o in created_obs],
            "decisions": [d.model_dump() for d in decisions],
            "twin": self.twin.snapshot(case_id),
        }

    def _run_cams(
        self,
        case_id: str,
        fact_key: str,
        trigger_observation_id: Optional[str] = None,
        trigger_document_id: Optional[str] = None,
    ) -> DecisionResult:
        all_for_fact = self.store.get_observations(case_id, fact_key)
        timeline = self.store.timeline_event_times(case_id)
        previous = self.store.get_fact_value(case_id, fact_key)

        decision = synchronize(
            case_id=case_id,
            fact_key=fact_key,
            observations=all_for_fact,
            timeline=timeline,
            previous_value=previous,
        )

        supporting: List[str] = []
        if decision.candidates:
            supporting = list(decision.candidates[0].supporting_observation_ids)

        if decision.decided:
            self.store.set_fact(
                case_id,
                fact_key,
                decision.accepted_value,
                confidence=decision.candidates[0].confidence if decision.candidates else (decision.C1 or 0.0),
                supporting_ids=supporting,
            )
        else:
            self.store.mark_unresolved(case_id, fact_key, retain_existing=True)

        entry = SyncHistoryEntry(
            case_id=case_id,
            fact_key=fact_key,
            decided=decision.decided,
            selected_value=decision.accepted_value if decision.decided else None,
            previous_value=previous,
            unresolved=decision.unresolved,
            C1=decision.C1,
            C2=decision.C2,
            margin=decision.margin,
            tau=decision.tau,
            delta=decision.delta,
            message=decision.message,
            supporting_observation_ids=supporting,
            candidates=decision.candidates,
            trigger_observation_id=trigger_observation_id,
            trigger_document_id=trigger_document_id,
        )
        self.store.append_history(entry)
        return decision


def _default_reliability(source_type: str) -> float:
    return {
        "court": 0.95,
        "forensic": 0.92,
        "police": 0.85,
        "lawyer": 0.75,
        "media": 0.55,
        "witness": 0.60,
        "citizen": 0.50,
    }.get(source_type.lower(), 0.70)


sync_service = SyncService()
