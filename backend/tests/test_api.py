from app import models
from app.models import utcnow


def _add_flag(session, patient_id=1, encounter_id=1, severity=models.Severity.HIGH):
    flag = models.AnomalyFlag(
        patient_id=patient_id, encounter_id=encounter_id, flag_type=models.FlagType.MED_INTERACTION,
        severity=severity, rule_id="test", message="warfarin + ibuprofen",
    )
    session.add(flag)
    session.commit()
    return flag


def _add_suggestion(session, encounter_id=1):
    s = models.AISuggestion(
        encounter_id=encounter_id, model="test-model", prompt_version="v1", input_sha256="0" * 64,
        retrieved_context=[{"code": "M17.11"}], raw_output='{"diagnoses": []}', parsed_output={"diagnoses": []},
    )
    session.add(s)
    session.flush()
    session.add(models.ExtractedEntity(
        encounter_id=encounter_id, suggestion_id=s.id, entity_type=models.EntityType.DIAGNOSIS,
        text="Osteoarthritis of right knee", code="M17.11", confidence=0.93,
    ))
    session.commit()
    return s


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_list_patients_and_search(client):
    assert len(client.get("/api/patients").json()) == 10
    hits = client.get("/api/patients", params={"q": "vance"}).json()
    assert [p["mrn"] for p in hits] == ["CEIS-1001"]


def test_patient_detail(client, session):
    _add_flag(session)
    p = client.get("/api/patients/1").json()
    assert p["mrn"] == "CEIS-1001"
    assert {m["name"] for m in p["medications"]} == {"warfarin", "metoprolol"}
    assert p["allergies"][0]["substance"] == "sulfa drugs"
    assert len(p["encounters"]) == 2
    assert p["encounters"][0]["encounter_date"] >= p["encounters"][1]["encounter_date"]
    assert p["open_flag_count"] == 1


def test_patient_not_found(client):
    assert client.get("/api/patients/999").status_code == 404


def test_list_encounters_filters(client):
    assert len(client.get("/api/encounters").json()) == 12
    assert len(client.get("/api/encounters", params={"patient_id": 1}).json()) == 2
    assert client.get("/api/encounters", params={"status": "reviewed"}).json() == []
    assert client.get("/api/encounters", params={"status": "bogus"}).status_code == 422


def test_encounter_detail_includes_ai_output_and_flags(client, session):
    _add_suggestion(session)
    _add_flag(session)
    e = client.get("/api/encounters/1").json()
    assert "warfarin" in e["note_text"]
    assert e["patient_name"] == "Harold Vance"
    assert e["entities"][0]["code"] == "M17.11"
    assert len(e["suggestions"]) == 1 and len(e["flags"]) == 1
    assert e["follow_ups"][0]["description"] == "Recheck INR"


def test_create_encounter(client):
    body = {
        "patient_id": 2, "provider_id": 1, "encounter_date": "2026-09-30",
        "encounter_type": "office visit", "note_text": "S: Follow-up. A: Stable. P: Continue.",
    }
    r = client.post("/api/encounters", json=body)
    assert r.status_code == 201
    assert r.json()["status"] == "pending"
    assert client.post("/api/encounters", json=body | {"patient_id": 999}).status_code == 422
    assert client.post("/api/encounters", json=body | {"note_text": ""}).status_code == 422


def test_flags_list_and_resolve(client, session):
    flag = _add_flag(session)
    assert len(client.get("/api/flags").json()) == 1
    assert client.get("/api/flags", params={"severity": "low"}).json() == []

    r = client.post(f"/api/flags/{flag.id}/resolve", json={"provider_id": 2})
    assert r.status_code == 200 and r.json()["resolved_by"] == 2
    assert client.get("/api/flags").json() == []
    assert len(client.get("/api/flags", params={"resolved": True}).json()) == 1
    assert client.post(f"/api/flags/{flag.id}/resolve", json={"provider_id": 2}).status_code == 409


def test_suggestion_audit_log(client, session):
    s = _add_suggestion(session)
    listed = client.get("/api/suggestions", params={"review_status": "pending"}).json()
    assert [x["id"] for x in listed] == [s.id]
    detail = client.get(f"/api/suggestions/{s.id}").json()
    assert detail["raw_output"] == '{"diagnoses": []}'
    assert detail["retrieved_context"] == [{"code": "M17.11"}]
    assert detail["entities"][0]["confidence"] == 0.93
    assert client.get("/api/suggestions/999").status_code == 404


def test_dashboard_summary(client, session):
    _add_flag(session, severity=models.Severity.HIGH)
    _add_flag(session, severity=models.Severity.MODERATE)
    resolved = _add_flag(session, severity=models.Severity.LOW)
    resolved.resolved_at = utcnow()
    session.commit()
    _add_suggestion(session)

    d = client.get("/api/dashboard/summary").json()
    assert d["patients"] == 10
    assert d["encounters_pending_extraction"] == 12
    assert d["open_flags"] == {"low": 0, "moderate": 1, "high": 1}
    assert d["overdue_follow_ups"] >= 5
    assert d["suggestions_by_review_status"]["pending"] == 1
