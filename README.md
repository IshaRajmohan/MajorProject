# NyayaOS Backend

Confidence-Aware Multi-Source Synchronization (CAMS) for a Justice Digital Twin.

## Setup

```bash
cp .env.example .env
docker compose up --build
```

API docs: http://localhost:8000/docs

## Run tests (Person B's CAMS engine, no DB needed)

```bash
pip install -r requirements.txt
pytest tests/
```

## Run the evaluation harness standalone (no DB, no API)

```bash
python -m app.eval.runner
```

## Ownership map

| Folder | Owner | Depends on |
|---|---|---|
| `app/core/`, `app/models/user.py`, `app/models/case.py`, `app/api/routes/auth.py`, `app/api/routes/cases.py` | **Person A** | nothing — build first |
| `app/cams/` | **Person B** | nothing — pure Python, start immediately |
| `app/models/observation.py`, `app/models/source_authority.py`, `app/services/observation_service.py`, `app/api/routes/observations.py`, `app/api/routes/twin.py` | **Person C** | Person A's `core/database.py`, `core/security.py`; Person B's `cams/models.py` + `cams/engine.py` shapes |
| `app/baselines/`, `app/eval/`, `app/api/routes/eval.py` | **Person D** | Person B's `cams/models.py` shapes only — start immediately |

## The one contract to agree on before splitting up

`app/cams/models.py` — the `Candidate`, `CAMSWeights`, and `SyncResult` dataclasses.
Everything else can be built independently against these three shapes.

## Folder structure

```
nyayaos/
  main.py                        # FastAPI app + router wiring
  requirements.txt
  docker-compose.yml
  Dockerfile
  .env.example
  app/
    core/
      config.py                  # [A] settings from .env
      database.py                # [A] async SQLAlchemy session
      security.py                # [A] JWT + require_role dependency
    models/
      base.py                    # [A] shared declarative Base
      user.py                    # [A]
      case.py                    # [A] Case, Entity
      observation.py             # [C] FactKey, Observation, TwinState, SyncDecision
      source_authority.py        # [C] SourceAuthorityRule, CAMSConfig
    schemas/
      auth.py                    # [A]
      observation.py             # [C]
    cams/
      models.py                  # [B] Candidate / CAMSWeights / SyncResult — THE CONTRACT
      engine.py                  # [B] synchronize() — Algorithm 1
      factors.py                 # [B] A/T/X/E heuristics
    services/
      observation_service.py     # [C] ingestion -> CAMS -> TwinState (the integration point)
    baselines/
      latest_update_wins.py      # [D]
      majority_voting.py         # [D]
      fixed_source_authority.py  # [D]
    eval/
      scenario_generator.py      # [D] conflicting/delayed/noisy/corroboration/duplicate
      metrics.py                 # [D] TSA, Conflict Resolution Accuracy, etc.
      runner.py                  # [D] runs CAMS + baselines + ablations
    api/
      routes/
        auth.py                  # [A]
        cases.py                 # [A]
        observations.py          # [C]
        twin.py                  # [C]
        eval.py                  # [D]
  tests/
    test_cams_engine.py          # [B]
  alembic/
    env.py
    versions/
```
