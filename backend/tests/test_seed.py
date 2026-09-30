import re

from sqlalchemy import select

from app import models
from app.seed import data
from tests.conftest import TODAY


def test_row_counts(session):
    assert len(session.scalars(select(models.Patient)).all()) == len(data.PATIENTS)
    assert len(session.scalars(select(models.Encounter)).all()) == len(data.ENCOUNTERS)
    assert len(session.scalars(select(models.ICD10Code)).all()) == len(data.ICD10_CODES)
    assert len(session.scalars(select(models.DrugInteraction)).all()) == len(data.DRUG_INTERACTIONS)


def test_encounters_start_pending(session):
    statuses = set(session.scalars(select(models.Encounter.status)))
    assert statuses == {models.EncounterStatus.PENDING}


def test_drug_pairs_are_sorted(session):
    for row in session.scalars(select(models.DrugInteraction)):
        assert row.drug_a < row.drug_b


def test_icd10_codes_in_notes_exist_in_reference_table(session):
    known = set(session.scalars(select(models.ICD10Code.code)))
    for e in data.ENCOUNTERS:
        codes = set(re.findall(r"\(([A-Z]\d{2}(?:\.\d{1,4})?)\)", e["note"]))
        assert codes and codes <= known, e["mrn"]


def test_seed_contains_missed_follow_ups(session):
    overdue = session.scalars(
        select(models.FollowUp).where(models.FollowUp.due_date < TODAY, models.FollowUp.completed_at.is_(None))
    ).all()
    assert len(overdue) >= 5
