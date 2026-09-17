"""
End-to-end pipeline:
  text → Gemini (or fallback) → observations (JSON files) → CAMS → Digital Twin → history/conflicts
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from cams import synchronize
from config import DELTA, TAU, WEIGHTS
from file_repository import FileRepository, repo as default_repo
from gemini_extractor import extract_from_text
from models import Observation


def _parse_dt(value: Any, fallback: Optional[datetime] = None) -> datetime:
    if value is None or value == "":
        return fallback or datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return fallback or datetime.now(timezone.utc)


def _obs_from_dict(d: Dict[str, Any]) -> Observation:
    """Load a stored observation dict into the CAMS Observation model."""
    return Observation(
        observation_id=d.get("observation_id") or str(uuid4()),
        case_id=d["case_id"],
        fact_key=d["fact_key"],
        value=d["value"],
        source_id=d.get("source_id") or d.get("source") or "unknown",
        source_type=d.get("source_type") or "unknown",
        event_time=_parse_dt(d.get("event_time")),
        ingestion_time=_parse_dt(d.get("ingestion_time")),
        extraction_reliability=float(
            d.get("extraction_reliability", d.get("extraction_confidence", 0.7))
        ),
        evidence=d.get("evidence") or "",
        status=d.get("status") or "recorded",
        document_id=d.get("document_id"),
    )


def _plain_english(decision: Any, top_factors: Optional[Dict[str, float]] = None) -> str:
    """Human-readable reason from CAMS decision (no JS CAMS logic)."""
    parts: List[str] = []
    if decision.decided:
        parts.append(f"The system ACCEPTED “{decision.accepted_value}” for {decision.fact_key}.")
        if decision.C1 is not None:
            parts.append(f"Top confidence C1={decision.C1:.3f} met threshold τ={decision.tau}.")
        if decision.C2 is not None and decision.margin is not None:
            parts.append(
                f"It beat the next candidate by margin {decision.margin:.3f} (need ≥ δ={decision.delta})."
            )
    else:
        parts.append(
            f"The system ABSTAINED on {decision.fact_key} and did not replace the current Digital Twin value."
        )
        parts.append(decision.message)
        parts.append("All competing observations are kept for provenance.")

    if top_factors:
        a, t, x, e = (
            top_factors.get("source_authority"),
            top_factors.get("temporal_consistency"),
            top_factors.get("cross_source_corroboration"),
            top_factors.get("extraction_reliability"),
        )
        if a is not None and a >= 0.8:
            parts.append("This source type is considered more authoritative for this fact (high A).")
        if a is not None and a <= 0.4:
            parts.append("This source type has lower authority for this fact (low A).")
        if t is not None and t < 0.5:
            parts.append("The event timing looks inconsistent with the case timeline (low T).")
        if t is not None and t >= 0.85:
            parts.append("The event timing fits the known timeline well (high T).")
        if x is not None and x >= 0.66:
            parts.append("This value is supported by multiple distinct sources (high X).")
        if x is not None and x <= 0.34:
            parts.append("Few distinct sources agree on this value (low X).")
        if e is not None and e < 0.4:
            parts.append("Extraction confidence for this claim is low (low E).")
        if e is not None and e >= 0.85:
            parts.append("Extraction confidence for this claim is high (high E).")

    if not decision.decided and decision.C2 is not None and decision.margin is not None:
        if decision.margin < decision.delta:
            parts.append(
                "The evidence is inconsistent or too close to call, so the system did not replace the current state."
            )
    return " ".join(parts)


class Pipeline:
    def __init__(self, repository: Optional[FileRepository] = None) -> None:
        self.repo = repository or default_repo

    def create_case(
        self,
        case_id: Optional[str] = None,
        title: str = "Untitled case",
        description: str = "",
    ) -> Dict[str, Any]:
        return self.repo.create_case(case_id=case_id, title=title, description=description)

    def ingest_text(
        self,
        case_id: str,
        text: str,
        source: str = "user",
        source_type: str = "unknown",
        title: str = "",
        force_fallback: bool = False,
    ) -> Dict[str, Any]:
        """
        Full pipeline for POST /cases/{id}/text
        """
        self.repo.ensure_case(case_id)
        now = datetime.now(timezone.utc)
        document_id = str(uuid4())

        extraction = extract_from_text(text, source_type=source_type, force_fallback=force_fallback)

        doc = {
            "document_id": document_id,
            "case_id": case_id,
            "source": source,
            "source_id": source,
            "source_type": source_type,
            "title": title or f"{source_type}:{source}",
            "text": text,
            "ingestion_time": now.isoformat(),
            "extractor": extraction["extractor"],
            "extractor_note": extraction["note"],
        }
        self.repo.append_document(case_id, doc)

        new_obs: List[Dict[str, Any]] = []
        for fact in extraction["facts"]:
            event_time = _parse_dt(fact.get("event_time"), fallback=now)
            conf = float(fact.get("extraction_confidence", 0.7))
            oid = str(uuid4())
            obs = {
                "observation_id": oid,
                "case_id": case_id,
                "source": source,
                "source_id": source,
                "source_type": source_type,
                "fact_key": fact["fact_key"],
                "value": fact["value"],
                "event_time": event_time.isoformat(),
                "ingestion_time": now.isoformat(),
                "evidence": fact.get("evidence") or "",
                "extraction_confidence": conf,
                "extraction_reliability": conf,  # CAMS field
                "status": "recorded",
                "document_id": document_id,
            }
            new_obs.append(obs)

        if new_obs:
            self.repo.append_observations(case_id, new_obs)

        # Run CAMS per affected fact_key using ALL stored observations
        fact_keys = sorted({o["fact_key"] for o in new_obs}) or []
        decisions = []
        for fk in fact_keys:
            decisions.append(self._run_cams_for_fact(case_id, fk, trigger_document_id=document_id))

        return {
            "case_id": case_id,
            "document": doc,
            "extraction": {
                "extractor": extraction["extractor"],
                "note": extraction["note"],
                "facts": extraction["facts"],
            },
            "observations_created": new_obs,
            "decisions": decisions,
            "facts": self.repo.get_facts(case_id),
            "conflicts": self.repo.get_conflicts(case_id),
            "history_tail": self.repo.get_history(case_id)[-len(decisions) :] if decisions else [],
        }

    def _run_cams_for_fact(
        self,
        case_id: str,
        fact_key: str,
        trigger_document_id: Optional[str] = None,
        trigger_observation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        stored = self.repo.get_observations(case_id, fact_key)
        observations = [_obs_from_dict(o) for o in stored]
        timeline = [_parse_dt(o.get("event_time")) for o in self.repo.get_observations(case_id)]
        previous = self.repo.get_fact_value(case_id, fact_key)

        decision = synchronize(
            case_id=case_id,
            fact_key=fact_key,
            observations=observations,
            timeline=timeline,
            previous_value=previous,
            tau=TAU,
            delta=DELTA,
            weights=WEIGHTS,
        )

        supporting: List[str] = []
        top_factors = None
        if decision.candidates:
            supporting = list(decision.candidates[0].supporting_observation_ids)
            top_factors = decision.candidates[0].factors.model_dump()

        explanation = _plain_english(decision, top_factors)

        # Update Digital Twin ONLY if decided
        if decision.decided:
            provenance = []
            by_id = {o["observation_id"]: o for o in stored}
            for oid in supporting:
                if oid in by_id:
                    o = by_id[oid]
                    provenance.append(
                        {
                            "observation_id": oid,
                            "source": o.get("source") or o.get("source_id"),
                            "source_type": o.get("source_type"),
                            "value": o.get("value"),
                            "evidence": o.get("evidence"),
                            "document_id": o.get("document_id"),
                        }
                    )
            self.repo.set_fact(
                case_id,
                fact_key,
                {
                    "fact_key": fact_key,
                    "value": decision.accepted_value,
                    "status": "resolved",
                    "confidence": decision.C1,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "supporting_observation_ids": supporting,
                    "provenance": provenance,
                },
            )
            self.repo.clear_conflict(case_id, fact_key)
        else:
            # Do NOT overwrite current fact — mark conflict / unresolved
            competing = []
            for c in decision.candidates:
                competing.append(
                    {
                        "value": c.value,
                        "confidence": c.confidence,
                        "factors": c.factors.model_dump(),
                        "supporting_observation_ids": c.supporting_observation_ids,
                        "supporting_source_ids": c.supporting_source_ids,
                    }
                )
            self.repo.set_conflict(
                case_id,
                fact_key,
                {
                    "fact_key": fact_key,
                    "status": "unresolved",
                    "reason": decision.message,
                    "explanation": explanation,
                    "previous_value": previous,
                    "C1": decision.C1,
                    "C2": decision.C2,
                    "margin": decision.margin,
                    "candidates": competing,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            # If fact never existed, record open placeholder without inventing a value
            facts = self.repo.get_facts(case_id)
            if fact_key not in facts:
                self.repo.set_fact(
                    case_id,
                    fact_key,
                    {
                        "fact_key": fact_key,
                        "value": previous,
                        "status": "unresolved",
                        "confidence": decision.C1,
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                        "supporting_observation_ids": supporting,
                        "provenance": [],
                    },
                )
            elif facts[fact_key].get("status") == "resolved":
                # Keep resolved value but note contested via conflicts.json
                pass

        history_entry = {
            "history_id": str(uuid4()),
            "case_id": case_id,
            "fact_key": fact_key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decision": "ACCEPTED" if decision.decided else "ABSTAINED",
            "decided": decision.decided,
            "selected_value": decision.accepted_value if decision.decided else None,
            "previous_value": previous,
            "unresolved": not decision.decided,
            "C1": decision.C1,
            "C2": decision.C2,
            "margin": decision.margin,
            "tau": decision.tau,
            "delta": decision.delta,
            "weights": dict(WEIGHTS),
            "candidates": [c.model_dump() for c in decision.candidates],
            "supporting_observation_ids": supporting,
            "reason": decision.message,
            "explanation": explanation,
            "trigger_document_id": trigger_document_id,
            "trigger_observation_id": trigger_observation_id,
        }
        self.repo.append_history(case_id, history_entry)
        return history_entry

    def resync(self, case_id: str) -> Dict[str, Any]:
        """Re-run CAMS for every fact_key present in observations."""
        self.repo.ensure_case(case_id)
        keys = sorted({o["fact_key"] for o in self.repo.get_observations(case_id)})
        decisions = [self._run_cams_for_fact(case_id, fk) for fk in keys]
        return {
            "case_id": case_id,
            "decisions": decisions,
            "facts": self.repo.get_facts(case_id),
            "conflicts": self.repo.get_conflicts(case_id),
        }

    def case_snapshot(self, case_id: str) -> Dict[str, Any]:
        meta = self.repo.get_case(case_id)
        return {
            **meta,
            "facts": self.repo.get_facts(case_id),
            "conflicts": self.repo.get_conflicts(case_id),
            "observation_count": len(self.repo.get_observations(case_id)),
            "document_count": len(self.repo.get_documents(case_id)),
            "history_count": len(self.repo.get_history(case_id)),
        }

    def provenance(self, case_id: str) -> Dict[str, Any]:
        """
        Trace each current fact → history → observations → evidence → original text.
        """
        facts = self.repo.get_facts(case_id)
        obs_by_id = {o["observation_id"]: o for o in self.repo.get_observations(case_id)}
        docs_by_id = {d["document_id"]: d for d in self.repo.get_documents(case_id)}
        history = self.repo.get_history(case_id)

        out: Dict[str, Any] = {}
        for fact_key, fact in facts.items():
            chain = []
            for oid in fact.get("supporting_observation_ids") or []:
                o = obs_by_id.get(oid)
                if not o:
                    continue
                doc = docs_by_id.get(o.get("document_id") or "")
                chain.append(
                    {
                        "observation": o,
                        "evidence": o.get("evidence"),
                        "document_id": o.get("document_id"),
                        "original_text": (doc or {}).get("text"),
                        "source": o.get("source") or o.get("source_id"),
                        "source_type": o.get("source_type"),
                    }
                )
            related_hist = [h for h in history if h.get("fact_key") == fact_key]
            out[fact_key] = {
                "current_fact": fact,
                "latest_decision": related_hist[-1] if related_hist else None,
                "trace": chain,
            }
        return {"case_id": case_id, "provenance": out}


pipeline = Pipeline()
