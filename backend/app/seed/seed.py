"""Create the schema and load synthetic seed data.

Usage (from backend/):
    python -m app.seed.seed            # create tables if missing, load data if the DB is empty
    python -m app.seed.seed --reset    # drop all tables first
"""

import argparse
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import models
from app.db import Base, engine as default_engine
from app.seed import data


def _days(offset: int, today: date) -> date:
    return today + timedelta(days=offset)


def load(session: Session, today: date | None = None) -> None:
    today = today or date.today()

    session.add_all(models.ICD10Code(code=c, description=d, category=cat) for c, d, cat in data.ICD10_CODES)
    for a, b, severity, description in data.DRUG_INTERACTIONS:
        a, b = sorted((a, b))
        session.add(models.DrugInteraction(drug_a=a, drug_b=b, severity=models.Severity(severity), description=description))

    providers = {p["email"]: models.Provider(**p) for p in data.PROVIDERS}
    session.add_all(providers.values())

    patients: dict[str, models.Patient] = {}
    for p in data.PATIENTS:
        patient = models.Patient(
            mrn=p["mrn"],
            first_name=p["first_name"],
            last_name=p["last_name"],
            date_of_birth=date.fromisoformat(p["date_of_birth"]),
            sex=p["sex"],
            allergies=[models.Allergy(substance=s, reaction=r) for s, r in p["allergies"]],
        )
        patients[p["mrn"]] = patient
    session.add_all(patients.values())

    for mrn, name, drug_class, dose, freq, start in data.MEDICATIONS:
        session.add(
            models.PatientMedication(
                patient=patients[mrn], name=name, drug_class=drug_class, dose=dose, frequency=freq,
                start_date=_days(start, today), active=True,
            )
        )

    for e in data.ENCOUNTERS:
        patient = patients[e["mrn"]]
        encounter_date = _days(e["offset"], today)
        encounter = models.Encounter(
            patient=patient,
            provider=providers[e["provider"]],
            encounter_date=encounter_date,
            encounter_type=e["type"],
            chief_complaint=e["chief_complaint"],
            note_text=e["note"],
            status=models.EncounterStatus.PENDING,
            created_at=datetime.combine(encounter_date, time(9, 0), tzinfo=timezone.utc),
        )
        session.add(encounter)
        for description, due, completed in e["follow_ups"]:
            due_date = _days(due, today)
            session.add(
                models.FollowUp(
                    encounter=encounter,
                    patient=patient,
                    description=description,
                    due_date=due_date,
                    completed_at=datetime.combine(due_date, time(12, 0), tzinfo=timezone.utc) if completed else None,
                )
            )

    session.commit()


def run(engine: Engine, reset: bool = False) -> None:
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        if session.scalar(select(func.count()).select_from(models.Patient)):
            print("Database already has data; use --reset to reload.")
            return
        load(session)
        counts = {
            t: session.scalar(select(func.count()).select_from(m))
            for t, m in [("patients", models.Patient), ("encounters", models.Encounter),
                         ("medications", models.PatientMedication), ("follow_ups", models.FollowUp),
                         ("icd10_codes", models.ICD10Code), ("drug_interactions", models.DrugInteraction)]
        }
        print("Seeded:", ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="drop all tables before seeding")
    run(default_engine, reset=parser.parse_args().reset)
