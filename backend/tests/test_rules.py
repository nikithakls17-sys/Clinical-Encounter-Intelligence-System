from datetime import timedelta

from sqlalchemy import select

from app import models
from app.models import FlagType, ReviewStatus, Severity, utcnow
from app.rules.engine import current_medications, evaluate_patient, run_rules
from tests.conftest import TODAY

# The medication each seeded note introduces, as extraction would report it.
NEW_MEDS = {  # encounter_id -> (drug, action)
    1: ("ibuprofen", "start"),       # patient on warfarin
    2: ("tramadol", "start"),        # patient on sertraline
    3: ("spironolactone", "start"),  # patient on lisinopril
    4: ("clarithromycin", "start"),  # patient on simvastatin
    5: ("amoxicillin", "start"),     # patient allergic to penicillin
    7: ("ibuprofen", "start"),       # patient on naproxen
}


def add_med_entities(session, encounter_id, meds, status=ReviewStatus.PENDING):
    """Simulate an extraction that produced these (name, action) medication entities."""
    s = models.AISuggestion(encounter_id=encounter_id, model="fake", prompt_version="v", input_sha256="0" * 64,
                            raw_output="{}", review_status=status)
    session.add(s)
    session.flush()
    for name, action in meds:
        session.add(models.ExtractedEntity(
            encounter_id=encounter_id, suggestion_id=s.id, entity_type=models.EntityType.MEDICATION,
            text=name, normalized=name, attributes={"action": action}, review_status=status,
        ))
    session.commit()
    return s


def open_flags(session, patient_id=None, rule_id=None):
    stmt = select(models.AnomalyFlag).where(models.AnomalyFlag.resolved_at.is_(None))
    if patient_id:
        stmt = stmt.where(models.AnomalyFlag.patient_id == patient_id)
    if rule_id:
        stmt = stmt.where(models.AnomalyFlag.rule_id == rule_id)
    return session.scalars(stmt).all()


def test_seed_scenarios_after_extraction(session):
    for encounter_id, med in NEW_MEDS.items():
        add_med_entities(session, encounter_id, [med])
    run_rules(session, today=TODAY)

    med_flags = {
        (f.patient_id, f.rule_id, f.fingerprint, f.severity, f.encounter_id)
        for f in open_flags(session) if f.rule_id != "missed_follow_up"
    }
    assert med_flags == {
        (1, "drug_interaction", "ibuprofen|warfarin", Severity.HIGH, 1),
        (2, "drug_interaction", "sertraline|tramadol", Severity.HIGH, 2),
        (3, "drug_interaction", "lisinopril|spironolactone", Severity.MODERATE, 3),
        (4, "drug_interaction", "clarithromycin|simvastatin", Severity.HIGH, 4),
        (5, "allergy_conflict", "penicillin|amoxicillin", Severity.HIGH, 5),
        (7, "duplicate_therapy", "NSAID|ibuprofen|naproxen", Severity.MODERATE, 7),
    }


def test_flag_details_record_where_each_drug_came_from(session):
    add_med_entities(session, 1, [("ibuprofen", "start")])
    [finding] = [f for f in evaluate_patient(session, session.get(models.Patient, 1), TODAY)
                 if f.rule_id == "drug_interaction"]
    sources = {d["name"]: d["source"] for d in finding.details["drugs"]}
    assert sources == {"ibuprofen": "ai", "warfarin": "ehr"}


def test_no_med_flags_without_extraction(session):
    run_rules(session, today=TODAY)
    assert {f.rule_id for f in open_flags(session)} == {"missed_follow_up"}


def test_missed_follow_ups_and_severity(session):
    run_rules(session, today=TODAY)
    by_desc = {f.details["follow_up_id"]: f for f in open_flags(session, rule_id="missed_follow_up")}
    follow_ups = {f.id: f for f in session.scalars(select(models.FollowUp))}
    overdue = {i for i, f in follow_ups.items() if f.completed_at is None and f.due_date < TODAY}
    assert set(by_desc) == overdue

    def severity_for(desc):
        [f] = [f for f in by_desc.values() if follow_ups[f.details["follow_up_id"]].description == desc]
        return f.severity
    assert severity_for("Recheck INR") == Severity.LOW           # 5 days
    assert severity_for("BMP (potassium, creatinine)") == Severity.MODERATE  # 13 days
    assert severity_for("Exercise stress test") == Severity.HIGH  # 46 days


