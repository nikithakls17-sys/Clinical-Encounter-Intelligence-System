from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_session

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _count(session: Session, stmt) -> int:
    return session.scalar(select(func.count()).select_from(stmt.subquery())) or 0


@router.get("/summary", response_model=schemas.DashboardSummary)
def summary(session: Session = Depends(get_session)):
    E = models.Encounter
    flag_rows = session.execute(
        select(models.AnomalyFlag.severity, func.count())
        .where(models.AnomalyFlag.resolved_at.is_(None))
        .group_by(models.AnomalyFlag.severity)
    ).all()
    review_rows = session.execute(
        select(models.AISuggestion.review_status, func.count()).group_by(models.AISuggestion.review_status)
    ).all()
    return schemas.DashboardSummary(
        patients=_count(session, select(models.Patient.id)),
        encounters_pending_extraction=_count(session, select(E.id).where(E.status == models.EncounterStatus.PENDING)),
        encounters_awaiting_review=_count(session, select(E.id).where(E.status == models.EncounterStatus.EXTRACTED)),
        open_flags={s: 0 for s in models.Severity} | dict(flag_rows),
        overdue_follow_ups=_count(
            session,
            select(models.FollowUp.id).where(
                models.FollowUp.due_date < date.today(), models.FollowUp.completed_at.is_(None)
            ),
        ),
        suggestions_by_review_status={s: 0 for s in models.ReviewStatus} | dict(review_rows),
    )
