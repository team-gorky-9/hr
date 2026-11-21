"""Запись пакета в базу: по одной транзакции на файл.

Для каждого файла:
1. текст не извлёкся или правила не определили тип/должность → `quarantined`;
2. служебный документ → `source_documents` без кандидата, `excluded_non_resume`;
3. резюме: дубли и конфликты по таблице контракта импорта (п. 3), затем очистка ПДн
   и запись документа, кандидата, ПДн, текста версии 1 и отклика на этапе `new`;
4. у резюме, кандидат которого есть в базе (новый или уже загруженный раньше), —
   «История общения с кандидатом» (app/ingest/history.py): публикация и дата самого
   отклика и внешние отклики на другие должности. Повтор ничего не дублирует, поэтому
   повторный прогон дописывает историю и файлам, загруженным до ingest-02.

Ошибка внутри одного файла откатывает только его (точка сохранения, SAVEPOINT):
частичного кандидата без отклика или текста в базе не остаётся.
"""
import hashlib
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import repository as repo
from app.db.enums import ApplicationSource, DocumentKind
from app.db.models import Application, Candidate, CandidatePii, Position, SourceDocument, Vacancy
from app.ingest.history import parse_history
from app.ingest.package import InputFile, MappingConfig, Problem, Route, resolve_route
from app.ingest.redact import REDACTION_METHOD, RedactionError, redact
from app.schemas.pii import PiiData
from app.ingest.report import ImportReport, ItemStatus, ReportItem
from app.postings.provenance import dataset_fingerprint, record_source


def default_batch_label(now: datetime) -> str:
    return f"ingest-{now:%Y%m%d-%H%M%S}"


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _TextIndex:
    """Отпечатки извлечённого текста уже загруженных резюме — для предупреждения
    `duplicate_text_warning` (разные файлы с одинаковым текстом, ADR-002 Р2)."""

    def __init__(self, session: Session):
        rows = session.execute(
            select(SourceDocument.sha256, SourceDocument.raw_text).where(SourceDocument.kind == DocumentKind.RESUME)
        )
        self._by_text: dict[str, set[str]] = {}
        for file_sha, raw_text in rows:
            self._by_text.setdefault(_text_digest(raw_text), set()).add(file_sha)

    def has_other_file(self, text: str, file_sha: str) -> bool:
        return bool(self._by_text.get(_text_digest(text), set()) - {file_sha})

    def add(self, text: str, file_sha: str) -> None:
        self._by_text.setdefault(_text_digest(text), set()).add(file_sha)


def _find_vacancy(session: Session, route: Route) -> Vacancy | None:
    return session.scalars(
        select(Vacancy)
        .join(Position)
        .where(Position.code == route.position_code, Vacancy.channel == route.channel)
        .order_by(Vacancy.opened_at.desc().nulls_last())
    ).first()


def _current_text_id(session: Session, candidate: Candidate):
    text = repo.get_current_text(session, candidate.id)
    return text.id if text is not None else None


def _sync_history(session: Session, candidate: Candidate, application: Application, raw_text: str) -> dict:
    """Записать сведения «Истории общения» и подвала резюме. Возвращает поля для отчёта.

    Основной отклик получает публикацию и дату, если их ещё нет (ручные правки не затираем).
    Каждая запись истории, не совпавшая с подвалом, — внешний отклик (`source = history`,
    `vacancy_id` пуст); уже существующий не создаётся заново (то же правило держит
    уникальный индекс `uq_applications_history`).
    """
    parsed = parse_history(raw_text)
    if not parsed.found:
        return {}
    if parsed.response_title is not None and application.posting_title is None:
        application.posting_title = parsed.response_title
    if parsed.response_date is not None and application.applied_at is None:
        application.applied_at = parsed.response_date

    added = existing = 0
    for entry in parsed.external:
        found = session.scalar(
            select(Application.id).where(
                Application.candidate_id == candidate.id,
                Application.source == ApplicationSource.HISTORY,
                Application.external_position_title == entry.title,
                Application.applied_at.is_not_distinct_from(entry.applied_at),
            )
        )
        if found is not None:
            existing += 1
            continue
        repo.create_application(
            session,
            candidate_id=candidate.id,
            source=ApplicationSource.HISTORY,
            external_position_title=entry.title,
            applied_at=entry.applied_at,
        )
        added += 1
    session.flush()
    return {
        "posting_found": parsed.response_title is not None,
        "history_added": added,
        "history_existing": existing,
        "history_warnings": list(parsed.warnings),
    }


