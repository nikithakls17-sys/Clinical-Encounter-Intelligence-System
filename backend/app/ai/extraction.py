"""RAG extraction of symptoms, medications and ICD-10 diagnoses from an encounter note.

Pipeline:
  1. retrieve candidate ICD-10 codes for the note
  2. prompt the model with the note + candidates, requesting strict JSON
  3. validate the output (schema, code exists in reference table, text is grounded in the note)
  4. write one ai_suggestions row (always, even on failure) and one extracted_entities row per item

Nothing extracted here changes the patient's record. Entities stay "pending" until a provider reviews them.
"""

import hashlib
import json
import time
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.ai.llm import LLMClient
from app.ai.retrieval import RetrievedDoc, Retriever
from app.config import settings

PROMPT_VERSION = "extract-v1"

SYSTEM_PROMPT = """You are a clinical documentation assistant. Extract structured data from one encounter note.

Rules:
- Only extract what the note states. Do not infer diagnoses or medications that are not written.
- "text" must be copied verbatim from the note (a short span), so it can be highlighted.
- Symptoms: patient-reported complaints and exam findings, not diagnoses.
- Medications: every drug mentioned. "action" is what this encounter does with it: start, continue, change,
  stop, or mentioned (history only). Use the lowercase generic name for "name".
- Diagnoses: assign an ICD-10-CM code. Prefer a code from CANDIDATE CODES. If none fits, give your best code
  and set "code_from_candidates" to false.
- "confidence" is 0 to 1: how sure you are the item is correct as extracted.
"""


# ------------------------------------------------------------------- output schema


class Symptom(BaseModel):
    text: str
    normalized: str
    negated: bool
    confidence: float = Field(ge=0, le=1)


class Medication(BaseModel):
    text: str
    name: str
    dose: str | None
    frequency: str | None
    route: str | None
    action: Literal["start", "continue", "change", "stop", "mentioned"]
    confidence: float = Field(ge=0, le=1)


class Diagnosis(BaseModel):
    text: str
    description: str
    icd10_code: str
    code_from_candidates: bool
    confidence: float = Field(ge=0, le=1)


class Extraction(BaseModel):
    symptoms: list[Symptom]
    medications: list[Medication]
    diagnoses: list[Diagnosis]


def _strict(schema: dict) -> dict:
    """Adapt a Pydantic JSON schema to OpenAI strict mode: every property required, no extras."""
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        schema["required"] = list(schema.get("properties", {}))
    for key in ("properties", "$defs"):
        for sub in schema.get(key, {}).values():
            _strict(sub)
    for key in ("items", "anyOf"):
        val = schema.get(key)
        for sub in val if isinstance(val, list) else [val] if val else []:
            _strict(sub)
    for sub in schema.get("properties", {}).values():
        sub.pop("title", None)
        # OpenAI strict mode does not accept numeric bounds; Pydantic still enforces them on parse.
        sub.pop("minimum", None)
        sub.pop("maximum", None)
    schema.pop("title", None)
    return schema


EXTRACTION_SCHEMA = _strict(Extraction.model_json_schema())


# ------------------------------------------------------------------------ pipeline


class ExtractionConflict(Exception):
    pass


def build_messages(note: str, candidates: list[RetrievedDoc]) -> list[dict]:
    candidate_block = "\n".join(f"- {d.text}" for d in candidates) or "(none)"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"CANDIDATE CODES:\n{candidate_block}\n\nNOTE:\n{note}"},
    ]


def _grounded(span: str, note: str) -> bool:
    return " ".join(span.lower().split()) in " ".join(note.lower().split())


def _entities(
    parsed: Extraction, note: str, known_codes: set[str], encounter_id: int
) -> list[models.ExtractedEntity]:
    out = []
    for s in parsed.symptoms:
        out.append(models.ExtractedEntity(
            encounter_id=encounter_id, entity_type=models.EntityType.SYMPTOM, text=s.text[:200],
            normalized=s.normalized[:200], confidence=s.confidence,
            attributes={"negated": s.negated, "grounded": _grounded(s.text, note)},
        ))
    for m in parsed.medications:
        out.append(models.ExtractedEntity(
            encounter_id=encounter_id, entity_type=models.EntityType.MEDICATION, text=m.text[:200],
            normalized=m.name.lower()[:200], confidence=m.confidence,
            attributes={"dose": m.dose, "frequency": m.frequency, "route": m.route, "action": m.action,
                        "grounded": _grounded(m.text, note)},
        ))
    for d in parsed.diagnoses:
        code = d.icd10_code.strip().upper()
        out.append(models.ExtractedEntity(
            encounter_id=encounter_id, entity_type=models.EntityType.DIAGNOSIS, text=d.text[:200],
            normalized=d.description[:200], code=code[:20], confidence=d.confidence,
            attributes={"code_in_reference": code in known_codes, "code_from_candidates": d.code_from_candidates,
                        "grounded": _grounded(d.text, note)},
        ))
    return out


def extract_encounter(
    session: Session, encounter: models.Encounter, llm: LLMClient, retriever: Retriever
) -> models.AISuggestion:
    if encounter.status == models.EncounterStatus.REVIEWED:
        raise ExtractionConflict("Encounter has already been reviewed")

    candidates = retriever.retrieve(session, encounter.note_text, settings.retrieval_top_k)
    messages = build_messages(encounter.note_text, candidates)
    suggestion = models.AISuggestion(
        encounter_id=encounter.id,
        model=llm.model,
        prompt_version=PROMPT_VERSION,
        input_sha256=hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest(),
        retrieved_context=[d.as_dict() | {"retriever": retriever.name} for d in candidates],
        raw_output="",
    )

    started = time.perf_counter()
    try:
        completion = llm.complete_json(messages, "clinical_extraction", EXTRACTION_SCHEMA)
    except Exception as exc:  # network, auth, rate limit: log the failed call and re-raise
        suggestion.latency_ms = int((time.perf_counter() - started) * 1000)
        suggestion.error = f"{type(exc).__name__}: {exc}"[:2000]
        session.add(suggestion)
        session.commit()
        raise
    suggestion.latency_ms = int((time.perf_counter() - started) * 1000)
    suggestion.model = completion.model
    suggestion.raw_output = completion.text
    suggestion.prompt_tokens = completion.prompt_tokens
    suggestion.completion_tokens = completion.completion_tokens

    try:
        parsed = Extraction.model_validate_json(completion.text)
    except ValidationError as exc:
        suggestion.error = f"parse error: {exc}"[:2000]
        session.add(suggestion)
        session.commit()
        return suggestion

    # Older unreviewed suggestions for this encounter are replaced by this one.
    for old in session.scalars(
        select(models.AISuggestion).where(
            models.AISuggestion.encounter_id == encounter.id,
            models.AISuggestion.review_status == models.ReviewStatus.PENDING,
        )
    ):
        old.review_status = models.ReviewStatus.SUPERSEDED
        for ent in old.entities:
            ent.review_status = models.ReviewStatus.SUPERSEDED

    suggestion.parsed_output = parsed.model_dump()
    known_codes = set(session.scalars(select(models.ICD10Code.code)))
    suggestion.entities = _entities(parsed, encounter.note_text, known_codes, encounter.id)
    encounter.status = models.EncounterStatus.EXTRACTED
    session.add(suggestion)
    session.commit()
    return suggestion
