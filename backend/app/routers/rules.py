from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.db import get_session
from app.rules.engine import run_rules

router = APIRouter(prefix="/rules", tags=["flags"])


class RuleRunResult(BaseModel):
    created: int
    updated: int
    auto_resolved: int


@router.post("/run", response_model=RuleRunResult)
def run(patient_id: int | None = None, session: Session = Depends(get_session)):
    """Re-evaluate anomaly rules for one patient, or everyone if patient_id is omitted."""
    if patient_id is not None and session.get(models.Patient, patient_id) is None:
        raise HTTPException(404, "Patient not found")
    return asdict(run_rules(session, patient_id))
