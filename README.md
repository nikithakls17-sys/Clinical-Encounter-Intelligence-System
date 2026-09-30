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
- [ ] FastAPI endpoints
- [ ] RAG extraction pipeline
- [ ] Anomaly rules (drug interactions, allergy conflicts, duplicate therapy, missed follow-ups)
- [ ] React provider dashboard
- [ ] Audit log review UI

## Data model
| Group | Tables |
|---|---|
| Clinical | `providers`, `patients`, `allergies`, `encounters`, `patient_medications`, `follow_ups` |
| AI output | `ai_suggestions` (audit log, one row per model call), `extracted_entities` |
| Rules | `anomaly_flags` |
| Reference | `icd10_codes`, `drug_interactions` |

## Running locally
```bash
docker compose up -d db                 # Postgres 16 on localhost:5432
cp .env.example .env
python -m venv .venv && .venv/Scripts/pip install -r backend/requirements.txt   # use .venv/bin on macOS/Linux
cd backend
python -m app.seed.seed --reset         # create tables and load synthetic data
python -m pytest                        # tests run on in-memory SQLite
```
