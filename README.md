# NyayaOS-lite

**Research prototype. CAMS confidence is NOT legal truth.**  
Evaluation numbers come from synthetic data in `evaluate.py` and are separate from demo case files.

## What this is (simple)

```
Your text
   → Gemini extracts facts + exact quotes (or a labelled rule-based fallback)
   → Each fact becomes an Observation
   → Observations are saved forever in PostgreSQL (append-only)
   → CAMS compares sources using A / T / X / E
   → Digital Twin shows only the current synchronized values
   → History, provenance, and unresolved conflicts are stored in PostgreSQL
```

| Piece | Responsibility |
| --- | --- |
| **Gemini** | Extract facts and evidence from text only. Never resolves conflicts. |
| **Observations (PostgreSQL)** | System memory. Never deleted — including duplicates and rejected claims. |
| **CAMS** | Scores and synchronizes competing claims (authority, time, corroboration, reliability). |
| **Digital Twin** | Current synchronized state only (`twin_facts`). |
| **History / conflicts** | Every decision and every abstention, with C1/C2/margin and explanations. |

## Storage (PostgreSQL + upload files)

Structured runtime state lives in PostgreSQL (`cases.id` UUID is the internal FK; `case_number` is the external `CASE-001`-style id). Raw uploaded bytes stay on disk:

```
data/cases/{case_number}/          # real cases (is_demo=false)
  uploads/                         # every raw uploaded file
  stakeholders/{source_type}__{source_id}/documents/
data/demo_cases/{case_number}/     # demo only (is_demo=true)
```

Legacy JSON files under `data/` are **not** read or written at runtime. Do not delete them yet.

Data **survives FastAPI restarts**. Observations are never removed when CAMS rejects or abstains.

## CAMS (unchanged research core)

\[
C = w_A A + w_T T + w_X X + w_E E
\]

Update the twin only if \(C_1 \ge \tau\) and \((C_1 - C_2) \ge \delta\). Otherwise **abstain** and keep the previous twin value.

Core code preserved: `cams.py`, `config.py`, `evaluate.py`, `baselines.py`, `testcases.py`, `metrics.py`.

## OCR uploads

```bash
# PDF text layer works with pypdf alone.
# Image OCR needs Tesseract:
brew install tesseract   # macOS
```

Upload via the UI or `POST /cases/{id}/upload`. Files land in:

```
data/cases/{CASE_ID}/
  uploads/
  stakeholders/{source_type}__{source_id}/documents/
```

Document metadata, observations, Twin state, history, conflicts, and provenance are stored in PostgreSQL.

Watch the **terminal running uvicorn** for step-by-step CAMS calculations.

## Configure Gemini

1. Copy `.env.example` to `.env`
2. Set `GEMINI_API_KEY=your_key`
3. Optional: `GEMINI_MODEL=gemini-2.5-flash`
4. Set `DATABASE_URL`, `JWT_SECRET_KEY`, and (for local demo users) `DEV_SEED_PASSWORD`

If the key is missing or the API fails, the backend uses a **clearly labelled deterministic fallback** so the demo still works. The UI checkbox “Use rule-based fallback” forces that path.

## Run

```bash
cd nyayaos-lite
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn main:app --host 127.0.0.1 --port 8000
# Case dashboard: http://127.0.0.1:8000/
# API docs:       http://127.0.0.1:8000/docs
```

```bash
pytest -q
python cli.py               # interactive — same data/cases/ as the web UI
python cli.py --smoke ID    # create case + one text observation
python evaluate.py          # synthetic research table → results.md
python simulate.py          # qualitative demo → data/demo_cases/ only
```

## Main API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/cases` | Create case |
| `GET` | `/cases` | List cases |
| `GET` | `/cases/{id}` | Case snapshot |
| `POST` | `/cases/{id}/text` | **Full pipeline** text→extract→store→CAMS→twin |
| `GET` | `/cases/{id}/observations` | Full observation log |
| `GET` | `/cases/{id}/facts` | Digital Twin |
| `GET` | `/cases/{id}/history` | CAMS decisions |
| `GET` | `/cases/{id}/conflicts` | Unresolved facts |
| `GET` | `/cases/{id}/provenance` | Fact → decision → obs → evidence → text |
| `POST` | `/cases/{id}/resync` | Re-run CAMS from stored observations |
| `POST` | `/auth/login` | JSON `{email, password}` → JWT access token |
| `GET` | `/auth/me` | Current user (Bearer token). Never returns password hashes. |

## Case dashboard (web + CLI)

Both UIs use the same PostgreSQL cases (`case_number`) and upload folders under `data/cases/<case_id>/`:

- **Web** — `frontend/index.html` at `/`: select/create case → twin status (facts + UNRESOLVED conflicts) → upload PDF/image/text.
- **CLI** — `python cli.py`: same actions with live `console_log` CAMS reasoning in the terminal.

Deep-link a case: `http://127.0.0.1:8000/?case=YOUR_CASE_ID`

Demo/synthetic scenarios write only to `data/demo_cases/` (`POST /demo/*`, `simulate.py`).

## Why observations are never deleted

The twin is a *view*. PostgreSQL rows are the *memory*. Keeping rejected and conflicting claims lets you prove how a value was chosen (or why the system abstained).

## Limitations

- PostgreSQL required at runtime (no JSON fallback)
- Gemini extraction quality depends on the model/key; fallback is pattern-based
- Roles/demo sources are illustrative; case-level RBAC is Task 3
- Synthetic evaluation ≠ real case accuracy
- **Not for operational justice decisions**

## PostgreSQL + authentication (Task 2)

| Piece | Responsibility |
| --- | --- |
| `db.py` | Async engine, `AsyncSessionLocal`, declarative `Base`, FastAPI `get_db()` |
| `db_models.py` | `users`, `cases`, `case_access`, documents, observations, twin, conflicts, history, provenance, uploads |
| `db_repository.py` | Async runtime repository (API-compatible dict shapes) |
| `security.py` / `auth.py` | bcrypt hashes, JWT, `POST /auth/login`, `GET /auth/me`, `get_current_active_user` |
| `seed.py` | Idempotent development users |
| `alembic/` | `t1auth0001` then `t2data0002` |

Setup:

```bash
pip install -r requirements.txt
# CREATE DATABASE nyayaos_rbac;
# .env: DATABASE_URL, JWT_SECRET_KEY, DEV_SEED_PASSWORD (see .env.example)
alembic upgrade head
python seed.py            # optional — dev users also auto-seed on API startup
uvicorn main:app --host 127.0.0.1 --port 8000
pytest -q
```

**Development seed** (created on API startup, password from `DEV_SEED_PASSWORD`, default `NyayaOS-dev-2026!`):

| Email | Role |
| --- | --- |
| `admin@nyayaos.dev` | ADMIN |
| `court@nyayaos.dev` | COURT |
| `police@nyayaos.dev` | POLICE |
| `lawyer@nyayaos.dev` | LAWYER |
| `forensic@nyayaos.dev` | FORENSIC |
| `citizen@nyayaos.dev` | CITIZEN |

**Left for Task 3:** case-level RBAC permission matrix (`case_access` checks per request).

## License / use

Student research prototype only.
