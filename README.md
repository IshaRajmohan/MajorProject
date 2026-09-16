# NyayaOS Backend

Confidence-Aware Multi-Source Synchronization (CAMS) for a Justice Digital Twin.

Runs **locally on Windows** with Python + PostgreSQL. Docker is **not** required.

## Prerequisites

- Python 3.11+
- PostgreSQL 14+ (local install)
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) (only needed when using AI features)

## 1. Install PostgreSQL (Windows)

1. Download the installer from https://www.postgresql.org/download/windows/
2. Install and set a password for the `postgres` superuser.
3. Ensure PostgreSQL is running (default port `5432`).
4. Open **SQL Shell (psql)** or pgAdmin and create the database + app role:

```sql
CREATE USER nyayaos WITH PASSWORD 'your_strong_password';
CREATE DATABASE nyayaos OWNER nyayaos;
GRANT ALL PRIVILEGES ON DATABASE nyayaos TO nyayaos;
```

Replace `your_strong_password` with a real password, then put the same values in `.env`.

## 2. Configure environment

```powershell
cd MajorProject
copy .env.example .env
```

Edit `.env`:

```env
DATABASE_URL=postgresql+asyncpg://USERNAME:PASSWORD@localhost:5432/nyayaos
JWT_SECRET_KEY=GENERATE_A_NEW_SECURE_SECRET
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REDIS_URL=redis://localhost:6379/0
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GEMINI_MODEL=gemini-2.5-flash
```

### Generate a JWT secret

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the output into `JWT_SECRET_KEY`. Do not commit `.env`.

### Add the Gemini API key

1. Create a key at https://aistudio.google.com/apikey
2. Set `GEMINI_API_KEY=...` in `.env`
3. Optionally change `GEMINI_MODEL` (default: `gemini-2.5-flash`)

Redis is **optional**. Person A/B and app startup do **not** require Redis. Leave `REDIS_URL` as-is or blank; a missing Redis server will not block startup.

## 3. Install and run (Windows)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- Health: http://localhost:8000/health

Seed admin (dev only): `admin@nyayaos.dev` / `AdminPass123!`

## 4. Run tests

```powershell
.venv\Scripts\activate
pytest tests/ -v
```

CAMS unit tests need no database. Auth/case tests use in-memory SQLite.

## 5. Gemini service

AI calls go through `app/services/gemini_service.py` (google-genai SDK). Routes must not call Gemini directly. The service:

- Reads `GEMINI_API_KEY` / `GEMINI_MODEL` from settings
- Never returns or logs the API key
- Raises a clear error if the key is missing
- Creates the client only when a generate call is made

## Ownership map

| Folder | Owner | Depends on |
|---|---|---|
| `app/core/`, `app/models/user.py`, `app/models/case.py`, `app/api/routes/auth.py`, `app/api/routes/cases.py` | **Person A** | — |
| `app/cams/` | **Person B** | — |
| `app/models/observation.py`, `app/services/observation_service.py`, observation/twin routes | **Person C** | A + B contracts |
| `app/baselines/`, `app/eval/` | **Person D** | B contracts |
| `app/services/gemini_service.py` | Shared AI | `.env` Gemini vars |

## Optional Docker files

`Dockerfile` and `docker-compose.yml` may still exist in the repo but are **not used** for the local Windows workflow. Ask before deleting them if you want them removed.
