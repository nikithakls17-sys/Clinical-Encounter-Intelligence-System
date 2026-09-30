"""Database schema.

Tables fall into four groups:
  * core clinical data   - providers, patients, allergies, encounters, patient_medications, follow_ups
  * AI output            - ai_suggestions (audit log of every model call), extracted_entities
  * rule engine output   - anomaly_flags
  * reference data       - icd10_codes, drug_interactions (used for RAG retrieval and rules)

All data in this project is synthetic. Never load real patient data (PHI).
"""

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# JSONB on Postgres, plain JSON elsewhere (SQLite in tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class EncounterStatus(str, enum.Enum):
    PENDING = "pending"  # note captured, not yet processed by AI
    EXTRACTED = "extracted"  # AI suggestions exist, awaiting review
    REVIEWED = "reviewed"  # provider has reviewed every suggestion


class EntityType(str, enum.Enum):
    SYMPTOM = "symptom"
    MEDICATION = "medication"
    DIAGNOSIS = "diagnosis"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"  # replaced by a newer extraction before review


class FlagType(str, enum.Enum):
    MED_INTERACTION = "med_interaction"
    DUPLICATE_THERAPY = "duplicate_therapy"
    ALLERGY_CONFLICT = "allergy_conflict"
    MISSED_FOLLOW_UP = "missed_follow_up"