def _with_history(result: ReportItem, history: dict) -> ReportItem:
    if not history:
        return result
    warnings = [*result.warnings, *history.pop("history_warnings")]
    return result.model_copy(update={**history, "warnings": warnings})


def _merge_pii(session: Session, candidate: Candidate, pii: PiiData) -> None:
    """Дополнить ПДн тем, что нашли новые правила. Уже сохранённое не затираем."""
    row = session.get(CandidatePii, candidate.id)
    data = pii.model_dump()
    if row is None:
        session.add(CandidatePii(candidate_id=candidate.id, **data))
        return
    for name, value in data.items():
        if name == "links":
            row.links = [*row.links, *(link for link in value if link not in row.links)]
        elif name == "extra":
            row.extra = {**value, **row.extra}
        elif getattr(row, name) is None and value is not None:
            setattr(row, name, value)


def _reredact(session: Session, candidate: Candidate, item: InputFile, route: Route) -> dict:
    """Перечистка уже загруженного резюме текущими правилами (флаг --reredact, план ingest-02 Р5).

    Текст отличается → новая текущая версия `candidate_texts` (оценки по старой станут `stale`)
    и ПДн дополняются. Новые правила не прошли проверку → остаётся старый текст, а в отчёте —
    `reredact_failed`: такой текст покажет аудит.
    """
    try:
        redacted = redact(item.text, route.file_format)
    except RedactionError as error:
        return {"reredact": "failed", "warnings": [f"reredact_failed:{error.code}"]}
    current = repo.get_current_text(session, candidate.id)
    if current is not None and current.text == redacted.text:
        return {"reredact": "unchanged"}
    row = repo.add_candidate_text(session, candidate.id, text=redacted.text, redaction_method=REDACTION_METHOD)
    _merge_pii(session, candidate, redacted.pii)
    return {"reredact": "updated", "candidate_text_id": row.id}


def _with_reredact(result: ReportItem, outcome: dict) -> ReportItem:
    if not outcome:
        return result
    warnings = [*result.warnings, *outcome.pop("warnings", [])]
    return result.model_copy(update={**outcome, "warnings": warnings})


