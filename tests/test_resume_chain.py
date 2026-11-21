"""HTTP contract regressions on PostgreSQL, with controlled LLM answers (not quality evidence)."""
import base64
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.ai import FakeLLMClient
from app.assessment.fixtures import FIXTURES_DIR, load, create_fixture_profile
from app.db.models import Application, User
from app.db.session import get_session
from app.db.enums import UserRole
from app.main import create_app
from tests import factories as f


@pytest.mark.parametrize("initial_failure", [False, True])
def test_file_to_vacancies_repeat_correction_and_access(session, monkeypatch, tmp_path, initial_failure):
    text = "Python-разработчик. Общий коммерческий опыт — 3 года. Написал API-тесты для сервиса заявок."
    fixture = load(FIXTURES_DIR / "py-9001.json")
    profile = create_fixture_profile(session, fixture)
    actor = f.make_user(session, login="stage2-hr")
    f.approve(session, profile, actor)
    department = f.make_user(session, role=UserRole.DEPARTMENT, login="stage2-dept")
    counter = []
    indicator = fixture["profile"]["competencies"][0]["indicators"][0]["key"]

    def answer(role, schema, system, user):
        counter.append(schema)
        if schema == "ExtractedFacts":
            return {"card": {}, "assertions": [{"kind":"activity", "statement":"Разработка API",
                "quote":"Написал API-тесты для сервиса заявок.", "polarity":"asserted"}], "limitations":[]}
        if schema == "FormalExtraction":
            return {"statement":{"years":3,"commercial":True,"quote":"Общий коммерческий опыт — 3 года."}}
        if schema == "CompetencyExtraction":
            if initial_failure and counter.count("CompetencyExtraction") == 1:
                from app.ai import LLMUnavailableError
                raise LLMUnavailableError("controlled provider outage")
            return {"indicators":[{"indicator_key":indicator,"status":"confirmed",
                                   "quote":"Написал API-тесты для сервиса заявок."}]}
        raise AssertionError(schema)

    monkeypatch.setattr("app.ai.build_client", lambda: FakeLLMClient(answer))
    monkeypatch.setenv("HR_RESUME_FILES", str(tmp_path))
    monkeypatch.delenv("HR_MATCHING_CATALOG_URL", raising=False)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        headers={"X-User-Login":actor.login}
        before=session.scalar(select(func.count()).select_from(Application))
        body={"filename":"resume.txt","contour":"training","content_base64":base64.b64encode(text.encode()).decode()}
        r=client.post("/api/v1/matching/resumes",json=body,headers=headers)
        assert r.status_code==201,r.text
        cid=r.json()["candidate_id"]
        assert client.post("/api/v1/matching/resumes",json=body,headers=headers).json()["candidate_id"]==cid
        request={"candidate_id":cid,"contour":"training"}
        first=client.post("/api/v1/matching/vacancies/current/process",json=request,headers=headers)
        if initial_failure:
            assert first.status_code == 503, first.text
            first=client.post("/api/v1/matching/vacancies/current/process",json=request,headers=headers)
            assert counter.count('ExtractedFacts') == 1
        assert first.status_code==200,first.text
        assert first.json()["result"]["items"]
        calls=len(counter)
        again=client.post("/api/v1/matching/vacancies/current/process",json=request,headers=headers)
        assert again.status_code==200,again.text
        assert len(counter)==calls
        assert session.scalar(select(func.count()).select_from(Application))==before
        assert client.post("/api/v1/matching/vacancies/current/process",json=request,
                           headers={"X-User-Login":department.login}).status_code==403
        assert client.get('/api/v1/matching/runs/'+first.json()['run_id'],headers=headers).status_code==200
        facts=client.get(f"/api/v1/matching/resumes/{cid}/facts/{first.json()['facts_id']}",headers=headers).json()
        correction={"expected_facts_id":facts['id'],"contour":"training","reason":"Уточнение извлечения",
            "corrected":{"card":facts['card'],"assertions":[{k:v for k,v in a.items() if k not in ('evidence','ambiguous_location')}
                for a in facts['assertions']],"limitations":["Подтверждена область чтения"]}}
        endpoint=f"/api/v1/matching/resumes/{cid}/facts/correct"
        assert client.post(endpoint,json=correction,headers=headers).status_code==200
        assert client.post(endpoint,json=correction,headers=headers).status_code==409
        revised=client.post("/api/v1/matching/vacancies/current/process",json=request,headers=headers)
        assert revised.status_code==200,revised.text
        assert counter.count('ExtractedFacts')==1
        assert revised.json()['facts_id']!=facts['id']
        new_text=client.post(f"/api/v1/matching/resumes/{cid}/text",json={
            "expected_text_id":r.json()['text_id'], "text":text+' Изучаю SQL.',
            "reason":"Новая версия сведений", "contour":"training"},headers=headers)
        assert new_text.status_code==200,new_text.text
        old=client.get('/api/v1/matching/runs/'+first.json()['run_id'],headers=headers)
        assert old.json()['source_is_current'] is False
        after=client.post("/api/v1/matching/vacancies/current/process",json=request,headers=headers)
        assert after.status_code==200,after.text
        assert counter.count('ExtractedFacts')==2
        from app.db.models import Vacancy
        from app.db.enums import VacancyStatus
        for vacancy in session.scalars(select(Vacancy)):
            vacancy.status=VacancyStatus.CLOSED
        session.flush()
        empty=client.post("/api/v1/matching/vacancies/current/process",json=request,headers=headers)
        assert empty.status_code==200,empty.text
        assert empty.json()['catalog_count']==0 and empty.json()['run_id']
