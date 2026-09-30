"""Read access to the AI suggestion audit log. Review (accept/edit/reject) is added in a later stage."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.db import get_session

router = APIRouter(prefix="/suggestions", tags=["audit log"])


@router.get("", response_model=list[schemas.SuggestionSummary])
def list_suggestions(
    review_status: models.ReviewStatus | None = None,
    encounter_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    stmt = (
        select(models.AISuggestion)
        .order_by(models.AISuggestion.created_at.desc(), models.AISuggestion.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if review_status:
        stmt = stmt.where(models.AISuggestion.review_status == review_status)
    if encounter_id:
        stmt = stmt.where(models.AISuggestion.encounter_id == encounter_id)
    return session.scalars(stmt).all()


@router.get("/{suggestion_id}", response_model=schemas.SuggestionDetail)
def get_suggestion(suggestion_id: int, session: Session = Depends(get_session)):
    s = session.get(models.AISuggestion, suggestion_id, options=[selectinload(models.AISuggestion.entities)])
    if s is None:
        raise HTTPException(404, "Suggestion not found")
    return s
