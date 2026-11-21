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
from hiring.models import CandidateRequest, CandidateRequestEvent, CandidateRequestMessage, Document, now

EDITABLE = ("draft",)
CHOOSE_VACANCY = ("submitted", "needs_information", "ready")
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


OUTCOME_TITLES = {
    "continue": "Рассмотрение продолжается",
    "declined": "Решение по обращению",
    "no_open_opportunity": "Сейчас нет подходящей открытой вакансии",
    "completed": "Обращение завершено",
}
OPEN_FOR_WITHDRAWAL = ("draft", "submitted", "needs_information", "ready", "forwarded")


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
        info = row.information_request
        body["information_request"] = None if info is None else {
            k: info[k] for k in ("public_message", "requested_items", "requested_at", "answered")}
        body["information_request_ref"] = (
            {"request_id": uid(row.id), "event_sequence": info["event_sequence"]}
            if info and info.get("event_sequence") is not None else None)
        body["addenda"] = [{k: a[k] for k in ("text", "document_ids", "added_at")} for a in row.addenda]
        public = ("outcome", "public_explanation", "next_action", "decided_at")
        if self.actor.is_hr():
            body |= {"organization_id": uid(row.organization_id), "author_actor_id": uid(row.author_actor_id),
                     "submitted_snapshot": row.submitted_snapshot, "review": row.review,
                     "consideration": row.consideration, "outcomes": row.outcomes, "withdrawal": row.withdrawal}
        else:
            # Кандидат видит согласованное публичное объяснение, без ссылки на источник решения и автора.
            body["outcomes"] = [{k: o[k] for k in public} for o in row.outcomes]
            body["withdrawal"] = None if row.withdrawal is None else {
                k: row.withdrawal[k] for k in ("reason", "withdrawn_at", "notice")}
        body["unread_messages"] = self.session.scalar(
            select(func.count()).select_from(CandidateRequestMessage).where(
                CandidateRequestMessage.request_id == row.id, CandidateRequestMessage.read_at.is_(None))) or 0
        if not self.actor.is_hr():
            # Кандидат видит факт принятия к рассмотрению и выбранную вакансию, но не ссылки на записи
            # подбора, основание связи личности и внутреннюю проверку достаточности.
            consideration = row.consideration
            body["consideration"] = None if consideration is None else {
                "status": "registered", "recorded_at": consideration["recorded_at"],
                "selected_vacancy": consideration["selected_vacancy"]}
        return body

    def record(self, row: CandidateRequest, event_type: str, data: dict) -> int:
        self.session.flush()
        sequence = (self.session.scalar(select(func.max(CandidateRequestEvent.sequence))
                                        .where(CandidateRequestEvent.request_id == row.id)) or 0) + 1
        self.session.add(CandidateRequestEvent(
            request_id=row.id, sequence=sequence, request_revision=row.revision, event_type=event_type,
            actor_id=self.actor.actor_id, actor_role=self.actor.role,
            data=json.loads(json.dumps(data, default=str))))
        return sequence

    def history(self, request_id: uuid.UUID) -> dict:
        row = self.load(request_id)
        events = self.session.scalars(select(CandidateRequestEvent).where(CandidateRequestEvent.request_id == row.id)
                                      .order_by(CandidateRequestEvent.sequence))
        hr = self.actor.is_hr()
        return {"items": [{"sequence": e.sequence, "event_type": e.event_type, "request_revision": e.request_revision,
                           "actor_role": e.actor_role, "created_at": iso(e.created_at),
                           "data": e.data if hr else candidate_event_data(e.event_type, e.data),
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


    # --- 5B · уточнение и передача в подбор

    def hr_load(self, request_id) -> CandidateRequest:
        if not self.actor.is_hr():
            raise forbidden("hr or admin of the organization is required")
        return self.load(request_id, lock=True)

    @staticmethod
    def check(row: CandidateRequest, expected: int, allowed: tuple, action: str):
        if row.revision != expected:
            raise stale()
        if row.status not in allowed:
            raise invalid_state(f"{action} is not allowed in status {row.status}")

    def request_information(self, request_id, body: s.InformationRequest) -> dict:
        row = self.hr_load(request_id)
        self.check(row, body.expected_revision, ("submitted", "ready", "needs_information"), "Information request")
        previous = row.status
        row.information_request = {
            "public_message": body.public_message, "requested_items": body.requested_items,
            "requested_at": iso(now()), "requested_by_actor_id": uid(self.actor.actor_id), "answered": False}
        row.status = "needs_information"
        if previous == "ready":
            row.review = None  # готовность снята: сведения снова неполны
        row.revision += 1
        sequence = self.record(row, "information.requested", {"public_message": body.public_message,
                                                   "requested_items": body.requested_items, "previous": previous})
        row.information_request = {**row.information_request, "event_sequence": sequence}
        self.message(row, "information_request", "Нужны дополнительные сведения",
                     body.public_message + "\nЧто нужно: " + "; ".join(body.requested_items),
                     "Ответьте дополнением в кабинете")
        return self.view(row)

    def add_addendum(self, request_id, body: s.Addendum) -> dict:
        row = self.own(request_id)
        self.check(row, body.expected_revision, ("needs_information",), "Addendum")
        active_sequence = row.information_request.get("event_sequence")
        reference = body.information_request_ref
        if active_sequence is not None:
            if reference is None or reference.request_id != row.id or reference.event_sequence != active_sequence:
                raise stale("information_request_ref")
        elif reference is not None:
            # Historical requests have no proven event correlation; never guess from timestamps.
            raise stale("information_request_ref")
        own_documents = {d.id for d in self.documents(row)}
        unknown = [str(d) for d in body.document_ids if d not in own_documents]
        if unknown:
            raise Problem(422, "VALIDATION_ERROR", "document_ids must be documents of this request", "document_ids")
        addendum = {"text": body.text, "document_ids": [str(d) for d in body.document_ids], "added_at": iso(now()),
                    "answers_request_at": row.information_request["requested_at"]}
        if reference is not None:
            addendum["information_request_ref"] = reference.model_dump(mode="json")
        row.addenda = [*row.addenda, addendum]  # прежние материалы и подача сохраняются
        row.information_request = {**row.information_request, "answered": True}
        row.status = "submitted"
        row.revision += 1
        self.record(row, "addendum.added", addendum)
        return self.view(row)

    def mark_ready(self, request_id, body: s.RequestReady) -> dict:
        row = self.hr_load(request_id)
        self.check(row, body.expected_revision, ("submitted",), "Ready")
        row.review = {"review_basis": body.review_basis, "reviewed_by_actor_id": uid(self.actor.actor_id),
                      "reviewed_at": iso(now())}
        row.status = "ready"
        row.revision += 1
        self.record(row, "request.ready", {"review_basis": body.review_basis})
        return self.view(row)

    def choose_vacancy(self, request_id, body: s.ChooseVacancy) -> dict:
        row = self.own(request_id)
        self.check(row, body.expected_revision, CHOOSE_VACANCY, "Choosing a vacancy")
        vacancy, question = resolve_vacancy(self.settings, row.organization_id, body.vacancy_ref)
        if question is not None:
            raise Problem(409, "VACANCY_NOT_AVAILABLE", "Vacancy is closed or this revision is not published",
                          "vacancy_ref")
        row.vacancy_ref, row.vacancy, row.target_question = body.vacancy_ref.model_dump(mode="json"), vacancy, None
        row.revision += 1
        self.record(row, "vacancy.chosen", {"vacancy_ref": row.vacancy_ref})
        view = self.view(row)
        view["vacancy_conditions"] = vacancy_conditions(self.settings, body.vacancy_ref)
        return view

    def record_consideration(self, request_id, body: s.RecordConsideration) -> dict:
        row = self.hr_load(request_id)
        self.check(row, body.expected_revision, ("ready",), "Recording consideration")
        vacancy, _ = resolve_vacancy(self.settings, row.organization_id, body.selected_vacancy_ref)
        if vacancy is None:
            # Закрытая после фактической регистрации публикация допустима; неизвестная редакция — нет.
            raise Problem(409, "VACANCY_NOT_AVAILABLE", "Selected vacancy revision is unknown", "selected_vacancy_ref")
        row.consideration = {
            "candidate_ref": body.candidate_ref.model_dump(mode="json"),
            "application_ref": body.application_ref.model_dump(mode="json"),
            "selected_vacancy_ref": body.selected_vacancy_ref.model_dump(mode="json"),
            "selected_vacancy": {"title": vacancy["title"], "position_code": vacancy["position_code"]},
            "identity_basis": body.identity_basis, "source_reference": body.source_reference,
            # Слово HR о факте регистрации, а не автоматическая проверка соседней системы.
            "confirmation_method": "manual-confirmed",
            "recorded_by_actor_id": uid(self.actor.actor_id), "recorded_at": iso(now()),
        }
        row.status = "forwarded"
        row.revision += 1
        self.record(row, "consideration.recorded", row.consideration)
        return self.view(row)


    # --- 5C · исход, отзыв и сообщения кабинета

    def message(self, row: CandidateRequest, kind: str, title: str, body: str, next_action: str | None) -> None:
        self.session.add(CandidateRequestMessage(request_id=row.id, kind=kind, title=title, body=body,
                                                 next_action=next_action, created_by_actor_id=self.actor.actor_id))

    def publish_outcome(self, request_id, body: s.PublicOutcome) -> dict:
        row = self.hr_load(request_id)
        self.check(row, body.expected_revision, ("ready", "forwarded"), "Public outcome")
        if body.outcome == "continue" and row.status != "forwarded":
            # continue оставляет обращение в forwarded, а это требует записанной регистрации рассмотрения.
            raise invalid_state("Record the consideration before publishing that it continues")
        outcome = {
            "outcome": body.outcome, "public_explanation": body.public_explanation, "next_action": body.next_action,
            "source_reference": body.source_reference, "origin": "hr_decision",
            "decided_by_actor_id": uid(self.actor.actor_id), "decided_at": iso(now()),
        }
        row.outcomes = [*row.outcomes, outcome]
        row.status = "forwarded" if body.outcome == "continue" else "closed"
        row.revision += 1
        self.record(row, "outcome.published", outcome)
        self.message(row, "outcome", OUTCOME_TITLES[body.outcome], body.public_explanation, body.next_action)
        return self.view(row)

    def withdraw(self, request_id, body: s.WithdrawRequest) -> dict:
        row = self.own(request_id)
        self.check(row, body.expected_revision, OPEN_FOR_WITHDRAWAL, "Withdrawal")
        external = row.status == "forwarded"
        row.withdrawal = {
            "reason": body.reason, "withdrawn_at": iso(now()), "previous_status": row.status,
            "external_consideration_open": external,
            # Локальный отзыв не останавливает рассмотрение у владельца подбора.
            "notice": ("Обращение отозвано в кабинете. Рассмотрение в подборе завершает его владелец после "
                       "подтверждения." if external else "Обращение отозвано."),
        }
        row.status = "withdrawn"
        row.revision += 1
        self.record(row, "request.withdrawn", row.withdrawal)
        return self.view(row)

    def messages(self, request_id) -> dict:
        row = self.load(request_id)
        rows = self.session.scalars(select(CandidateRequestMessage).where(CandidateRequestMessage.request_id == row.id)
                                    .order_by(CandidateRequestMessage.created_at, CandidateRequestMessage.id))
        return {"items": [message_view(m) for m in rows]}

    def mark_read(self, request_id, message_id) -> dict:
        row = self.own(request_id)  # отметку прочтения ставит только автор
        message = self.session.scalar(select(CandidateRequestMessage).where(
            CandidateRequestMessage.id == message_id, CandidateRequestMessage.request_id == row.id).with_for_update())
        if message is None:
            raise not_found("Message")
        if message.read_at is None:  # повтор возвращает первую отметку
            message.read_at = now()
            self.record(row, "message.read", {"message_id": uid(message.id)})
        self.session.flush()
        self.session.refresh(message)  # первый ответ и повтор показывают одно сохранённое значение
        return message_view(message)


def candidate_event_data(event_type: str, data: dict) -> dict:
    """Public history is a DTO, never an internal event payload with a few fields removed."""
    allowed = {
        "request.created": ("vacancy_ref", "target_question"),
        "request.updated": ("changed_fields",),
        "request.submitted": ("number", "target_question", "document_ids"),
        "document.added": ("document_id", "kind", "after_submit"),
        "information.requested": ("public_message", "requested_items", "previous"),
        "addendum.added": ("text", "document_ids", "added_at", "information_request_ref"),
        "vacancy.chosen": ("vacancy_ref",),
        "consideration.recorded": ("recorded_at", "selected_vacancy"),
        "outcome.published": ("outcome", "public_explanation", "next_action", "decided_at"),
        "request.withdrawn": ("reason", "withdrawn_at", "notice"),
        "message.read": ("message_id",),
    }
    return {key: data[key] for key in allowed.get(event_type, ()) if key in data}


def message_view(message: CandidateRequestMessage) -> dict:
    return {"id": uid(message.id), "kind": message.kind, "title": message.title, "body": message.body,
            "next_action": message.next_action, "created_at": iso(message.created_at), "read_at": iso(message.read_at)}


def vacancy_conditions(settings, ref: s.PortalVacancyRef) -> dict | None:
    """Условия точной редакции публикации из того же источника, по которому выбрана вакансия."""
    for item in public_vacancies(settings)["vacancies"]:
        if (item["ref"]["system"], item["ref"]["id"], item["ref"]["revision"]) == (ref.system, str(ref.id), ref.revision):
            return {"ref": item["ref"], "title": item["title"], "description": item["description"]}
    return None