def _import_resume(
    session: Session, item: InputFile, route: Route, base: ReportItem, batch: str, text_index: _TextIndex,
    reredact: bool = False,
    *, vacancy: Vacancy | None = None,
) -> ReportItem:
    vacancy = vacancy or _find_vacancy(session, route)
    if vacancy is None:
        return base.model_copy(update={
            "status": ItemStatus.QUARANTINED,
            "reason": f"UNKNOWN_VACANCY: нет вакансии для должности {route.position_code} и канала {route.channel}",
        })

    # Тот же файл (те же байты), возможно под другим именем.
    existing = session.scalar(select(SourceDocument).where(SourceDocument.sha256 == item.sha256))
    if existing is not None:
        if existing.kind != DocumentKind.RESUME:
            return base.model_copy(update={
                "status": ItemStatus.CONFLICT,
                "reason": f"KIND_CONFLICT: те же байты уже сохранены как {existing.kind}",
            })
        candidate = session.scalar(select(Candidate).where(Candidate.source_document_id == existing.id))
        if candidate is None:
            return base.model_copy(update={
                "status": ItemStatus.ERROR, "reason": "ORPHAN_DOCUMENT: резюме сохранено без кандидата",
            })
        # Признак учебного кандидата не меняется: файл, сохранённый реальным, не станет учебным и наоборот.
        # Конфликт — только при явном расхождении; без пометки в mapping повтор остаётся в своём контуре.
        if route.is_synthetic is not None and candidate.is_synthetic != route.is_synthetic:
            return base.model_copy(update={
                "status": ItemStatus.CONFLICT, "candidate_code": candidate.code,
                "reason": "CONTOUR_CONFLICT: те же байты уже сохранены как "
                          + ("учебный" if candidate.is_synthetic else "реальный") + " кандидат",
            })
        refreshed = _reredact(session, candidate, item, route) if reredact else {}
        known = {
            "candidate_code": candidate.code,
            "is_synthetic": candidate.is_synthetic,
            "candidate_id": candidate.id,
            "candidate_text_id": _current_text_id(session, candidate),
        }
        application = session.scalar(
            select(Application).where(Application.candidate_id == candidate.id, Application.vacancy_id == vacancy.id)
        )
        if application is not None:
            # Файл уже загружен: дописываем только историю (её могло не быть до ingest-02).
            result = _with_reredact(base.model_copy(update={
                **known, "status": ItemStatus.DUPLICATE_SKIPPED, "application_id": application.id,
            }), refreshed)
            return _with_history(result, _sync_history(session, candidate, application, item.text))
        application = repo.create_application(
            session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE, vacancy_id=vacancy.id
        )
        result = _with_reredact(base.model_copy(update={
            **known, "status": ItemStatus.APPLICATION_ADDED, "application_id": application.id,
        }), refreshed)
        return _with_history(result, _sync_history(session, candidate, application, item.text))

    # Новый файл, но его код уже у другого кандидата: молча не перезаписываем.
    if session.scalar(select(Candidate.id).where(Candidate.code == route.candidate_code)) is not None:
        return base.model_copy(update={
            "status": ItemStatus.CONFLICT,
            "candidate_code": route.candidate_code,
            "reason": "CODE_CONFLICT: код кандидата уже занят другим файлом",
        })

    try:
        redacted = redact(item.text, route.file_format)
    except RedactionError as error:
        return base.model_copy(update={"status": ItemStatus.QUARANTINED, "reason": str(error)})

    document, _ = repo.add_source_document(
        session,
        kind=DocumentKind.RESUME,
        channel=route.channel,
        file_format=route.file_format,
        original_path=item.source_path,
        raw_text=item.text,
        content=item.content,
        import_batch=batch,
    )
    candidate = repo.create_candidate(
        session,
        code=route.candidate_code,
        source_document_id=document.id,
        redacted_text=redacted.text,
        redaction_method=REDACTION_METHOD,
        headline=redacted.headline,
        pii=redacted.pii,
        is_synthetic=bool(route.is_synthetic),
    )
    application = repo.create_application(
        session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE, vacancy_id=vacancy.id
    )

    warnings = list(redacted.warnings)
    if text_index.has_other_file(item.text, item.sha256):
        warnings.append("duplicate_text_warning")
    result = base.model_copy(update={
        "status": ItemStatus.IMPORTED,
        "candidate_code": candidate.code,
        "is_synthetic": candidate.is_synthetic,
        "candidate_id": candidate.id,
        "candidate_text_id": _current_text_id(session, candidate),
        "application_id": application.id,
        "warnings": warnings,
    })
    return _with_history(result, _sync_history(session, candidate, application, item.text))


