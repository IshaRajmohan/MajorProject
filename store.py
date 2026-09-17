"""
Backward-compatible store facade.

Delegates to observation_store so existing imports (`from store import store`)
keep working. Prefer observation_store / sync_service for new code.
"""

from __future__ import annotations

from observation_store import ObservationStore, observation_store

# Shared singleton — same object used by sync_service / digital_twin / API
store: ObservationStore = observation_store