class Severity(str, enum.Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


# --------------------------------------------------------------------------- core


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    specialty: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(160), unique=True)

    encounters: Mapped[list["Encounter"]] = relationship(back_populates="provider")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    mrn: Mapped[str] = mapped_column(String(20), unique=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    date_of_birth: Mapped[date] = mapped_column(Date)
    sex: Mapped[str] = mapped_column(String(1))

    allergies: Mapped[list["Allergy"]] = relationship(back_populates="patient")
    encounters: Mapped[list["Encounter"]] = relationship(back_populates="patient")
    medications: Mapped[list["PatientMedication"]] = relationship(back_populates="patient")

    __table_args__ = (CheckConstraint("sex IN ('F', 'M', 'X')", name="ck_patients_sex"),)


class Allergy(Base):
    __tablename__ = "allergies"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))
    substance: Mapped[str] = mapped_column(String(120))
    reaction: Mapped[str | None] = mapped_column(String(200))

    patient: Mapped[Patient] = relationship(back_populates="allergies")


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"))
    encounter_date: Mapped[date] = mapped_column(Date)
    encounter_type: Mapped[str] = mapped_column(String(40))  # office visit, telehealth, ED, ...
    chief_complaint: Mapped[str | None] = mapped_column(String(200))
    note_text: Mapped[str] = mapped_column(Text)
    status: Mapped[EncounterStatus] = mapped_column(
        _enum(EncounterStatus, "encounter_status"), default=EncounterStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    patient: Mapped[Patient] = relationship(back_populates="encounters")
    provider: Mapped[Provider] = relationship(back_populates="encounters")
    entities: Mapped[list["ExtractedEntity"]] = relationship(back_populates="encounter")
    suggestions: Mapped[list["AISuggestion"]] = relationship(back_populates="encounter")
    follow_ups: Mapped[list["FollowUp"]] = relationship(back_populates="encounter")

    __table_args__ = (Index("ix_encounters_patient_date", "patient_id", "encounter_date"),)


class PatientMedication(Base):
    """Medication list per patient. Rows can come from the seed/EHR or from an accepted AI extraction."""

    __tablename__ = "patient_medications"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))
    encounter_id: Mapped[int | None] = mapped_column(ForeignKey("encounters.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120))  # generic name, lowercase
    drug_class: Mapped[str | None] = mapped_column(String(80))
    dose: Mapped[str | None] = mapped_column(String(40))
    frequency: Mapped[str | None] = mapped_column(String(40))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    patient: Mapped[Patient] = relationship(back_populates="medications")

    __table_args__ = (Index("ix_patient_medications_active", "patient_id", "active"),)


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[int] = mapped_column(primary_key=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.id", ondelete="CASCADE"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[date] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    encounter: Mapped[Encounter] = relationship(back_populates="follow_ups")
    patient: Mapped[Patient] = relationship()

    __table_args__ = (Index("ix_follow_ups_open", "patient_id", "due_date"),)


# ---------------------------------------------------------------------- AI output


class AISuggestion(Base):
    """Audit log: one row per model call. Rows are never updated except for the review fields."""

    __tablename__ = "ai_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(40))
    input_sha256: Mapped[str] = mapped_column(String(64))  # hash of the exact prompt sent
    retrieved_context: Mapped[list | None] = mapped_column(JSONType)  # RAG chunks given to the model
    raw_output: Mapped[str] = mapped_column(Text)  # verbatim model response
    parsed_output: Mapped[dict | None] = mapped_column(JSONType)  # validated structure, null if parse failed
    error: Mapped[str | None] = mapped_column(Text)  # API or parse failure; failed calls are logged too
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Human review
    review_status: Mapped[ReviewStatus] = mapped_column(
        _enum(ReviewStatus, "review_status"), default=ReviewStatus.PENDING
    )
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("providers.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_output: Mapped[dict | None] = mapped_column(JSONType)  # what the provider actually signed off on
    reviewer_note: Mapped[str | None] = mapped_column(Text)

    encounter: Mapped[Encounter] = relationship(back_populates="suggestions")
    entities: Mapped[list["ExtractedEntity"]] = relationship(back_populates="suggestion")

    __table_args__ = (Index("ix_ai_suggestions_review", "review_status", "created_at"),)


class ExtractedEntity(Base):
    __tablename__ = "extracted_entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.id", ondelete="CASCADE"))
    suggestion_id: Mapped[int] = mapped_column(ForeignKey("ai_suggestions.id", ondelete="CASCADE"))
    entity_type: Mapped[EntityType] = mapped_column(_enum(EntityType, "entity_type"))
    text: Mapped[str] = mapped_column(String(200))  # as written in the note
    normalized: Mapped[str | None] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(20))  # ICD-10 for diagnoses
    attributes: Mapped[dict | None] = mapped_column(JSONType)  # dose, frequency, severity, ...
    confidence: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[ReviewStatus] = mapped_column(
        _enum(ReviewStatus, "review_status"), default=ReviewStatus.PENDING
    )

    encounter: Mapped[Encounter] = relationship(back_populates="entities")
    suggestion: Mapped[AISuggestion] = relationship(back_populates="entities")


# -------------------------------------------------------------------- rule engine


class AnomalyFlag(Base):
    __tablename__ = "anomaly_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))
    encounter_id: Mapped[int | None] = mapped_column(ForeignKey("encounters.id", ondelete="CASCADE"))
    flag_type: Mapped[FlagType] = mapped_column(_enum(FlagType, "flag_type"))
    severity: Mapped[Severity] = mapped_column(_enum(Severity, "severity"))
    rule_id: Mapped[str] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(String(300))
    details: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("providers.id"))

    __table_args__ = (Index("ix_anomaly_flags_open", "patient_id", "resolved_at"),)


# ------------------------------------------------------------------ reference data


class ICD10Code(Base):
    __tablename__ = "icd10_codes"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    description: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(80))


class ReferenceEmbedding(Base):
    """Cached embedding vectors for reference documents used in retrieval."""

    __tablename__ = "reference_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40))  # e.g. "icd10"
    ref_id: Mapped[str] = mapped_column(String(40))  # e.g. the ICD-10 code
    model: Mapped[str] = mapped_column(String(80))
    content_sha256: Mapped[str] = mapped_column(String(64))  # re-embed when the text changes
    vector: Mapped[list] = mapped_column(JSONType)

    __table_args__ = (UniqueConstraint("source", "ref_id", "model", name="uq_reference_embeddings"),)


class DrugInteraction(Base):
    __tablename__ = "drug_interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stored in alphabetical order so each pair appears once.
    drug_a: Mapped[str] = mapped_column(String(120))
    drug_b: Mapped[str] = mapped_column(String(120))
    severity: Mapped[Severity] = mapped_column(_enum(Severity, "severity"))
    description: Mapped[str] = mapped_column(String(300))

    __table_args__ = (
        UniqueConstraint("drug_a", "drug_b", name="uq_drug_interactions_pair"),
        CheckConstraint("drug_a < drug_b", name="ck_drug_interactions_order"),
    )
