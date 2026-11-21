"""Focused live recruitment check; writes only to the explicitly isolated archive_demo DB."""
import json
import os
import sys
from pathlib import Path
from datetime import date, timedelta
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from sqlalchemy import select
from app.db.session import SessionLocal
from app.db import repository as repo
from app.db.models import Candidate, User, Vacancy, Position, Application
from app.db.enums import ApplicationSource
assert '15439/archive_demo' in os.environ.get('DATABASE_URL', ''), 'isolated database required'
with SessionLocal() as session:
    recipient = session.scalar(select(User).where(User.login == 'dept_demo'))
    candidate = session.scalar(select(Candidate).where(Candidate.code == 'search-9002', Candidate.is_synthetic.is_(True)))
    vacancy = session.scalar(select(Vacancy).join(Position).where(Position.code == 'python-dev'))
    application = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE, vacancy_id=vacancy.id, posting_title='Учебный маршрут передачи и обратной связи', applied_at=date.today())
    session.commit()
    application_id, recipient_id = str(application.id), str(recipient.id)
with httpx.Client(base_url='http://127.0.0.1:18400/api/v1', headers={'X-User-Login':'hr_demo'}, timeout=20) as client:
    def call(method, path, status=200, **kwargs):
        response=client.request(method,path,**kwargs)
        assert response.status_code == status, (path,response.status_code,response.text)
        return response.json()
    d=call('GET',f'/applications/{application_id}')
    text=call('GET',f"/candidate-texts/{d['candidate']['current_text_id']}")
    history=call('GET',f'/applications/{application_id}/history')
    summary=call('GET',f'/applications/{application_id}/handoff-summary')
    assert not call('GET',f'/applications/{application_id}/handoffs')['items']
    moved=call('POST',f'/applications/{application_id}/stage',201,json={'to_stage_code':'sent_to_department','expected_seq':history['last_seq'],'confirm_skip':True,'comment':'Учебная проверка адресной передачи без смены правил отбора','handoff':{'recipient_user_id':recipient_id,'channel':'cabinet','summary_revision':summary['summary_revision'],'request_id':str(uuid4())}})
    attempt=moved['handoff']
    new_due=(date.fromisoformat(attempt['due_date'])+timedelta(days=7)).isoformat()
    call('POST',f"/applications/{application_id}/handoffs/{attempt['attempt_id']}/deadline",201,json={'new_due_date':new_due,'expected_due_date':attempt['due_date'],'reason_code':'other','comment':'Учебный перенос встречи подразделения','request_id':str(uuid4())})
    dept={'X-User-Login':'dept_demo'}
    mine=call('GET','/handoffs?contour=training',headers=dept)
    assert any(a['attempt_id']==attempt['attempt_id'] for a in mine['items'])
    feedback=call('POST',f'/applications/{application_id}/feedback',201,headers=dept,json={'attempt_id':attempt['attempt_id'],'outcome':'fit','interview_status':'yes','contact_status':'yes','comment':'Учебное собеседование состоялось, кандидат подходит для следующего шага','request_id':str(uuid4())})
    reread=call('GET',f'/applications/{application_id}/handoffs')['items'][0]
    assert reread['latest_feedback']['feedback_id']==feedback['feedback']['feedback_id']
    assert reread['due_date']==new_due
    assert call('GET',f'/applications/{application_id}')['stage']['code']=='sent_to_department'
    history=call('GET',f'/applications/{application_id}/history')
    call('POST',f'/applications/{application_id}/stage',201,json={'to_stage_code':'documents','expected_seq':history['last_seq'],'confirm_skip':True,'comment':'HR учёл положительный ответ подразделения и начал оформление'})
    assert call('GET',f'/applications/{application_id}')['stage']['code']=='documents'
    missing=client.get('/candidate-texts/'+str(uuid4()))
    assert missing.status_code==404
    guide=client.post(f'/applications/{application_id}/interview-guide',json={'kind':'phone','regenerate':False,'request_id':str(uuid4())})
    print(json.dumps({'application_id':application_id,'recipient_id':recipient_id,'source_chars':len(text['text']),'attempt_id':attempt['attempt_id'],'final_stage':'documents','checks':'summary does not mutate; handoff; deadline; scoped department read; persisted feedback; independent HR decision; missing source 404','interview_guide_status':guide.status_code,'interview_guide_result':guide.json().get('error')},ensure_ascii=False))
