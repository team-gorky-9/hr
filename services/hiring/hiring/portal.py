"""candidate-portal, 5A: собственное обращение кандидата (wave-5-candidate-portal-stage-1).

Пример. Кандидат `candidate` создаёт черновик по учебной вакансии «Экономист» (точная редакция из
fixtures/public-vacancies.json), прикладывает резюме и отправляет: обращение получает номер ОБР-000001
и статус submitted, снимок подачи фиксирует текст, контакт, цель и файлы. Кандидат `candidate2`
подаёт обращение без вакансии: target_question=no_target. HR своей организации видит обе подачи в
очереди, черновики — нет. Ни один кандидат не открывает чужое обращение и чужой файл: 404.
Если выбранная вакансия закрыта или не найдена, обращение принимается с вопросом цели
(vacancy_closed / vacancy_unknown) и откликом в подборе автоматически не становится."""
import json
import uuid
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from hiring import schemas as s
from hiring.auth import Actor
from hiring.domain import iso, uid
from hiring.errors import Problem, forbidden, invalid_state, not_found, stale
from hiring.models import CandidateRequest, CandidateRequestEvent, Document, now

EDITABLE = ("draft",)
DOCUMENTS_ALLOWED = ("draft", "submitted", "needs_information")


@lru_cache(maxsize=4)
def _vacancy_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def public_vacancies(settings) -> dict:
    """Учебный снимок публичных вакансий (source=training_snapshot). Живой каталог не подключён."""
    return _vacancy_file(settings.public_vacancies_file)


def resolve_vacancy(settings, organization_id: uuid.UUID, ref: s.PortalVacancyRef | None) -> tuple[dict | None, str | None]:
    """(снимок вакансии для обращения, вопрос цели). Точная редакция; похожее название не используется."""
    if ref is None:
        return None, "no_target"
    data = public_vacancies(settings)
    for item in data["vacancies"]:
        known = item["ref"]
        if (known["system"], known["id"], known["revision"]) == (ref.system, str(ref.id), ref.revision) \
                and item["organization_id"] == str(organization_id):
            snapshot = {"title": item["title"], "status": item["status"], "position_code": item["position_code"],
                        "source": data["source"], "observed_at": data["observed_at"]}
            return snapshot, (None if item["status"] == "published" else "vacancy_closed")
    return None, "vacancy_unknown"


def document_view(document: Document) -> dict:
    return {"id": uid(document.id), "kind": document.kind, "original_name": document.original_name,
            "media_type": document.media_type, "size_bytes": document.size_bytes, "sha256": document.sha256,
            "created_at": iso(document.created_at)}


