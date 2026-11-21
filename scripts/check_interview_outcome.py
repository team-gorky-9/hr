"""Короткий HTTP-проход итога телефонной встречи (wave-2-stage-1, раздел «Илья») на учебных данных.

Нужны база из .env (DATABASE_URL) после `alembic upgrade head` и запущенный API
(`uv run uvicorn app.main:app`). Модель не вызывается: открытую встречу создаёт существующий
repo.open_interview — тот же путь, которым её открывает генерация гайда.

    uv run python scripts/check_interview_outcome.py                       # py-9101 и py-9102
    uv run python scripts/check_interview_outcome.py --held py-9103 --no-answer py-9104 --base-url http://127.0.0.1:8000

Повторный запуск на тех же кандидатах печатает уже записанный итог (повтор команды не создаёт факт)."""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import repository as repo  # noqa: E402
from app.db.enums import ApplicationSource  # noqa: E402
from app.db.models import Application, Candidate, Interview  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

HR = {"X-User-Login": "hr_demo"}
MSK = timezone(timedelta(hours=3))


def phone_interview(code: str) -> tuple[str, str]:
    """Отклик учебного кандидата и его телефонная встреча: открытая, а если её нет — последняя завершённая."""
    with SessionLocal() as session:
        application = session.scalar(
            select(Application).join(Candidate, Candidate.id == Application.candidate_id)
            .where(Candidate.code == code, Candidate.is_synthetic.is_(True),
                   Application.source == ApplicationSource.RESPONSE))
        if application is None:
            raise SystemExit(f"нет учебного отклика {code}: сначала python -m scripts.demo_setup --no-llm")
        interview = repo.latest_interview(session, application.id, "phone")
        if interview is None:
            interview = repo.open_interview(session, application.id, "phone")
            session.commit()
        return str(application.id), str(interview.id)


def show(label: str, response: httpx.Response) -> dict:
    body = response.json()
    print(f"• {label}: {response.request.method} {response.request.url.path} → {response.status_code}")
    print("  ", {k: body.get(k) for k in ("result", "held_at", "attempt_at", "interviewer_user_id", "revision")}
          if "result" in body else body)
    return body


def outcome(http: httpx.Client, interview_id: str, result: str, when: datetime, summary: str, revision: int = 1):
    return http.post(f"/api/v1/interviews/{interview_id}/outcome", headers=HR, json={
        "expected_revision": revision, "result": result, "occurred_at": when.isoformat(), "summary": summary})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--held", default="py-9101", help="кандидат, с которым разговор состоялся")
    parser.add_argument("--no-answer", default="py-9102", help="кандидат, который не ответил")
    args = parser.parse_args(argv)
    when = datetime.now(MSK).replace(second=0, microsecond=0) - timedelta(minutes=30)
    http = httpx.Client(base_url=args.base_url, timeout=10)

    application_id, interview_id = phone_interview(args.held)
    print(f"{args.held}: application {application_id}, interview {interview_id}")
    summary = "Опыт с API-тестами подтвердил, готов к собеседованию в департаменте (учебно)"
    first = show("итог continue", outcome(http, interview_id, "continue", when, summary))
    if first.get("error", {}).get("code") == "INTERVIEW_ALREADY_COMPLETED":
        print("   встреча уже завершена ранее — ниже её сохранённый итог")
    else:
        show("повтор той же команды", outcome(http, interview_id, "continue", when, summary))
    show("перечитать встречи отклика",
         http.get(f"/api/v1/applications/{application_id}/interviews", headers=HR))
    show("иной итог той же встречи", outcome(http, interview_id, "stop", when, "Передумали (учебно)", revision=2))
    show("роль department", http.post(f"/api/v1/interviews/{interview_id}/outcome",
                                      headers={"X-User-Login": "dept_demo"}, json={}))

    application_id, interview_id = phone_interview(args.no_answer)
    print(f"{args.no_answer}: application {application_id}, interview {interview_id}")
    show("итог no_answer", outcome(http, interview_id, "no_answer", when, "Не взял трубку, перезвонить (учебно)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
