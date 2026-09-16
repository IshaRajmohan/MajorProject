"""
OWNER: Person C
This is the INTEGRATION POINT between ingestion (this file) and Person B's
pure CAMS engine (app/cams/engine.py). Agree on Candidate/SyncResult shapes
with Person B before writing this — otherwise work independently.

Flow:
  1. Store the incoming observation as a new row (never overwrite).
  2. Fetch all observations for the same fact_key_id (including the new one).
  3. Build Candidate objects via app.cams.factors (A/T/X/E).
  4. Call app.cams.engine.synchronize(candidates, weights, tau, delta).
  5. Persist a SyncDecision row with the full score snapshot.
  6. If decision == "updated": upsert TwinState. Otherwise leave TwinState untouched.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.observation import ObservationCreate

class ObservationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest(self, payload: ObservationCreate):
        # TODO(Person C): implement the 6 steps in the docstring above
        raise NotImplementedError
