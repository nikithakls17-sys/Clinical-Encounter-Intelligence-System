import re
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import models
from app.db import Base
from app.seed import data
from app.seed.seed import load

TODAY = date(2026, 9, 30)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        load(s, today=TODAY)
        yield s


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
