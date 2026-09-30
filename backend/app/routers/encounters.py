from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.db import get_session

router = APIRouter(prefix="/encounters", tags=["encounters"])


def encounter_summary(e: models.Encounter) -> schemas.EncounterSummary:
    return schemas.EncounterSummary(
        id=e.id,
        patient_id=e.patient_id,
        patient_name=f"{e.patient.first_name} {e.patient.last_name}",
        provider=schemas.ProviderOut.model_validate(e.provider),
        encounter_date=e.encounter_date,
        encounter_type=e.encounter_type,
        chief_complaint=e.chief_complaint,
        status=e.status,
    )


@router.get("", response_model=list[schemas.EncounterSummary])
def list_encounters(
    status: models.EncounterStatus | None = None,
    patient_id: int | None = None,
    provider_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    stmt = (
        select(models.Encounter)
        .options(selectinload(models.Encounter.patient), selectinload(models.Encounter.provider))
        .order_by(models.Encounter.encounter_date.desc(), models.Encounter.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        stmt = stmt.where(models.Encounter.status == status)
    if patient_id:
        stmt = stmt.where(models.Encounter.patient_id == patient_id)
    if provider_id:
        stmt = stmt.where(models.Encounter.provider_id == provider_id)
    return [encounter_summary(e) for e in session.scalars(stmt)]


@router.get("/{encounter_id}", response_model=schemas.EncounterDetail)
def get_encounter(encounter_id: int, session: Session = Depends(get_session)):
    e = session.get(
        models.Encounter,
        encounter_id,
        options=[
            selectinload(models.Encounter.patient),
            selectinload(models.Encounter.provider),
            selectinload(models.Encounter.entities),
            selectinload(models.Encounter.suggestions),
            selectinload(models.Encounter.follow_ups),
        ],
    )
    if e is None:
        raise HTTPException(404, "Encounter not found")
    flags = session.scalars(
        select(models.AnomalyFlag)
        .where(models.AnomalyFlag.encounter_id == encounter_id)
        .order_by(models.AnomalyFlag.created_at.desc())
    ).all()
    return schemas.EncounterDetail(
        **encounter_summary(e).model_dump(),
        note_text=e.note_text,
        entities=e.entities,
        suggestions=sorted(e.suggestions, key=lambda s: s.created_at, reverse=True),
        follow_ups=sorted(e.follow_ups, key=lambda f: f.due_date),
        flags=flags,
    )


@router.post("", response_model=schemas.EncounterDetail, status_code=201)
def create_encounter(body: schemas.EncounterCreate, session: Session = Depends(get_session)):
    if session.get(models.Patient, body.patient_id) is None:
        raise HTTPException(422, "Unknown patient_id")
    if session.get(models.Provider, body.provider_id) is None:
        raise HTTPException(422, "Unknown provider_id")
    encounter = models.Encounter(**body.model_dump(), status=models.EncounterStatus.PENDING)
    session.add(encounter)
    session.commit()
    return get_encounter(encounter.id, session)
