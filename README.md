# NyayaOS-lite

**Research prototype. CAMS confidence is NOT legal truth.**  
Evaluation numbers come from synthetic data in `evaluate.py` and are separate from demo case files.

## What this is (simple)

```
Your text
   → Gemini extracts facts + exact quotes (or a labelled rule-based fallback)
   → Each fact becomes an Observation
   → Observations are saved forever as JSON files
   → CAMS compares sources using A / T / X / E
   → Digital Twin shows only the current synchronized values
   → History, provenance, and unresolved conflicts are stored
```

| Piece | Responsibility |
| --- | --- |
| **Gemini** | Extract facts and evidence from text only. Never resolves conflicts. |
| **Observations (JSON)** | System memory. Never deleted — including duplicates and rejected claims. |
| **CAMS** | Scores and synchronizes competing claims (authority, time, corroboration, reliability). |
| **Digital Twin** | Current synchronized state only (`facts.json`). |
| **History / conflicts** | Every decision and every abstention, with C1/C2/margin and explanations. |

## File storage (no database)

```
data/cases/CASE-001/
  case.json
  documents.json      # original user texts
  observations.json   # append-only memory
  facts.json          # Digital Twin (current state)
  history.json        # every CAMS decision
  conflicts.json      # unresolved / abstained facts
```

Data **survives FastAPI restarts**. Observations are never removed when CAMS rejects or abstains.

## CAMS (unchanged research core)

\[
C = w_A A + w_T T + w_X X + w_E E
\]

Update the twin only if \(C_1 \ge \tau\) and \((C_1 - C_2) \ge \delta\). Otherwise **abstain** and keep the previous twin value.

Core code preserved: `cams.py`, `config.py`, `evaluate.py`, `baselines.py`, `testcases.py`, `metrics.py`.

## Configure Gemini

1. Copy `.env.example` to `.env`
2. Set `GEMINI_API_KEY=your_key`
3. Optional: `GEMINI_MODEL=gemini-2.0-flash`

If the key is missing or the API fails, the backend uses a **clearly labelled deterministic fallback** so the demo still works. The UI checkbox “Use rule-based fallback” forces that path.

## Run

```bash
cd nyayaos-lite
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn main:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000/
```

```bash
pytest -q
python evaluate.py          # synthetic research table → results.md
python simulate.py          # qualitative observation scenarios
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
| `POST` | `/demo/case-001` | Built-in multi-source demo |

## Frontend

Plain HTML/CSS/JS at `/`. Explains Input → Extraction → Observations → CAMS → Decision → Twin → Provenance → Conflicts.  
Uses `fetch()` only — **no CAMS logic in JavaScript**.

## Why observations are never deleted

The twin is a *view*. The files are the *memory*. Keeping rejected and conflicting claims lets you prove how a value was chosen (or why the system abstained).

## Limitations

- File JSON storage, not a production database
- Gemini extraction quality depends on the model/key; fallback is pattern-based
- Roles/demo sources are illustrative
- Synthetic evaluation ≠ real case accuracy
- **Not for operational justice decisions**

## License / use

Student research prototype only.
