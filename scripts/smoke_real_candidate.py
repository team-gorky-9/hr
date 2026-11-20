"""Сквозной прогон каркаса базы на одном реальном отклике из архива организаторов.

Что реально: исходный текст файла «Python-разработчик/отклик 5.txt», цитаты-доказательства
ищутся в этом тексте и проверяются кодом.
Что заполнено вручную: карточка кандидата, очистка ПДн и требования должности —
импорта и ИИ-модуля ещё нет. Это проверка хранения, а не извлечения.

Всё выполняется в одной транзакции и откатывается: база остаётся как была.

Запуск (из корня hr):
    uv run python -m scripts.smoke_real_candidate "<путь к папке Кадры>"
"""
import re
import sys
import unicodedata
from pathlib import Path

from sqlalchemy import func, select

from app.db import repository as repo
from app.db.enums import (
    ApplicationSource,
    Channel,
    CheckResult,
    DocumentKind,
    FeedbackOutcome,
    FileFormat,
    FormalRequirementKind,
    RowOrigin,
    UserRole,
    VerificationMethod,
)
from app.db.models import (
    AuditLog,
    Position,
    StageEvent,
    User,
    Vacancy,
)
from app.db.session import SessionLocal
from app.schemas.assessment import CompetencyScoreIn, FormalCheckIn
from app.schemas.card import CandidateCard, Evidence, Experience, Skill
from app.schemas.pii import PiiData
from app.schemas.requirements import CompetencyIn, FormalRequirementIn, IndicatorIn

RESUME = ("Python-разработчик", "отклик 5.txt")


def find_resume(root: Path) -> Path:
    for path in root.rglob("*.txt"):
        parts = [unicodedata.normalize("NFC", p) for p in path.parts]
        if "__MACOSX" not in parts and tuple(parts[-2:]) == RESUME:
            return path
    raise SystemExit(f"не найден файл {'/'.join(RESUME)} в {root}")


def quote(text_row, fragment: str) -> Evidence:
    start = text_row.text.index(fragment)
    return Evidence(candidate_text_id=text_row.id, quote=fragment, start=start, end=start + len(fragment))


