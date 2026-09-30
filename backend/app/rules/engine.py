"""Rule-based anomaly detection.

The engine builds each patient's current medication list from two sources:
  * the EHR list (patient_medications, active rows)
  * AI-extracted medication entities that are pending, accepted or edited, i.e. not rejected or superseded.
    Their "action" attribute adds (start/continue/change) or removes (stop) a drug.

Including pending AI output is deliberate: the reviewer sees "accepting this creates a conflict" before signing off.
Each flag records which source every drug came from.

Rules: drug-drug interaction, allergy conflict, duplicate therapy, missed follow-up.

Flags are synced, not appended. A condition that still holds keeps its existing flag. A condition that went away
(suggestion rejected, follow-up completed) auto-resolves its flag. A flag a provider resolved is never re-raised
for the same condition.
"""

from dataclasses import dataclass, field
from datetime import date
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.models import FlagType, ReviewStatus, Severity, utcnow
from app.rules.reference import DUPLICATE_GROUPS, allergy_matches

ACTIVE_ENTITY_STATUSES = (ReviewStatus.PENDING, ReviewStatus.ACCEPTED, ReviewStatus.EDITED)


@dataclass
class Med:
    name: str
    source: str  # "ehr" or "ai"
    encounter_id: int | None = None
    entity_id: int | None = None

    def describe(self) -> dict:
        return {k: v for k, v in vars(self).items() if v is not None}


@dataclass
class Finding:
    rule_id: str
    flag_type: FlagType
    severity: Severity
    fingerprint: str
    message: str
    encounter_id: int | None = None
    details: dict = field(default_factory=dict)


# ------------------------------------------------------------------ med list


def current_medications(session: Session, patient_id: int) -> dict[str, Med]:
    meds: dict[str, Med] = {
        m.name.lower(): Med(m.name.lower(), "ehr", m.encounter_id)
        for m in session.scalars(
            select(models.PatientMedication).where(
                models.PatientMedication.patient_id == patient_id, models.PatientMedication.active.is_(True)
            )
        )
    }
    entities = session.scalars(
        select(models.ExtractedEntity)
        .join(models.Encounter)
        .where(
            models.Encounter.patient_id == patient_id,
            models.ExtractedEntity.entity_type == models.EntityType.MEDICATION,
            models.ExtractedEntity.review_status.in_(ACTIVE_ENTITY_STATUSES),
        )
        .order_by(models.Encounter.encounter_date, models.ExtractedEntity.id)
    )
    for e in entities:
        name = (e.normalized or e.text).lower().strip()
        action = (e.attributes or {}).get("action")
        if action == "stop":
            meds.pop(name, None)
        elif action in ("start", "continue", "change") and name not in meds:
            meds[name] = Med(name, "ai", e.encounter_id, e.id)
    return meds


def _encounter_of(*meds: Med) -> int | None:
    # Attach the flag to the encounter that introduced the newest drug, if an AI extraction did.
    return max((m.encounter_id for m in meds if m.source == "ai" and m.encounter_id), default=None)


# --------------------------------------------------------------------- rules


def interaction_rule(session: Session, meds: dict[str, Med]) -> list[Finding]:
    if len(meds) < 2:
        return []
    names = sorted(meds)
    table = {
        (i.drug_a, i.drug_b): i
        for i in session.scalars(
            select(models.DrugInteraction).where(
                models.DrugInteraction.drug_a.in_(names), models.DrugInteraction.drug_b.in_(names)
            )
        )
    }
    out = []
    for a, b in combinations(names, 2):
        if (hit := table.get((a, b))) is None:
            continue
        out.append(Finding(
            rule_id="drug_interaction", flag_type=FlagType.MED_INTERACTION, severity=hit.severity,
            fingerprint=f"{a}|{b}", message=f"{a} + {b}: {hit.description}",
            encounter_id=_encounter_of(meds[a], meds[b]),
            details={"drugs": [meds[a].describe(), meds[b].describe()], "interaction_id": hit.id},
        ))
    return out


def allergy_rule(patient: models.Patient, meds: dict[str, Med]) -> list[Finding]:
    out = []
    for allergy in patient.allergies:
        for name, med in meds.items():
            if allergy_matches(allergy.substance, name):
                reaction = f" (reaction: {allergy.reaction})" if allergy.reaction else ""
                out.append(Finding(
                    rule_id="allergy_conflict", flag_type=FlagType.ALLERGY_CONFLICT, severity=Severity.HIGH,
                    fingerprint=f"{allergy.substance.lower()}|{name}",
                    message=f"{name.title()} prescribed despite documented {allergy.substance} allergy{reaction}.",
                    encounter_id=_encounter_of(med),
                    details={"allergy": allergy.substance, "reaction": allergy.reaction, "drug": med.describe()},
                ))
    return out