class Portal:
    def __init__(self, session: Session, actor: Actor, settings):
        self.session, self.actor, self.settings = session, actor, settings

    # --- доступ

    def require_candidate(self):
        if not self.actor.is_candidate():
            raise forbidden("Only a candidate account can create and edit its own request")

    def require_reader(self):
        if not (self.actor.is_candidate() or self.actor.is_hr()):
            raise forbidden("Candidate requests are available to the author and hr/admin of the organization")

    def visible(self, row: CandidateRequest | None) -> bool:
        if row is None or row.organization_id != self.actor.organization_id:
            return False
        if row.author_actor_id == self.actor.actor_id:
            return True
        # Черновик принадлежит только автору: HR видит обращение после подачи.
        return self.actor.is_hr() and row.status != "draft"

    def load(self, request_id: uuid.UUID, lock: bool = False) -> CandidateRequest:
        self.require_reader()
        query = select(CandidateRequest).where(CandidateRequest.id == request_id)
        row = self.session.scalar(query.with_for_update() if lock else query)
        if not self.visible(row):
            raise not_found("Candidate request")
        return row

    def own(self, request_id: uuid.UUID) -> CandidateRequest:
        self.require_candidate()
        row = self.load(request_id, lock=True)
        if row.author_actor_id != self.actor.actor_id:
            raise not_found("Candidate request")
        return row

    # --- представление и история

    def documents(self, row: CandidateRequest) -> list[Document]:
        return list(self.session.scalars(select(Document).where(Document.request_id == row.id)
                                         .order_by(Document.created_at, Document.id)))

    def view(self, row: CandidateRequest) -> dict:
        self.session.flush()
        body = {
            "id": uid(row.id), "number": row.number, "status": row.status, "revision": row.revision,
            "vacancy_ref": row.vacancy_ref, "vacancy": row.vacancy, "target_question": row.target_question,
            "message": row.message, "contact": row.contact,
            "documents": [document_view(d) for d in self.documents(row)],
            "created_at": iso(row.created_at), "updated_at": iso(row.updated_at), "submitted_at": iso(row.submitted_at),
        }
        if self.actor.is_hr():
            body |= {"organization_id": uid(row.organization_id), "author_actor_id": uid(row.author_actor_id),
                     "submitted_snapshot": row.submitted_snapshot}
        return body

    def record(self, row: CandidateRequest, event_type: str, data: dict) -> None:
        self.session.flush()
        sequence = (self.session.scalar(select(func.max(CandidateRequestEvent.sequence))
                                        .where(CandidateRequestEvent.request_id == row.id)) or 0) + 1
        self.session.add(CandidateRequestEvent(
            request_id=row.id, sequence=sequence, request_revision=row.revision, event_type=event_type,
            actor_id=self.actor.actor_id, actor_role=self.actor.role,
            data=json.loads(json.dumps(data, default=str))))

    def history(self, request_id: uuid.UUID) -> dict:
        row = self.load(request_id)
        events = self.session.scalars(select(CandidateRequestEvent).where(CandidateRequestEvent.request_id == row.id)
                                      .order_by(CandidateRequestEvent.sequence))
        hr = self.actor.is_hr()
        return {"items": [{"sequence": e.sequence, "event_type": e.event_type, "request_revision": e.request_revision,
                           "actor_role": e.actor_role, "created_at": iso(e.created_at), "data": e.data,
                           **({"actor_id": uid(e.actor_id)} if hr else {})} for e in events]}

    # --- операции

    def contact_of(self, contact: s.CandidateContact) -> dict:
        return {"channel": contact.channel, "value": contact.value, "source": "candidate_reported",
                "verified": False}

    def create(self, body: s.CreateCandidateRequest) -> tuple[int, dict]:
        self.require_candidate()
        vacancy, question = resolve_vacancy(self.settings, self.actor.organization_id, body.vacancy_ref)
        row = CandidateRequest(
            id=uuid.uuid4(), organization_id=self.actor.organization_id, author_actor_id=self.actor.actor_id,
            status="draft", revision=1, message=body.message, contact=self.contact_of(body.contact),
            vacancy_ref=body.vacancy_ref.model_dump(mode="json") if body.vacancy_ref else None,
            vacancy=vacancy, target_question=question)
        self.session.add(row)
        self.record(row, "request.created", {"vacancy_ref": row.vacancy_ref, "target_question": question})
        return 201, self.view(row)

    def update(self, request_id, body: s.UpdateCandidateRequest) -> dict:
        row = self.own(request_id)
        if row.revision != body.expected_revision:
            raise stale()
        if row.status not in EDITABLE:
            raise invalid_state(f"Only a draft can be edited, status is {row.status}")
        changed = []
        if body.message is not None:
            row.message, changed = body.message, [*changed, "message"]
        if body.contact is not None:
            row.contact, changed = self.contact_of(body.contact), [*changed, "contact"]
        if body.vacancy_ref is not None or body.clear_vacancy:
            ref = body.vacancy_ref
            row.vacancy, row.target_question = resolve_vacancy(self.settings, row.organization_id, ref)
            row.vacancy_ref = ref.model_dump(mode="json") if ref else None
            changed.append("vacancy_ref")
        row.revision += 1
        self.record(row, "request.updated", {"fields": changed, "target_question": row.target_question})
        return self.view(row)

    def submit(self, request_id, body: s.SubmitCandidateRequest) -> dict:
        row = self.own(request_id)
        if row.revision != body.expected_revision:
            raise stale()
        if row.status != "draft":
            raise invalid_state(f"Only a draft can be submitted, status is {row.status}")
        # Цель перепроверяется на момент подачи: вакансию могли закрыть после выбора.
        if row.vacancy_ref is not None:
            ref = s.PortalVacancyRef.model_validate(row.vacancy_ref)
            row.vacancy, row.target_question = resolve_vacancy(self.settings, row.organization_id, ref)
        number = self.session.scalar(text("SELECT nextval('candidate_request_number_seq')"))
        row.number = f"ОБР-{number:06d}"
        row.status = "submitted"
        row.submitted_at = now()
        row.revision += 1
        row.submitted_snapshot = {
            "message": row.message, "contact": row.contact, "vacancy_ref": row.vacancy_ref, "vacancy": row.vacancy,
            "target_question": row.target_question, "document_ids": [uid(d.id) for d in self.documents(row)],
            "submitted_at": iso(row.submitted_at)}
        self.record(row, "request.submitted", {"number": row.number, "target_question": row.target_question,
                                               "document_ids": row.submitted_snapshot["document_ids"]})
        return self.view(row)

    def attach(self, request_id, document: Document) -> dict:
        row = self.own(request_id)
        if row.status not in DOCUMENTS_ALLOWED:
            raise invalid_state(f"Documents cannot be added in status {row.status}")
        document.request_id = row.id
        self.session.add(document)
        row.revision += 1
        self.record(row, "document.added", {"document_id": uid(document.id), "kind": document.kind,
                                            "after_submit": row.status != "draft"})
        self.session.flush()
        return {**document_view(document), "request_id": uid(row.id), "request_revision": row.revision}

    def list_requests(self, status: str | None) -> dict:
        self.require_reader()
        query = select(CandidateRequest).where(CandidateRequest.organization_id == self.actor.organization_id)
        if self.actor.is_hr():
            query = query.where(CandidateRequest.status != "draft")
        else:
            query = query.where(CandidateRequest.author_actor_id == self.actor.actor_id)
        if status is not None:
            if status not in s.REQUEST_STATUSES:
                raise Problem(422, "VALIDATION_ERROR", f"status must be one of {', '.join(s.REQUEST_STATUSES)}",
                              "status")
            query = query.where(CandidateRequest.status == status)
        rows = self.session.scalars(query.order_by(CandidateRequest.created_at, CandidateRequest.id))
        return {"items": [self.view(row) for row in rows]}

    def get(self, request_id) -> dict:
        return self.view(self.load(request_id))

    def document(self, request_id, document_id) -> Document:
        row = self.load(request_id)
        document = self.session.get(Document, document_id)
        if document is None or document.request_id != row.id:
            raise not_found("Document")
        return document
