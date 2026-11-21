"""Демо-стенд одной командой: база, учебные кандидаты, профили по ДИ, оценка и светофор.

    uv run python -m scripts.demo_setup              # всё, включая оценку моделью (нужен ключ в .env)
    uv run python -m scripts.demo_setup --no-llm     # без вызовов модели: база, данные, профили, сводка
    uv run python -m scripts.demo_setup --workers 4  # параллельность оценки

Шаги (повторный запуск безопасен — уже сделанное пропускается):
1. миграции и справочники (`alembic upgrade head`, `app.db.seed`);
2. учебные пакеты `fixtures/stage_0a` и `fixtures/demo_training` штатным импортом — с происхождением
   для реестра публикаций (правила `stage0a-training` и `demo-training`);
3. шесть профилей по ДИ и матрице (requirements-02): рабочие черновики загружаются как есть
   и НЕ утверждаются; их учебные копии утверждаются от учётки стенда `hr_demo` с основанием
   «учебный контур демо». Реальное кадровое утверждение остаётся отдельным действием HR;
4. первичная оценка откликов на Python и консультанта и кросс-оценка по всем учебным профилям;
5. сводка светофора по двум вакансиям — то, что увидит кадровик.

Все кандидаты вымышленные (is_synthetic). Модель видит только очищенный текст.
"""
import argparse
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "fixtures/requirement_profiles/all_six"
PACKAGES = [ROOT / "fixtures/stage_0a", ROOT / "fixtures/demo_training"]
DEMO_POSITIONS = ("python-dev", "hr-consultant")
CREATED_BY = "demo_setup"
APPROVER = "hr_demo"
BASIS = "Учебный контур демо: копия черновика по ДИ (requirements-02), не кадровое утверждение"
ICON = {"ready": "🟢", "clarify": "🟡", "not_met": "🔴", "needs_action": "⚪"}


def _assessments() -> int:
    from sqlalchemy import func

    from app.db.models import Assessment
    from app.db.session import SessionLocal
    with SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(Assessment)) or 0


def run(*args: str, progress: bool = False, tolerate: bool = False) -> None:
    """Шаг отдельным процессом. Длинный вывод — в лог, на экран — хвост и, для оценки,
    ход работы раз в 15 секунд (сколько оценок уже в базе), чтобы долгий шаг не выглядел зависшим."""
    print(f"\n$ {' '.join(args)}", flush=True)
    # В образе сервиса каталог кода только для чтения: на стенде журнал задаётся DEMO_SETUP_LOG.
    log = Path(os.environ.get("DEMO_SETUP_LOG") or ROOT / ".demo_setup.log")
    offset = log.stat().st_size if log.exists() else 0
    with open(log, "a", encoding="utf-8") as out:
        process = subprocess.Popen([sys.executable, *args], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, text=True)
        started, start_count = time.monotonic(), _assessments() if progress else 0
        while True:
            try:
                process.wait(timeout=15)
                break
            except subprocess.TimeoutExpired:
                if progress:
                    print(f"  … {int(time.monotonic() - started)} с, новых оценок: {_assessments() - start_count}",
                          flush=True)
    with open(log, encoding="utf-8") as written:
        written.seek(offset)
        tail = written.read().strip().splitlines()[-2:]
    for line in tail:
        print("  " + line[:200])
    if process.returncode != 0:
        message = f"шаг завершился с ошибкой (подробности в {log.name}): {' '.join(args)}"
        if not tolerate:
            raise SystemExit(message)
        print("  ⚠ " + message + " — остальные пары сохранены, повторный запуск продолжит")


