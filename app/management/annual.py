"""4B: годовой выпуск из разрешённых фактов legacy-hr.

Пример. HR выпускает учебный отчёт за 2026 год с observed_until=2026-11-22 и заявляет полноту
журнала откликов на интервале 2026-11-01…2026-11-22. Сервис:
1. выбирает отклики площадки (source=response) кандидатов учебного контура и их телефонные встречи;
2. пишет обычный входной пакет годового модуля (manifest.json + applications.csv +
   phone_interviews.csv) во временный каталог рабочей области сервера. Ключи — технические UUID,
   даты — реальные даты отклика и разговора по Москве, без ФИО, контактов и текстов резюме.
   no_answer и встречи без даты разговора идут с пустым held_on — они не становятся проведёнными;
3. проверяет пакет тем же загрузчиком (load_package), считает тем же расчётом (generate) и
   сохраняет снимок в каталог (store.save);
4. записывает выпуск в реестр: контур, заявленная полнота, основание, итог подготовки, автор.
Поздняя поправка источника (новая встреча, дата) даёт новый расчёт с новым snapshot_id; прежний
выпуск остаётся. Факты после observed_until в пакет не входят: дата их не придумывается."""
import csv
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.schemas import Contour
from app.api.workflow import REPORT_TZ
from app.db.enums import ApplicationSource, InterviewKind, InterviewResult
from app.db.models import AnnualReportRelease, Application, Candidate, Interview, User, Vacancy
from app.management.schemas import AnnualReleaseIn, AnnualReleaseOut, ReleaseSummary
from app.reporting import store
from app.reporting.engine import generate
from app.reporting.loader import PackageError, load_package

SCOPE = {Contour.TRAINING: ("legacy-hr-training", "Учебный контур legacy-hr: отклики площадки и телефонные встречи"),
         Contour.WORKING: ("legacy-hr-working", "Рабочий контур legacy-hr: отклики площадки и телефонные встречи")}
MODE = {Contour.TRAINING: "demo", Contour.WORKING: "work"}


def local_day(moment: datetime | None):
    return moment.astimezone(REPORT_TZ).date() if moment is not None else None


def collect(session: Session, body: AnnualReleaseIn) -> tuple[list, list, dict, dict]:
    """Строки пакета и итог подготовки: сколько взято и сколько и почему не вошло."""
    cutoff = body.observed_until
    rows = session.execute(
        select(Application.id, Application.vacancy_id, Application.applied_at, Vacancy.title)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .outerjoin(Vacancy, Vacancy.id == Application.vacancy_id)
        .where(Application.source == ApplicationSource.RESPONSE,
               Candidate.is_synthetic == (body.contour == Contour.TRAINING))
        .order_by(Application.id)
    ).all()
    applications, vacancies, included = [], {}, set()
    skipped = {"applications_without_vacancy": 0, "applications_after_cutoff": 0,
               "interviews_after_cutoff": 0, "interviews_of_skipped_applications": 0}
    for application_id, vacancy_id, applied_at, title in rows:
        if vacancy_id is None:
            skipped["applications_without_vacancy"] += 1
            continue
        if applied_at is not None and applied_at >= cutoff:
            skipped["applications_after_cutoff"] += 1
            continue
        applications.append((str(application_id), str(vacancy_id), applied_at.isoformat() if applied_at else ""))
        vacancies[str(vacancy_id)] = (title or "").strip() or str(vacancy_id)
        included.add(application_id)

    interviews = []
    meetings = session.execute(
        select(Interview.id, Interview.application_id, Interview.result, Interview.held_at)
        .join(Application, Application.id == Interview.application_id)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .where(Interview.kind == InterviewKind.PHONE, Application.source == ApplicationSource.RESPONSE,
               Candidate.is_synthetic == (body.contour == Contour.TRAINING))
        .order_by(Interview.id)
    ).all()
    for interview_id, application_id, result, held_at in meetings:
        if application_id not in included:
            skipped["interviews_of_skipped_applications"] += 1
            continue
        result = InterviewResult(result)
        # Попытка no_answer — не разговор: дата попытки в held_on не переносится.
        held_on = None if result == InterviewResult.NO_ANSWER else local_day(held_at)
        if held_on is not None and held_on >= cutoff:
            skipped["interviews_after_cutoff"] += 1
            continue
        interviews.append((str(interview_id), str(application_id), held_on.isoformat() if held_on else "",
                           str(result)))
    preparation = {"applications": len(applications), "phone_interviews": len(interviews),
                   "undated_applications": sum(1 for a in applications if not a[2]),
                   "interviews_without_held_on": sum(1 for i in interviews if not i[2]), "skipped": skipped}
    return applications, interviews, vacancies, preparation


