# Clinical Encounter Intelligence System

Extracts structured data (symptoms, medications, ICD-10 diagnoses) from clinical encounter notes with a
retrieval-augmented LLM pipeline, flags medication conflicts and missed follow-ups with a rule engine, and
shows everything on a provider dashboard. Every AI suggestion is written to an audit log with the model,
prompt hash, retrieved context, raw output, and the provider's accept/edit/reject decision.

> All patient data in this repository is synthetic.

## Stack
- **Backend:** FastAPI, SQLAlchemy 2, PostgreSQL
- **AI:** OpenAI API with retrieval over ICD-10 and drug-interaction reference data
- **Frontend:** React

## Status
- [x] Database schema and synthetic seed data
- [x] FastAPI endpoints
- [x] RAG extraction pipeline
- [ ] Anomaly rules (drug interactions, allergy conflicts, duplicate therapy, missed follow-ups)
- [ ] React provider dashboard
- [ ] Audit log review UI

## Data model
| Group | Tables |
|---|---|
| Clinical | `providers`, `patients`, `allergies`, `encounters`, `patient_medications`, `follow_ups` |
| AI output | `ai_suggestions` (audit log, one row per model call), `extracted_entities` |
| Rules | `anomaly_flags` |
| Reference | `icd10_codes`, `drug_interactions`, `reference_embeddings` (cached vectors) |

## Extraction pipeline
`POST /api/encounters/{id}/extract` runs retrieval-augmented extraction on one note
(`backend/app/ai/extraction.py`):

1. **Retrieve** candidate ICD-10 codes for the note. With an API key this uses OpenAI embeddings
   (`text-embedding-3-small`, cached in `reference_embeddings` and re-embedded only when a description changes);
   without one it falls back to BM25. Codes written verbatim in the note are always included.
2. **Generate** with the OpenAI API in strict JSON-schema mode: symptoms (with negation), medications
   (dose, frequency, route, and whether this visit starts/continues/changes/stops them) and ICD-10 diagnoses.
3. **Validate**: Pydantic parses the output; every diagnosis code is checked against the reference table and
   every extracted span is checked for being grounded in the note text. These checks are stored on each entity
   so the reviewer can see them.
4. **Audit**: every call writes an `ai_suggestions` row with model, prompt version, SHA-256 of the exact prompt,
   retrieved context, raw output, parsed output, token counts, latency and any error, including calls that
   failed or returned invalid JSON. Re-running extraction marks the previous unreviewed suggestion `superseded`.

Nothing extracted changes the patient record until a provider reviews it.

Batch mode: `python -m app.ai.extract_all` processes every pending encounter.

## API
Interactive docs at `http://localhost:8000/docs` once the server is running.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/dashboard/summary` | Counts for the dashboard header: pending extractions, open flags by severity, overdue follow-ups, review status |
| GET | `/api/patients?q=` | Patient list with open-flag count and last visit; search by name or MRN |
| GET | `/api/patients/{id}` | Allergies, medications, follow-ups, encounters |
| GET | `/api/encounters?status=&patient_id=&provider_id=` | Encounter list |
| GET | `/api/encounters/{id}` | Note text, extracted entities, AI suggestions, follow-ups, flags |
| POST | `/api/encounters` | Add a new encounter note |
| POST | `/api/encounters/{id}/extract` | Run RAG extraction; returns the audit record |
| GET | `/api/flags?resolved=&severity=&flag_type=` | Anomaly flags |
| POST | `/api/flags/{id}/resolve` | Mark a flag resolved by a provider |
| GET | `/api/suggestions?review_status=` | AI audit log |
| GET | `/api/suggestions/{id}` | Full audit record: prompt hash, retrieved context, raw and parsed output, review |

## Running locally
```bash
docker compose up -d db                 # Postgres 16 on localhost:5432
cp .env.example .env
python -m venv .venv && .venv/Scripts/pip install -r backend/requirements.txt   # use .venv/bin on macOS/Linux
cd backend
python -m app.seed.seed --reset         # create tables and load synthetic data
python -m pytest                        # tests run on in-memory SQLite
uvicorn app.main:app --reload          # API on http://localhost:8000
```
