"""API response and request models."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import EncounterStatus, EntityType, FlagType, ReviewStatus, Severity


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ clinical


class ProviderOut(ORM):
    id: int
    name: str
    specialty: str


class AllergyOut(ORM):
    substance: str
    reaction: str | None


class MedicationOut(ORM):
    id: int
    name: str
    drug_class: str | None
    dose: str | None
    frequency: str | None
    start_date: date | None
    end_date: date | None
    active: bool


class FollowUpOut(ORM):
    id: int
    encounter_id: int
    description: str
    due_date: date
    completed_at: datetime | None


class PatientSummary(ORM):
    id: int
    mrn: str
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    open_flag_count: int = 0
    last_encounter_date: date | None = None


class EncounterSummary(ORM):
    id: int
    patient_id: int
    patient_name: str
    provider: ProviderOut
    encounter_date: date
    encounter_type: str
    chief_complaint: str | None
    status: EncounterStatus


class PatientDetail(PatientSummary):
    allergies: list[AllergyOut]
    medications: list[MedicationOut]
    follow_ups: list[FollowUpOut]
    encounters: list[EncounterSummary]


class EncounterCreate(BaseModel):
    patient_id: int
    provider_id: int
    encounter_date: date
    encounter_type: str = Field(min_length=1, max_length=40)
    chief_complaint: str | None = Field(default=None, max_length=200)
    note_text: str = Field(min_length=1)


# --------------------------------------------------------------------- AI


class EntityOut(ORM):
    id: int
    entity_type: EntityType
    text: str
    normalized: str | None
    code: str | None
    attributes: dict | None
    confidence: float | None
    review_status: ReviewStatus


class SuggestionSummary(ORM):
    id: int
    encounter_id: int
    model: str
    prompt_version: str
    created_at: datetime
    latency_ms: int | None
    review_status: ReviewStatus
    reviewed_by: int | None
    reviewed_at: datetime | None


class SuggestionDetail(SuggestionSummary):
    input_sha256: str
    retrieved_context: list | None
    raw_output: str
    parsed_output: dict | None
    error: str | None
    final_output: dict | None
    reviewer_note: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    entities: list[EntityOut]


# ------------------------------------------------------------------ rules


class FlagOut(ORM):
    id: int
    patient_id: int
    encounter_id: int | None
    flag_type: FlagType
    severity: Severity
    rule_id: str
    message: str
    details: dict | None
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: int | None


class FlagResolve(BaseModel):
    provider_id: int


class EncounterDetail(EncounterSummary):
    note_text: str
    entities: list[EntityOut]
    suggestions: list[SuggestionSummary]
    follow_ups: list[FollowUpOut]
    flags: list[FlagOut]


# -------------------------------------------------------------- dashboard


class DashboardSummary(BaseModel):
    patients: int
    encounters_pending_extraction: int
    encounters_awaiting_review: int
    open_flags: dict[Severity, int]
    overdue_follow_ups: int
    suggestions_by_review_status: dict[ReviewStatus, int]