def manifest(body: AnnualReleaseIn, vacancies: dict, extracted_at: datetime) -> dict:
    scope_id, scope_label = SCOPE[body.contour]

    def source(name, coverage):
        return {"source_id": f"legacy-hr.{name}", "source_revision": extracted_at.isoformat(),
                "complete_intervals": [{"from": i.from_.isoformat(), "to": i.to.isoformat()}
                                       for i in coverage.complete_intervals],
                "comparable_to_previous_year": coverage.comparable_to_previous_year}
    return {
        "input_schema_version": 1, "csv_delimiter": ",", "scope_id": scope_id, "scope_label": scope_label,
        "scope_revision": "1", "mode": MODE[body.contour], "timezone": str(REPORT_TZ),
        "extracted_at": extracted_at.isoformat(), "observed_until": body.observed_until.isoformat(),
        "sources": {"applications": source("applications", body.coverage.applications),
                    "phone_interviews": source("phone_interviews", body.coverage.phone_interviews)},
        "vacancies": vacancies,
    }


def write_package(directory: Path, manifest_data: dict, applications: list, interviews: list) -> None:
    import json
    (directory / "manifest.json").write_text(json.dumps(manifest_data, ensure_ascii=False), encoding="utf-8")
    for name, header, rows in (("applications.csv", ["application_key", "vacancy_key", "applied_on"], applications),
                               ("phone_interviews.csv", ["interview_key", "application_key", "held_on", "result"],
                                interviews)):
        with (directory / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)


def coverage_summary(snapshot: dict, body: AnnualReleaseIn) -> dict:
    totals = snapshot["totals"]
    return {
        "interim": snapshot["interim"],
        "period": {"from": snapshot["period_start"], "to": snapshot["period_end_exclusive"]},
        "declared": body.coverage.model_dump(mode="json", by_alias=True),
        "totals_status": {name: cell["status"] for name, cell in totals.items()},
        "quality": snapshot["quality"],
        "note": ("Выпуск по журналу legacy-hr в пределах заявленной полноты. Это не полная кадровая "
                 "статистика организации: partial — нижняя граница, unavailable — нет подтверждённого охвата."),
    }


def release_summary(row: AnnualReportRelease, author: str | None) -> ReleaseSummary:
    base = f"/api/v1/management/annual-reports/{row.snapshot_id}"
    return ReleaseSummary(
        snapshot_id=row.snapshot_id, mode=row.mode, year=row.year, contour=row.contour, generated_at=row.created_at,
        observed_until=row.observed_until, coverage_summary=row.coverage, preparation=row.preparation,
        confirmation_basis=row.confirmation_basis, created_by=author, report_url=base, xlsx_url=f"{base}/xlsx")


def create_release(session: Session, body: AnnualReleaseIn, user: User, catalog: Path) -> ReleaseSummary:
    extracted_at = datetime.now(REPORT_TZ).replace(microsecond=0)
    if body.observed_until > extracted_at.date():
        raise ApiError(422, "INVALID_OBSERVED_UNTIL", "observed_until не может быть позже сегодняшнего дня (МСК)",
                       {"observed_until": body.observed_until.isoformat()})
    applications, interviews, vacancies, preparation = collect(session, body)
    workspace = catalog / ".packages"
    workspace.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="legacy-hr-", dir=workspace))
    try:
        write_package(directory, manifest(body, vacancies, extracted_at), applications, interviews)
        try:
            snapshot = generate(load_package(directory), body.year)
        except PackageError as error:
            # Безопасная диагностика загрузчика без данных источника: файл, строка, код.
            raise ApiError(422, "PREPARATION_FAILED", "Пакет фактов не прошёл проверку годового модуля",
                           {"reason": str(error)}) from error
        snapshot_id = store.save(snapshot, catalog)
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    row = AnnualReportRelease(
        snapshot_id=snapshot_id, contour=str(body.contour), mode=MODE[body.contour], year=body.year,
        observed_until=body.observed_until, coverage=coverage_summary(snapshot, body),
        confirmation_basis=body.confirmation_basis, preparation=preparation, created_by_user_id=user.id,
        created_at=datetime.now(UTC))
    session.merge(row)
    session.commit()
    return release_summary(session.get(AnnualReportRelease, snapshot_id), user.login)


def read_release(session: Session, snapshot_id: str, catalog: Path) -> tuple[AnnualReportRelease, dict]:
    row = session.get(AnnualReportRelease, snapshot_id)
    if row is None:
        raise ApiError(404, "REPORT_NOT_FOUND", "Выпуск не найден")
    try:
        report = store.read(snapshot_id, catalog)
    except FileNotFoundError as exc:
        raise ApiError(404, "REPORT_NOT_FOUND", "Снимок выпуска отсутствует в каталоге") from exc
    except store.InvalidSnapshot as exc:
        raise ApiError(500, "CORRUPT_REPORT", "Сохранённая версия повреждена") from exc
    return row, report


def release_out(session: Session, row: AnnualReportRelease, report: dict) -> AnnualReleaseOut:
    author = session.get(User, row.created_by_user_id) if row.created_by_user_id else None
    report = {key: value for key, value in report.items() if key != "analytics_index"}
    return AnnualReleaseOut(release=release_summary(row, author.login if author else None), report=report)
