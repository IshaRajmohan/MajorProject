"""In-memory store for cases, observations, synced state, and unresolved facts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models import CaseState, FactState, Observation


class Store:
    def __init__(self) -> None:
        self.observations: Dict[str, List[Observation]] = {}
        self.states: Dict[str, CaseState] = {}
        self.unresolved: Dict[str, set[str]] = {}

    def ensure_case(self, case_id: str) -> CaseState:
        if case_id not in self.states:
            self.states[case_id] = CaseState(case_id=case_id)
            self.observations[case_id] = []
            self.unresolved[case_id] = set()
        return self.states[case_id]

    def add_observation(self, obs: Observation) -> Observation:
        self.ensure_case(obs.case_id)
        self.observations[obs.case_id].append(obs)
        return obs

    def get_observations(self, case_id: str, fact_key: Optional[str] = None) -> List[Observation]:
        self.ensure_case(case_id)
        obs = list(self.observations.get(case_id, []))
        if fact_key is not None:
            obs = [o for o in obs if o.fact_key == fact_key]
        return obs

    def get_state(self, case_id: str) -> CaseState:
        return deepcopy(self.ensure_case(case_id))

    def get_fact_value(self, case_id: str, fact_key: str) -> Any:
        state = self.ensure_case(case_id)
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
        state = self.ensure_case(case_id)
        state.facts[fact_key] = FactState(
            fact_key=fact_key,
            value=value,
            confidence=confidence,
            resolved=True,
            last_updated=datetime.now(timezone.utc),
            supporting_observation_ids=list(supporting_ids),
        )
        self.unresolved[case_id].discard(fact_key)

    def mark_unresolved(self, case_id: str, fact_key: str, retain_existing: bool = True) -> None:
        state = self.ensure_case(case_id)
        self.unresolved[case_id].add(fact_key)
        if fact_key not in state.facts:
            state.facts[fact_key] = FactState(fact_key=fact_key, resolved=False)
        elif not retain_existing:
            state.facts[fact_key].resolved = False
        # If retain_existing and already resolved, keep value but flag as currently contested

    def get_unresolved(self, case_id: str) -> List[str]:
        self.ensure_case(case_id)
        return sorted(self.unresolved.get(case_id, set()))

    def timeline_event_times(self, case_id: str, exclude_obs_id: Optional[str] = None) -> List[datetime]:
        """Event times from currently resolved facts' supporting observations, plus all obs."""
        times: List[datetime] = []
        for o in self.get_observations(case_id):
            if exclude_obs_id and o.observation_id == exclude_obs_id:
                continue
            times.append(o.event_time)
        return times


store = Store()
