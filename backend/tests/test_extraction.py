import hashlib
import json

import pytest
from sqlalchemy import select

from app import models
from app.ai.deps import get_llm, get_retriever
from app.ai.llm import Completion
from app.ai.retrieval import EmbeddingRetriever, KeywordRetriever
from app.config import settings
from app.main import app

ENCOUNTER_1_OUTPUT = {
    "symptoms": [
        {"text": "right knee pain", "normalized": "knee pain", "negated": False, "confidence": 0.95},
        {"text": "Denies fever", "normalized": "fever", "negated": True, "confidence": 0.9},
    ],
    "medications": [
        {"text": "warfarin 5 mg daily", "name": "warfarin", "dose": "5 mg", "frequency": "daily", "route": "oral",
         "action": "continue", "confidence": 0.97},
        {"text": "Start ibuprofen 400 mg three times daily", "name": "Ibuprofen", "dose": "400 mg",
         "frequency": "three times daily", "route": "oral", "action": "start", "confidence": 0.96},
    ],
    "diagnoses": [
        {"text": "Osteoarthritis of right knee", "description": "Unilateral primary osteoarthritis, right knee",
         "icd10_code": "M17.11", "code_from_candidates": True, "confidence": 0.92},
        {"text": "gout of the left toe", "description": "Gout", "icd10_code": "M10.9",
         "code_from_candidates": False, "confidence": 0.4},
    ],
}


class FakeLLM:
    model = "fake-model"

    def __init__(self, output: str | Exception):
        self.output = output
        self.calls: list[list[dict]] = []

    def complete_json(self, messages, schema_name, schema):
        self.calls.append(messages)
        if isinstance(self.output, Exception):
            raise self.output
        return Completion(model="fake-model-2026", text=self.output, prompt_tokens=812, completion_tokens=240)


class FakeEmbedder:
    """Hashed bag-of-words vectors: deterministic and similarity-preserving enough for ranking tests."""

    model = "fake-embed"

    def __init__(self):
        self.embedded = 0

    def embed(self, texts):
        self.embedded += len(texts)
        out = []
        for t in texts:
            v = [0.0] * 64
            for tok in t.lower().replace(",", " ").split():
                v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % 64] += 1
            out.append(v)
        return out


@pytest.fixture
def use_llm():
    def install(output):
        llm = FakeLLM(output if isinstance(output, (str, Exception)) else json.dumps(output))
        app.dependency_overrides[get_llm] = lambda: llm
        app.dependency_overrides[get_retriever] = KeywordRetriever
        return llm
    return install


# ------------------------------------------------------------------ retrieval


def test_keyword_retriever_finds_relevant_codes(session):
    note = session.get(models.Encounter, 3).note_text  # heart failure note
    codes = [d.ref_id for d in KeywordRetriever().retrieve(session, note, k=5)]
    assert codes[:2] == ["I50.22", "I10"]  # written in the note, so pinned first


def test_keyword_retriever_without_explicit_codes(session):
    codes = [d.ref_id for d in KeywordRetriever().retrieve(session, "patient with atrial fibrillation", k=3)]
    assert codes[0] == "I48.91"


def test_embedding_retriever_caches_vectors(session):
    embedder = FakeEmbedder()
    r = EmbeddingRetriever(embedder)
    assert r.index(session) == 34
    assert r.index(session) == 0  # unchanged docs are not re-embedded

    session.get(models.ICD10Code, "I10").description = "Hypertension, essential"
    session.commit()
    assert r.index(session) == 1

    docs = r.retrieve(session, "streptococcal pharyngitis sore throat", k=3)
    assert docs[0].ref_id == "J02.0"


# ------------------------------------------------------------------ extraction


def test_extract_writes_audit_row_and_entities(client, session, use_llm):
    llm = use_llm(ENCOUNTER_1_OUTPUT)
    r = client.post("/api/encounters/1/extract")
    assert r.status_code == 201, r.text
    s = r.json()

    # Audit fields
    assert s["model"] == "fake-model-2026" and s["prompt_version"] == "extract-v1"
    assert len(s["input_sha256"]) == 64
    assert s["prompt_tokens"] == 812 and s["completion_tokens"] == 240
    assert s["raw_output"] == json.dumps(ENCOUNTER_1_OUTPUT)
    assert s["parsed_output"]["diagnoses"][0]["icd10_code"] == "M17.11"
    assert s["error"] is None and s["review_status"] == "pending"
    assert {c["ref_id"] for c in s["retrieved_context"]} >= {"M17.11", "I48.91"}
    assert all(c["retriever"] == "bm25" for c in s["retrieved_context"])

    # Retrieved candidates are in the prompt
    assert "M17.11 Unilateral primary osteoarthritis, right knee" in llm.calls[0][1]["content"]

    # Entities and validation
    ents = {(e["entity_type"], e["normalized"]): e for e in s["entities"]}
    assert len(ents) == 6
    ibu = ents[("medication", "ibuprofen")]
    assert ibu["attributes"]["action"] == "start" and ibu["attributes"]["grounded"] is True
    assert ents[("symptom", "fever")]["attributes"]["negated"] is True
    gout = ents[("diagnosis", "Gout")]
    assert gout["attributes"] == {"code_in_reference": False, "code_from_candidates": False, "grounded": False}
    assert ents[("diagnosis", "Unilateral primary osteoarthritis, right knee")]["attributes"]["code_in_reference"]

    e = client.get("/api/encounters/1").json()
    assert e["status"] == "extracted" and len(e["entities"]) == 6


def test_reextract_supersedes_previous_suggestion(client, use_llm):
    use_llm(ENCOUNTER_1_OUTPUT)
    first = client.post("/api/encounters/1/extract").json()
    use_llm(ENCOUNTER_1_OUTPUT | {"symptoms": []})
    second = client.post("/api/encounters/1/extract").json()

    assert client.get(f"/api/suggestions/{first['id']}").json()["review_status"] == "superseded"
    assert client.get(f"/api/suggestions/{second['id']}").json()["review_status"] == "pending"
    assert len(client.get("/api/encounters/1").json()["entities"]) == 4


def test_unparseable_output_is_logged(client, session, use_llm):
    use_llm('{"symptoms": "oops"}')
    s = client.post("/api/encounters/1/extract").json()
    assert s["error"].startswith("parse error")
    assert s["raw_output"] == '{"symptoms": "oops"}' and s["parsed_output"] is None and s["entities"] == []
    assert client.get("/api/encounters/1").json()["status"] == "pending"


def test_model_failure_is_logged_and_returns_502(client, session, use_llm):
    use_llm(TimeoutError("upstream timed out"))
    assert client.post("/api/encounters/1/extract").status_code == 502
    row = session.scalars(select(models.AISuggestion)).one()
    assert row.error == "TimeoutError: upstream timed out" and row.raw_output == ""


def test_reviewed_encounter_cannot_be_reextracted(client, session, use_llm):
    use_llm(ENCOUNTER_1_OUTPUT)
    session.get(models.Encounter, 1).status = models.EncounterStatus.REVIEWED
    session.commit()
    assert client.post("/api/encounters/1/extract").status_code == 409


def test_missing_api_key_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None)
    r = client.post("/api/encounters/1/extract")
    assert r.status_code == 503 and "OPENAI_API_KEY" in r.json()["detail"]


def test_unknown_encounter_returns_404(client, use_llm):
    use_llm(ENCOUNTER_1_OUTPUT)
    assert client.post("/api/encounters/999/extract").status_code == 404