def main(root: Path) -> None:
    path = find_resume(root)
    content = path.read_bytes()
    raw_text = content.decode("utf-8")

    # Очистка вручную: убираем ссылки на GitHub (в них имя и фамилия).
    links = re.findall(r"(?:https?://)?github\.com/\S+", raw_text)
    redacted = re.sub(r"(?:https?://)?github\.com/\S+", "[ссылка скрыта]", raw_text)

    with SessionLocal() as session:
        position = session.scalar(select(Position).where(Position.code == "python-dev"))
        vacancy = session.scalar(select(Vacancy).where(Vacancy.position_id == position.id))

        # 1. Импорт: исходный документ, кандидат, ПДн отдельно, отклик на вакансию.
        document, created = repo.add_source_document(
            session, kind=DocumentKind.RESUME, channel=Channel.HH_RU, file_format=FileFormat.HH_TXT,
            original_path="/".join(RESUME), raw_text=raw_text, content=content, import_batch="smoke",
        )
        _, created_again = repo.add_source_document(
            session, kind=DocumentKind.RESUME, channel=Channel.HH_RU, file_format=FileFormat.HH_TXT,
            original_path="/".join(RESUME), raw_text=raw_text, content=content,
        )
        candidate = repo.create_candidate(
            session, code="py-0005", source_document_id=document.id, redacted_text=redacted,
            redaction_method="manual-smoke", headline="Python Backend Developer (FastAPI, PostgreSQL)",
            pii=PiiData(links=links),
        )
        application = repo.create_application(
            session, candidate_id=candidate.id, vacancy_id=vacancy.id, source=ApplicationSource.RESPONSE
        )
        text_row = repo.get_current_text(session, candidate.id)

        # 2. Карточка (вручную по тексту резюме).
        card = repo.add_candidate_card(
            session, candidate.id,
            CandidateCard(
                headline=candidate.headline,
                applied_to=["Python-разработчик"],
                experience_years=13.3,
                experience=[
                    Experience(position="Backend-разработчик", organization="Организация 1",
                               start="2024-05", end="2025-05",
                               duties=["REST API на FastAPI", "SQLAlchemy, PostgreSQL", "тесты на Pytest"]),
                    Experience(position="Специалист по контролю качества и аналитике",
                               organization="Организация 2", start="2016-06", end="2024-05"),
                ],
                skills=[Skill(name=s) for s in
                        ["Python", "PostgreSQL", "Docker", "Git", "Pytest", "SQLAlchemy", "FastAPI"]],
                missing=["сопроводительное письмо"],
            ),
            extractor="manual-smoke",
        )

        # 3. Требования должности (вручную, утверждены smoke-кадровиком) и оценка с цитатами из настоящего
        #    текста. Реального кандидата база оценивает только по утверждённому рабочему профилю (v1.5),
        #    поэтому сначала проверяем, что учебный профиль для него отклоняется.
        team = {"origin": RowOrigin.TEAM, "note": "проверочный профиль smoke-скрипта"}
        smoke_user = User(login="manual-smoke", full_name="Smoke", role=UserRole.HR, is_active=True)
        session.add(smoke_user)
        session.flush()
        education = FormalRequirementIn(
            key="smoke.education", kind=FormalRequirementKind.EDUCATION_LEVEL, description="Высшее образование",
            params={"schema_version": "0.1", "alternatives": [{"key": "smoke.education.alt1", "level": "высшее"}]},
            verification=VerificationMethod.RESUME, **team)
        training = repo.create_requirement_profile(
            session, position_id=position.id, created_by="manual-smoke", is_synthetic=True,
            formal_requirements=[education], competencies=[])
        repo.approve_requirement_profile(session, training.id, approved_by_user_id=smoke_user.id,
                                         approval_basis="smoke: учебный профиль")
        try:
            repo.save_assessment(session, candidate_id=candidate.id, profile_id=training.id, card_id=card.id,
                                 model="manual-smoke", formal_checks=[], competency_scores=[])
            training_rejected = False
        except repo.RepositoryError:
            training_rejected = True
        profile = repo.create_requirement_profile(
            session, position_id=position.id, created_by="manual-smoke",
            formal_requirements=[education],
            competencies=[CompetencyIn(
                key="smoke.BACKEND", code="BACKEND", name="Разработка backend на Python", **team,
                indicators=[IndicatorIn(key="smoke.BACKEND.01", text="разрабатывал REST API и писал автотесты",
                                        verification=VerificationMethod.RESUME, **team)])],
        )
        repo.approve_requirement_profile(session, profile.id, approved_by_user_id=smoke_user.id,
                                         approval_basis="smoke: проверочный рабочий профиль")
        assessment = repo.save_assessment(
            session, candidate_id=candidate.id, profile_id=profile.id, card_id=card.id, model="manual-smoke",
            formal_checks=[FormalCheckIn(requirement_id=profile.formal_requirements[0].id, result=CheckResult.MET,
                                         evidence=[quote(text_row, "Высшее образование")])],
            competency_scores=[CompetencyScoreIn(
                competency_id=profile.competencies[0].id, level=65,
                evidence=[quote(text_row, "Писала автоматические тесты на Pytest."),
                          quote(text_row, "Разрабатывала и поддерживала REST API (GET/POST).")],
            )],
        )
        try:
            repo.save_assessment(
                session, candidate_id=candidate.id, profile_id=profile.id, card_id=card.id, model="manual-smoke", formal_checks=[],
                competency_scores=[CompetencyScoreIn(
                    competency_id=profile.competencies[0].id, level=90,
                    evidence=[Evidence(candidate_text_id=text_row.id, quote="Руководила командой", start=0, end=19)],
                )],
            )
            fake_quote_rejected = False
        except repo.EvidenceError:
            fake_quote_rejected = True

        # 4. Отбор: звонок, департамент, отказ, резерв; поиск по навыкам и резерву.
        for stage in ["screening", "phone_interview", "sent_to_department"]:
            repo.move_application(session, application.id, stage)
        repo.record_department_feedback(
            session, application.id, outcome=FeedbackOutcome.NOT_FIT, interview_held=True,
            gaps="мало коммерческого опыта в разработке", rejection_reason_code="experience", keep_in_reserve=True,
        )
        repo.move_application(session, application.id, "rejected", rejection_reason_code="experience")
        repo.add_to_reserve(session, candidate_id=candidate.id, position_id=position.id, source_application_id=application.id,
                            reason="подойдёт на следующую вакансию Python")
        repo.get_candidate_pii(session, candidate.id, user_id=None, purpose="smoke")

        results = {
            "файл": str(path.relative_to(root)),
            "документ создан / повтор не создан": (created, not created_again),
            "ссылок вынесено в ПДн": len(links),
            "ссылок осталось в очищенном тексте": len(re.findall(r"github\.com", text_row.text)),
            "навыков в карточке": len(card.skills),
            "найден по навыкам fastapi+pytest": candidate in repo.find_candidates_by_skills(
                session, ["FastAPI", "pytest"]),
            "оценка: формальные / балл": (assessment.formal_result.value,
                                          assessment.competency_scores[0].level),
            "выдуманная цитата отклонена": fake_quote_rejected,
            "оценка реального кандидата по учебному профилю отклонена": training_rejected,
            "учебный и рабочий профили утверждены одновременно": (
                repo.get_approved_profile(session, position.id).id == profile.id
                and repo.get_approved_profile(session, position.id, synthetic=True).id == training.id),
            "история этапов": [e.to_stage_code for e in repo.stage_history(session, application.id)],
            "в резерве на должность": candidate.id in {
                e.candidate_id for e in repo.reserve_for_position(session, position.id)},
            "записей аудита": session.scalar(select(func.count()).select_from(AuditLog)
                                             .where(AuditLog.entity_id == str(candidate.id))),
            "событий этапов": session.scalar(select(func.count()).select_from(StageEvent)
                                             .where(StageEvent.application_id == application.id)),
        }
        session.rollback()

    for key, value in results.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