def duplicate_therapy_rule(meds: dict[str, Med]) -> list[Finding]:
    groups: dict[str, list[Med]] = {}
    for name, med in meds.items():
        if group := DUPLICATE_GROUPS.get(name):
            groups.setdefault(group, []).append(med)
    out = []
    for group, members in groups.items():
        if len(members) < 2:
            continue
        names = sorted(m.name for m in members)
        out.append(Finding(
            rule_id="duplicate_therapy", flag_type=FlagType.DUPLICATE_THERAPY, severity=Severity.MODERATE,
            fingerprint=f"{group}|{'|'.join(names)}",
            message=f"Duplicate {group} therapy: {', '.join(names)}.",
            encounter_id=_encounter_of(*members),
            details={"group": group, "drugs": [m.describe() for m in members]},
        ))
    return out


def missed_follow_up_rule(session: Session, patient_id: int, today: date) -> list[Finding]:
    overdue = session.scalars(
        select(models.FollowUp).where(
            models.FollowUp.patient_id == patient_id,
            models.FollowUp.completed_at.is_(None),
            models.FollowUp.due_date < today,
        )
    )
    out = []
    for f in overdue:
        days = (today - f.due_date).days
        severity = Severity.HIGH if days > 30 else Severity.MODERATE if days > 7 else Severity.LOW
        out.append(Finding(
            rule_id="missed_follow_up", flag_type=FlagType.MISSED_FOLLOW_UP, severity=severity,
            fingerprint=f"follow_up:{f.id}",
            message=f"{f.description} was due {f.due_date.isoformat()} and has not been completed.",
            encounter_id=f.encounter_id,
            details={"follow_up_id": f.id, "due_date": f.due_date.isoformat(), "days_overdue": days},
        ))
    return out


def evaluate_patient(session: Session, patient: models.Patient, today: date | None = None) -> list[Finding]:
    today = today or date.today()
    meds = current_medications(session, patient.id)
    return (
        interaction_rule(session, meds)
        + allergy_rule(patient, meds)
        + duplicate_therapy_rule(meds)
        + missed_follow_up_rule(session, patient.id, today)
    )


# ---------------------------------------------------------------------- sync


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    auto_resolved: int = 0

    def __iadd__(self, other: "SyncResult") -> "SyncResult":
        self.created += other.created
        self.updated += other.updated
        self.auto_resolved += other.auto_resolved
        return self


def sync_patient_flags(session: Session, patient: models.Patient, today: date | None = None) -> SyncResult:
    findings = {(f.rule_id, f.fingerprint): f for f in evaluate_patient(session, patient, today)}
    existing = session.scalars(select(models.AnomalyFlag).where(models.AnomalyFlag.patient_id == patient.id)).all()
    result = SyncResult()

    open_flags = {(f.rule_id, f.fingerprint): f for f in existing if f.resolved_at is None}
    provider_closed = {(f.rule_id, f.fingerprint) for f in existing if f.resolution == "provider"}

    for key, flag in open_flags.items():
        if key not in findings:
            flag.resolved_at = utcnow()
            flag.resolution = "auto_cleared"
            result.auto_resolved += 1

    for key, f in findings.items():
        if key in provider_closed:
            continue
        if (flag := open_flags.get(key)) is not None:
            if (flag.severity, flag.message, flag.details) != (f.severity, f.message, f.details):
                flag.severity, flag.message, flag.details = f.severity, f.message, f.details
                result.updated += 1
            continue
        session.add(models.AnomalyFlag(
            patient_id=patient.id, encounter_id=f.encounter_id, flag_type=f.flag_type, severity=f.severity,
            rule_id=f.rule_id, fingerprint=f.fingerprint, message=f.message[:300], details=f.details,
        ))
        result.created += 1

    session.commit()
    return result


def run_rules(session: Session, patient_id: int | None = None, today: date | None = None) -> SyncResult:
    stmt = select(models.Patient).order_by(models.Patient.id)
    if patient_id is not None:
        stmt = stmt.where(models.Patient.id == patient_id)
    total = SyncResult()
    for patient in session.scalars(stmt).all():
        total += sync_patient_flags(session, patient, today)
    return total