def training_profiles() -> list[dict]:
    """Рабочие черновики — как есть; учебные копии — утверждённые. Возвращает, что сделано."""
    from app import requirements as api
    from app.db.models import Position, SourceDocument, User
    from app.db.session import SessionLocal
    from app.requirements.package import convert_profile, read_json, validate_sources

    package = read_json(PROFILES / "profiles.draft.json")
    manifest = read_json(PROFILES / "sources.json")
    done = []
    with SessionLocal() as session:
        try:
            api.load_package(session, package, manifest, PROFILES / "originals", created_by=CREATED_BY)
            session.commit()
        except api.RequirementError as error:
            if error.code != "version_conflict":
                raise
            session.rollback()  # рабочие черновики этих версий уже загружены
        sources = validate_sources(manifest, PROFILES / "originals")
        documents = {key: session.scalar(select(SourceDocument.id).where(SourceDocument.sha256 == item[0]["sha256"]))
                     for key, item in sources.items()}
        user = session.scalar(select(User).where(User.login == APPROVER))
        if user is None:
            raise SystemExit(f"нет учётки {APPROVER}: сначала python -m app.db.seed")
        for item in package["profiles"]:
            position = session.scalar(select(Position).where(Position.code == item["position_code"]))
            current = api.get_approved_profile(session, position.id, synthetic=True)
            if current is not None and current.created_by == CREATED_BY:
                done.append({"position_code": position.code, "version": current.version, "status": "already"})
                continue
            payload = convert_profile(item, sources, documents, Counter())
            draft = api.load_profile_draft(session, payload.model_copy(update={"is_synthetic": True}),
                                           created_by=CREATED_BY)
            api.approve_profile(session, draft.id, approved_by_user_id=user.id, approval_basis=BASIS)
            session.commit()
            done.append({"position_code": position.code, "version": draft.version, "status": "approved"})
    return done


def traffic_light() -> None:
    """Светофор по откликам учебных кандидатов на две демо-вакансии — как в списке кадровика."""
    from app.assessment.ranking import GROUP_TITLE, rank, rank_input
    from app.db.models import (
        Application,
        Candidate,
        Position,
        RequirementProfile,
        Vacancy,
    )
    from app.db.session import SessionLocal
    from app.postings.registry import get_default_registry
    from app.postings.service import resolve_application, resolved_state

    registry = get_default_registry()
    with SessionLocal() as session:
        for code in DEMO_POSITIONS:
            rows = session.execute(
                select(Application, Candidate).join(Candidate, Candidate.id == Application.candidate_id)
                .join(Vacancy, Vacancy.id == Application.vacancy_id).join(Position, Position.id == Vacancy.position_id)
                .where(Position.code == code, Candidate.is_synthetic.is_(True), Application.source == "response")
            ).all()
            items = []
            for application, candidate in rows:
                resolution = resolve_application(session, application.id, registry=registry)
                state = resolved_state(session, resolution, imported_position_code=code)
                profile = session.get(RequirementProfile, resolution.profile_id) if resolution.ready else None
                items.append(rank_input(key=candidate.code, candidate_code=candidate.code,
                                        assessment_status=str(state.status), applied_at=application.applied_at,
                                        assessment=state.assessment, profile=profile))
            print(f"\nВакансия {code}: откликов {len(items)}")
            for result in rank(items):
                place = f"{result.position:>2}" if result.position else " —"
                print(f"  {place} {ICON[result.group]} {result.key:<8} {GROUP_TITLE[result.group]}: {result.reason}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.demo_setup", description=__doc__.split("\n")[0])
    parser.add_argument("--no-llm", action="store_true", help="не вызывать модель: без оценки")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)

    run("-m", "alembic", "upgrade", "head")
    run("-m", "app.db.seed")
    for package in PACKAGES:
        run("-m", "app.ingest", "--input", str(package), "--mapping", str(package / "mapping.json"))
    print("\nПрофили по ДИ (учебные копии):")
    for row in training_profiles():
        print(f"  {row['position_code']:<18} v{row['version']}  {row['status']}")
    if not args.no_llm:
        workers = str(args.workers)
        for code in DEMO_POSITIONS:
            run("-m", "app.assessment", "batch", "--position-code", code, "--technical",
                "--skip-existing", "--workers", workers, progress=True, tolerate=True)
            run("-m", "app.assessment", "batch", "--all-approved", "--technical", "--position-code", code,
                "--skip-existing", "--workers", workers, progress=True, tolerate=True)
    traffic_light()
    print("\nГотово. API: uv run uvicorn app.main:app — учётка стенда hr_demo, контур training.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