def _import_one(
    session: Session, item: InputFile, mapping: MappingConfig, batch: str, text_index: _TextIndex,
    reredact: bool = False,
    dataset_sha256: str | None = None,
) -> ReportItem:
    base = ReportItem(source_path=item.source_path, sha256=item.sha256, status=ItemStatus.QUARANTINED)
    if item.extract_error is not None:
        return base.model_copy(update={"reason": str(item.extract_error)})
    try:
        route = resolve_route(item, mapping)
    except Problem as problem:
        return base.model_copy(update={"reason": str(problem)})
    base = base.model_copy(update={"document_kind": route.document_kind.value})

    savepoint = session.begin_nested()
    try:
        if route.document_kind != DocumentKind.RESUME:
            repo.add_source_document(
                session,
                kind=route.document_kind,
                channel=route.channel,
                file_format=route.file_format,
                original_path=item.source_path,
                raw_text=item.text,
                content=item.content,
                import_batch=batch,
            )
            result = base.model_copy(update={"status": ItemStatus.EXCLUDED_NON_RESUME})
        else:
            result = _import_resume(session, item, route, base, batch, text_index, reredact)
            if mapping.dataset_id is not None and result.status in (
                ItemStatus.IMPORTED, ItemStatus.APPLICATION_ADDED, ItemStatus.DUPLICATE_SKIPPED,
            ):
                application = session.get(Application, result.application_id)
                if application.source == ApplicationSource.RESPONSE:
                    record_source(session, application.id, mapping.dataset_id, dataset_sha256, item, route.channel)
    except repo.RepositoryError as error:
        savepoint.rollback()
        return base.model_copy(update={"status": ItemStatus.ERROR, "reason": f"REPOSITORY_ERROR: {error}"})
    except SQLAlchemyError as error:
        # Текст ошибки базы может содержать значения параметров (в том числе raw_text), поэтому только тип.
        savepoint.rollback()
        return base.model_copy(update={"status": ItemStatus.ERROR, "reason": f"DATABASE_ERROR: {type(error).__name__}"})
    except Exception as error:  # noqa: BLE001 — сбой одного файла не должен останавливать пакет, но попадает в отчёт
        savepoint.rollback()
        return base.model_copy(update={"status": ItemStatus.ERROR, "reason": f"INTERNAL_ERROR: {type(error).__name__}"})

    # duplicate_skipped тоже фиксируется: файл не меняется, но мог дописаться его история.
    if result.status in (
        ItemStatus.IMPORTED, ItemStatus.APPLICATION_ADDED, ItemStatus.DUPLICATE_SKIPPED, ItemStatus.EXCLUDED_NON_RESUME,
    ):
        savepoint.commit()
        if result.status == ItemStatus.IMPORTED:
            text_index.add(item.text, item.sha256)
    else:
        savepoint.rollback()
    return result


def run_import(
    session: Session,
    files: list[InputFile],
    mapping: MappingConfig,
    *,
    import_batch: str,
    commit_each: bool = True,
    reredact: bool = False,
    now=datetime.now,
) -> ImportReport:
    """Загрузить файлы пакета. `commit_each=False` оставляет решение о commit вызывающему (пробный прогон).

    `reredact=True` — уже загруженные резюме очищаются заново текущими правилами (новая версия текста,
    если результат изменился)."""
    report = ImportReport(import_batch=import_batch, started_at=now().astimezone(), dry_run=not commit_each)
    text_index = _TextIndex(session)
    dataset_sha256 = dataset_fingerprint(files) if mapping.dataset_id is not None else None
    for item in files:
        report.add(_import_one(session, item, mapping, import_batch, text_index, reredact, dataset_sha256))
        if commit_each:
            session.commit()
    report.finish(now().astimezone())
    return report


def import_uploaded_resume(session: Session, item: InputFile, route: Route, vacancy: Vacancy) -> ReportItem:
    """Import one explicitly selected vacancy using CLI deduplication and redaction rules.

    The caller owns its transaction, contour access and upload size validation.
    Unlike folder import, this entry never chooses the newest vacancy implicitly.
    """
    if route.position_code != vacancy.position.code or route.channel != vacancy.channel:
        raise ValueError("Upload route does not match the selected vacancy")
    base = ReportItem(source_path=item.source_path, sha256=item.sha256,
                      status=ItemStatus.QUARANTINED, document_kind="resume")
    return _import_resume(session, item, route, base, "staff-upload", _TextIndex(session), vacancy=vacancy)