def test_rerun_is_idempotent(session):
    add_med_entities(session, 1, [("ibuprofen", "start")])
    first = run_rules(session, today=TODAY)
    second = run_rules(session, today=TODAY)
    assert first.created > 0
    assert (second.created, second.updated, second.auto_resolved) == (0, 0, 0)


def test_rejecting_suggestion_auto_resolves_flag(session):
    s = add_med_entities(session, 1, [("ibuprofen", "start")])
    run_rules(session, patient_id=1, today=TODAY)
    assert open_flags(session, 1, "drug_interaction")

    for e in s.entities:
        e.review_status = ReviewStatus.REJECTED
    session.commit()
    assert run_rules(session, patient_id=1, today=TODAY).auto_resolved == 1
    [flag] = session.scalars(select(models.AnomalyFlag).where(models.AnomalyFlag.rule_id == "drug_interaction"))
    assert flag.resolution == "auto_cleared" and flag.resolved_by is None


def test_provider_resolved_flag_is_not_reraised(session):
    add_med_entities(session, 1, [("ibuprofen", "start")])
    run_rules(session, patient_id=1, today=TODAY)
    [flag] = open_flags(session, 1, "drug_interaction")
    flag.resolved_at, flag.resolved_by, flag.resolution = utcnow(), 2, "provider"
    session.commit()
    assert run_rules(session, patient_id=1, today=TODAY).created == 0


def test_completed_follow_up_clears_flag(session):
    run_rules(session, patient_id=1, today=TODAY)
    [flag] = open_flags(session, 1, "missed_follow_up")
    session.get(models.FollowUp, flag.details["follow_up_id"]).completed_at = utcnow()
    session.commit()
    assert run_rules(session, patient_id=1, today=TODAY).auto_resolved == 1


def test_severity_escalates_as_follow_up_ages(session):
    run_rules(session, patient_id=1, today=TODAY)
    [flag] = open_flags(session, 1, "missed_follow_up")
    assert flag.severity == Severity.LOW
    assert run_rules(session, patient_id=1, today=TODAY + timedelta(days=40)).updated == 1
    assert open_flags(session, 1, "missed_follow_up")[0].severity == Severity.HIGH


def test_stop_action_removes_ehr_medication(session):
    add_med_entities(session, 1, [("warfarin", "stop"), ("ibuprofen", "start")])
    assert set(current_medications(session, 1)) == {"metoprolol", "ibuprofen"}
    run_rules(session, patient_id=1, today=TODAY)
    assert not open_flags(session, 1, "drug_interaction")


def test_mentioned_only_medication_is_ignored(session):
    add_med_entities(session, 1, [("ibuprofen", "mentioned")])
    assert "ibuprofen" not in current_medications(session, 1)


def test_rules_endpoint(client):
    r = client.post("/api/rules/run")
    assert r.status_code == 200 and r.json()["created"] >= 5
    assert client.post("/api/rules/run", params={"patient_id": 1}).json() == {"created": 0, "updated": 0, "auto_resolved": 0}
    assert client.post("/api/rules/run", params={"patient_id": 999}).status_code == 404
    assert {f["flag_type"] for f in client.get("/api/flags").json()} == {"missed_follow_up"}


def test_extraction_runs_rules(client):
    import json
    from app.ai.deps import get_llm, get_retriever
    from app.ai.retrieval import KeywordRetriever
    from app.main import app
    from tests.test_extraction import ENCOUNTER_1_OUTPUT, FakeLLM

    app.dependency_overrides[get_llm] = lambda: FakeLLM(json.dumps(ENCOUNTER_1_OUTPUT))
    app.dependency_overrides[get_retriever] = KeywordRetriever
    assert client.post("/api/encounters/1/extract").status_code == 201
    flags = client.get("/api/encounters/1").json()["flags"]
    assert {f["message"].split(":")[0] for f in flags if f["flag_type"] == "med_interaction"} == {"ibuprofen + warfarin"}
