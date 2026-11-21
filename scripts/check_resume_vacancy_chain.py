"""Short real HTTP check on a dedicated *_test database and synthetic resume.

Run: python -m scripts.check_resume_vacancy_chain --env-file deploy/local/resume-chain.env
Never prints credentials or request headers. Does not drop any database.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    args = parser.parse_args()
    load_dotenv(args.env_file, override=True)
    from sqlalchemy import create_engine, select, func, make_url
    from sqlalchemy.orm import Session
    from alembic import command
    from alembic.config import Config
    from app.db.seed import seed_all
    from app.db.models import Application, User, Assessment
    from app.assessment.artifacts import ProcessingArtifact
    from app.assessment.fixtures import load, create_fixture_profile, FIXTURES_DIR
    from app.db import repository as repo
    from app.db.enums import UserRole

    url = os.environ["DATABASE_URL"]
    assert (make_url(url).database or "").endswith("_test")
    config = Config("alembic.ini")
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    engine = create_engine(url)
    with Session(engine) as session:
        seed_all(session)
        actor = session.scalar(select(User).where(User.role == UserRole.HR, User.is_active))
        assert actor is not None
        login = actor.login
        department = session.scalar(select(User).where(User.role == UserRole.DEPARTMENT, User.is_active))
        from app.db.models import Position
        position = session.scalar(select(Position).where(Position.code == "python-dev"))
        profile = repo.get_approved_profile(session, position.id, synthetic=True)
        if profile is None:
            profile = create_fixture_profile(session, load(FIXTURES_DIR / "py-9001.json"))
            repo.approve_requirement_profile(session, profile.id, approved_by_user_id=actor.id,
                                            approval_basis="Synthetic stage 2 HTTP check")
        session.commit()
        before = session.scalar(select(func.count()).select_from(Application))
        department_login = department.login
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, LLM_TIMEOUT_SEC="120")
    log_path = Path("deploy/local/resume-chain-server.log")
    summary = {"synthetic": True, "provider": os.environ.get("LLM_PROVIDER", "yandexgpt"),
               "model": os.environ.get("LLM_ASSESS_MODEL", "configured-yandex"), "checks": []}

    def start():
        log = log_path.open("a", encoding="utf-8")
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
            "--port", str(port), "--log-level", "warning"], env=env, stdout=log, stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("HTTP server failed; see local server log")
            try:
                if httpx.get(f"http://127.0.0.1:{port}/openapi.json").status_code == 200:
                    return process, log
            except httpx.TransportError:
                pass
            time.sleep(.1)
        process.terminate()
        process.wait()
        log.close()
        raise RuntimeError("Server startup timed out")

    process, log = start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=240,
                          headers={"X-User-Login": login}) as client:
            resume = "Python-разработчик. Работал разработчиком с января 2022 по декабрь 2024. Общий коммерческий опыт — 3 года. Написал API-тесты для сервиса заявок. Использовал Python и PostgreSQL."
            payload = {"filename": "synthetic-resume.txt", "contour": "training",
                       "content_base64": base64.b64encode(resume.encode()).decode()}
            r = client.post("/api/v1/matching/resumes", json=payload)
            assert r.status_code == 201, r.text
            uploaded = r.json()
            assert uploaded["status"] == "ready", uploaded
            candidate_id = uploaded["candidate_id"]
            assert client.post("/api/v1/matching/resumes", json=payload).json()["candidate_id"] == candidate_id
            request = {"candidate_id": candidate_id, "contour": "training"}
            r = client.post("/api/v1/matching/vacancies/current/process", json=request)
            assert r.status_code == 200, r.text
            first = r.json()
            assert first["result"]["items"] and first["facts_id"], first
            with Session(engine) as session:
                count = session.scalar(select(func.count()).select_from(Assessment))
                assert session.scalar(select(func.count()).select_from(Application)) == before
            second = client.post("/api/v1/matching/vacancies/current/process", json=request)
            assert second.status_code == 200, second.text
            assert second.json()["processed_profiles"] == []
            assert second.json()["reused_profiles"]
            with Session(engine) as session:
                assert session.scalar(select(func.count()).select_from(Assessment)) == count
            assert client.post("/api/v1/matching/vacancies/current/process", json=request,
                               headers={"X-User-Login": department_login}).status_code == 403
            facts_url = f"/api/v1/matching/resumes/{candidate_id}/facts/{first['facts_id']}"
            facts = client.get(facts_url)
            assert facts.status_code == 200
            facts = facts.json()
            corrected = {"card": facts["card"], "assertions": [{k: v for k, v in a.items()
                         if k not in ("evidence", "ambiguous_location")} for a in facts["assertions"]],
                         "limitations": facts["limitations"] + ["HR verified extraction on synthetic input"]}
            correction = {"expected_facts_id": facts["id"], "corrected": corrected,
                          "reason": "Synthetic source review", "contour": "training"}
            endpoint = f"/api/v1/matching/resumes/{candidate_id}/facts/correct"
            updated = client.post(endpoint, json=correction)
            assert updated.status_code == 200, updated.text
            assert client.post(endpoint, json=correction).status_code == 409
            summary.update(candidate_id=candidate_id, facts_id=first["facts_id"], run_id=first["run_id"],
                           corrected_facts_id=updated.json()["id"], catalog_count=first["catalog_count"],
                           checks=["upload_without_application", "upload_repeat", "live_catalog_assessment",
                                   "reuse_without_new_assessment", "department_403", "fact_correction", "stale_correction_409"])
            process.terminate(); process.wait(timeout=10); log.close()
            process, log = start()
            assert client.get(facts_url).json() == facts
            stored_run = client.get('/api/v1/matching/runs/' + first['run_id'])
            assert stored_run.status_code == 200 and stored_run.json()['result'] == first['result']
            summary["checks"].append("restart_preserves_evidence")
            summary["checks"].append("restart_preserves_run")
    finally:
        if process.poll() is None:
            process.terminate(); process.wait(timeout=10)
        log.close()
    Path("deploy/local/resume-chain-result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
