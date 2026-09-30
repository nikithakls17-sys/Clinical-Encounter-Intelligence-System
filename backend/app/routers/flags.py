from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_session
from app.models import utcnow

router = APIRouter(prefix="/flags", tags=["flags"])


@router.get("", response_model=list[schemas.FlagOut])
def list_flags(
    resolved: bool = False,
    severity: models.Severity | None = None,
    flag_type: models.FlagType | None = None,
    patient_id: int | None = None,
    session: Session = Depends(get_session),
):
    stmt = select(models.AnomalyFlag).order_by(models.AnomalyFlag.created_at.desc())
    stmt = stmt.where(
        models.AnomalyFlag.resolved_at.is_not(None) if resolved else models.AnomalyFlag.resolved_at.is_(None)
    )
    if severity:
        stmt = stmt.where(models.AnomalyFlag.severity == severity)
    if flag_type:
        stmt = stmt.where(models.AnomalyFlag.flag_type == flag_type)
    if patient_id:
        stmt = stmt.where(models.AnomalyFlag.patient_id == patient_id)
    return session.scalars(stmt).all()


@router.post("/{flag_id}/resolve", response_model=schemas.FlagOut)
def resolve_flag(flag_id: int, body: schemas.FlagResolve, session: Session = Depends(get_session)):
    flag = session.get(models.AnomalyFlag, flag_id)
    if flag is None:
        raise HTTPException(404, "Flag not found")
    if flag.resolved_at is not None:
        raise HTTPException(409, "Flag already resolved")
    if session.get(models.Provider, body.provider_id) is None:
        raise HTTPException(422, "Unknown provider_id")
    flag.resolved_at = utcnow()
    flag.resolved_by = body.provider_id
    session.commit()
    return flag
