from datetime import date
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from workforce.domain import Problem, changed, digest, lock_organization, owned, permitted, serialize
from workforce.models import Actor, Audit, Department, Inbox, Intake, now
from workforce.schemas import Basis, Code, Input, Text


class InvalidEvent(Exception):
    """Permanent rejection; safe reason code can be recorded on the dead queue."""


class Reference(Input):
    system: Literal["legacy-hr"]
    id: UUID


class PersonReference(Reference):
    display_name: Text


class DocumentReference(Input):
    service: Literal["hiring"]
    id: UUID


class EventBasis(Basis):
    document_ref: DocumentReference


class EmploymentPayload(Input):
    case_id: UUID
    application_ref: Reference
    person_ref: PersonReference
    department_id: UUID
    position_code: Code
    starts_on: date
    basis: EventBasis
    confirmed_by_actor_id: UUID


class EmploymentEvent(Input):
    event_id: UUID
    event_type: Literal["employment.ready"]
    schema_version: Literal["1.0"]
    producer: Literal["hiring"]
    organization_id: UUID
    aggregate_id: UUID
    aggregate_revision: int = Field(ge=1, strict=True)
    occurred_at: AwareDatetime
    correlation_id: UUID
    payload: EmploymentPayload

    @model_validator(mode="after")
    def aggregate_matches(self):
        if self.aggregate_id != self.payload.case_id:
            raise ValueError("case does not match aggregate")
        return self


def receive_event(engine, data):
    try:
        event = EmploymentEvent.model_validate(data)
    except ValidationError as exc:
        raise InvalidEvent("INVALID_SCHEMA") from exc
    normalized = event.model_dump(mode="json")
    org = str(event.organization_id)
    payload = normalized["payload"]
    fingerprint = digest(normalized)
    try:
        with Session(engine) as session, session.begin():
            lock_organization(session, org)
            owned(session, Department, payload["department_id"], org)
            actor = owned(session, Actor, payload["confirmed_by_actor_id"], org)
            if not permitted(actor, ("hr", "admin")):
                raise InvalidEvent("UNAUTHORIZED_SOURCE_ACTOR")
            existing = session.get(Inbox, str(event.event_id))
            if existing:
                if existing.fingerprint != fingerprint:
                    raise InvalidEvent("EVENT_ID_CONFLICT")
                return "duplicate"
            row = session.scalar(
                select(Intake).where(
                    Intake.organization_id == org, Intake.source_case_id == str(event.aggregate_id)
                )
            )
            proposed = {key: payload[key] for key in ("department_id", "position_code", "starts_on", "basis")}
            before = serialize(row) if row else None
            if row is None:
                row = Intake(
                    organization_id=org,
                    source_case_id=str(event.aggregate_id),
                    source_case_revision=event.aggregate_revision,
                    source_event_id=str(event.event_id),
                    correlation_id=str(event.correlation_id),
                    source_payload=payload,
                    person_ref=payload["person_ref"],
                    proposed_assignment=proposed,
                )
                session.add(row)
                outcome = "received"
            elif event.aggregate_revision < row.source_case_revision:
                outcome = "stale"
            elif event.aggregate_revision == row.source_case_revision:
                if payload == row.source_payload:
                    outcome = "duplicate"
                else:
                    row.status, row.issue = "needs_review", "Conflicting content for the same source revision"
                    changed(row)
                    outcome = "needs_review"
            else:
                row.source_case_revision = event.aggregate_revision
                row.source_event_id = str(event.event_id)
                row.correlation_id = str(event.correlation_id)
                row.source_payload, row.person_ref, row.proposed_assignment = (
                    payload,
                    payload["person_ref"],
                    proposed,
                )
                row.status = "needs_review" if row.assignment_id or row.status == "rejected" else "received"
                row.issue = (
                    "New readiness version requires a human decision"
                    if row.status == "needs_review"
                    else None
                )
                changed(row)
                outcome = row.status
            session.flush()
            if outcome not in {"duplicate", "stale"}:
                session.add(
                    Audit(
                        organization_id=org,
                        employee_id=row.employee_id,
                        resource_id=row.id,
                        actor_id=actor.id,
                        action="intake.receive",
                        before=before,
                        after=serialize(row),
                        basis={
                            "source_event_id": str(event.event_id),
                            "source_revision": event.aggregate_revision,
                            "received_payload": payload,
                        },
                        effective_on=event.payload.starts_on,
                    )
                )
            session.add(Inbox(event_id=str(event.event_id), fingerprint=fingerprint, outcome=outcome))
            return outcome
    except Problem as exc:
        raise InvalidEvent("INVALID_ORGANIZATION_OR_REFERENCE") from exc


def registration_event(intake, assignment):
    return {
        "event_id": str(uuid4()),
        "event_type": "assignment.registered",
        "schema_version": "1.0",
        "producer": "workforce",
        "organization_id": intake.organization_id,
        "aggregate_id": assignment.id,
        "aggregate_revision": assignment.revision,
        "occurred_at": now().isoformat(),
        "correlation_id": intake.correlation_id,
        "payload": {
            "intake_id": intake.id,
            "source_case_id": intake.source_case_id,
            "source_case_revision": intake.source_case_revision,
            "source_event_id": intake.source_event_id,
            "employee_id": assignment.employee_id,
            "assignment_id": assignment.id,
            "department_id": assignment.department_id,
            "position_code": assignment.position_code,
            "starts_on": assignment.starts_on.isoformat(),
            "revision": assignment.revision,
        },
    }


def review_event(intake, assignment, review):
    envelope = registration_event(intake, assignment)
    envelope.update(
        event_type="assignment.reviewed", aggregate_id=intake.id, aggregate_revision=intake.revision
    )
    envelope["payload"].update(
        {key: review[key] for key in ("decision", "reason", "reviewed_by_actor_id", "reviewed_at")}
    )
    envelope["payload"]["basis"] = assignment.basis
    return envelope
