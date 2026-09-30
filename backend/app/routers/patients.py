from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.db import get_session
from app.routers.encounters import encounter_summary

router = APIRouter(prefix="/patients", tags=["patients"])


def _open_flag_counts(session: Session) -> dict[int, int]:
    rows = session.execute(
        select(models.AnomalyFlag.patient_id, func.count())
        .where(models.AnomalyFlag.resolved_at.is_(None))
        .group_by(models.AnomalyFlag.patient_id)
    )
    return dict(rows.all())


def _last_encounter_dates(session: Session) -> dict[int, object]:
    rows = session.execute(
        select(models.Encounter.patient_id, func.max(models.Encounter.encounter_date)).group_by(
            models.Encounter.patient_id
        )
    )
    return dict(rows.all())


@router.get("", response_model=list[schemas.PatientSummary])
def list_patients(
    q: str | None = Query(default=None, description="Search by name or MRN"),
    session: Session = Depends(get_session),
):
    stmt = select(models.Patient).order_by(models.Patient.last_name, models.Patient.first_name)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(models.Patient.first_name).like(like),
                func.lower(models.Patient.last_name).like(like),
                func.lower(models.Patient.mrn).like(like),
            )
        )
    flags = _open_flag_counts(session)
    last = _last_encounter_dates(session)
    return [
        schemas.PatientSummary.model_validate(p).model_copy(
            update={"open_flag_count": flags.get(p.id, 0), "last_encounter_date": last.get(p.id)}
        )
        for p in session.scalars(stmt)
    ]


@router.get("/{patient_id}", response_model=schemas.PatientDetail)
def get_patient(patient_id: int, session: Session = Depends(get_session)):
    patient = session.get(
        models.Patient,
        patient_id,
        options=[
            selectinload(models.Patient.allergies),
            selectinload(models.Patient.medications),
            selectinload(models.Patient.encounters).selectinload(models.Encounter.provider),
        ],
    )
    if patient is None:
        raise HTTPException(404, "Patient not found")

    follow_ups = session.scalars(
        select(models.FollowUp).where(models.FollowUp.patient_id == patient_id).order_by(models.FollowUp.due_date)
    ).all()
    encounters = sorted(patient.encounters, key=lambda e: e.encounter_date, reverse=True)

    return schemas.PatientDetail(
        **schemas.PatientSummary.model_validate(patient).model_dump(),
        allergies=patient.allergies,
        medications=sorted(patient.medications, key=lambda m: (not m.active, m.name)),
        follow_ups=follow_ups,
        encounters=[encounter_summary(e) for e in encounters],
    ).model_copy(
        update={
            "open_flag_count": _open_flag_counts(session).get(patient_id, 0),
            "last_encounter_date": encounters[0].encounter_date if encounters else None,
        }
    )
