"""Justice Digital Twin — current synchronized case state + provenance view."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from config import ROLE_PERMISSIONS, WEIGHTS, TAU, DELTA
from models import CaseMeta, FactState, Observation, SyncHistoryEntry
from observation_store import ObservationStore, observation_store


class JusticeDigitalTwin:
    """
    Separates current synced state from the full observation provenance log.
    """

    def __init__(self, store: ObservationStore | None = None) -> None:
        self.store = store or observation_store

    def snapshot(self, case_id: str, role: Optional[str] = None) -> Dict[str, Any]:
        meta = self.store.ensure_case(case_id)
        state = self.store.get_state(case_id)
        unresolved = self.store.get_unresolved(case_id)
        history = self.store.get_history(case_id)
        observations = self.store.get_observations(case_id)
        documents = self.store.get_documents(case_id)

        facts = {k: v.model_dump() for k, v in state.facts.items()}
        view = {
            "case_id": case_id,
            "title": meta.title,
            "description": meta.description,
            "created_at": meta.created_at.isoformat(),
            "facts": facts,
            "unresolved": unresolved,
            "observation_count": len(observations),
            "document_count": len(documents),
            "history_count": len(history),
            "cams_config": {"weights": WEIGHTS, "tau": TAU, "delta": DELTA},
            "role": role or "court",
        }

        if role:
            view = self.apply_role_filter(view, observations, history, role)
        else:
            view["observations"] = [o.model_dump() for o in observations]
            view["history"] = [h.model_dump() for h in history]
            view["documents"] = [d.model_dump() for d in documents]
            view["provenance"] = self._provenance(facts, observations)

        return view

    def _provenance(
        self,
        facts: Dict[str, Any],
        observations: List[Observation],
    ) -> Dict[str, List[Dict[str, Any]]]:
        by_id = {o.observation_id: o for o in observations}
        prov: Dict[str, List[Dict[str, Any]]] = {}
        for key, fact in facts.items():
            ids = fact.get("supporting_observation_ids") or []
            prov[key] = [
                by_id[i].model_dump() for i in ids if i in by_id
            ]
        return prov

    def apply_role_filter(
        self,
        view: Dict[str, Any],
        observations: List[Observation],
        history: List[SyncHistoryEntry],
        role: str,
    ) -> Dict[str, Any]:
        perms = ROLE_PERMISSIONS.get(role.lower(), ROLE_PERMISSIONS["citizen"])
        allowed = perms.get("visible_facts")

        facts = view["facts"]
        if allowed is not None:
            facts = {k: v for k, v in facts.items() if k in allowed}
            unresolved = [u for u in view["unresolved"] if u in allowed]
        else:
            unresolved = list(view["unresolved"])

        filtered = dict(view)
        filtered["facts"] = facts
        filtered["role"] = role.lower()
        filtered["permissions"] = perms

        if perms.get("show_unresolved"):
            filtered["unresolved"] = unresolved
        else:
            filtered["unresolved"] = []

        if not perms.get("show_confidence"):
            for f in filtered["facts"].values():
                f.pop("confidence", None)

        if perms.get("show_raw_observations"):
            obs = observations
            if allowed is not None:
                obs = [o for o in obs if o.fact_key in allowed]
            filtered["observations"] = [o.model_dump() for o in obs]
        else:
            filtered["observations"] = []

        if perms.get("show_history"):
            hist = history
            if allowed is not None:
                hist = [h for h in hist if h.fact_key in allowed]
            filtered["history"] = [h.model_dump() for h in hist]
        else:
            filtered["history"] = []

        if perms.get("show_provenance"):
            filtered["provenance"] = self._provenance(filtered["facts"], observations)
        else:
            filtered["provenance"] = {}

        # Citizens don't see document bodies
        if role.lower() == "citizen":
            filtered["documents"] = []
        else:
            filtered["documents"] = [d.model_dump() for d in self.store.get_documents(view["case_id"])]

        return filtered


digital_twin = JusticeDigitalTwin()
