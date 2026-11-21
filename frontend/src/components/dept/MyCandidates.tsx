import React, { useEffect, useState } from 'react';
import { Card, Btn, Badge, PageTitle } from '../shared/ui';
import { api, request, recruitmentContour, deadlineLabel, feedbackLabel, errorMessage, type Handoff, type HandoffDetail } from '../../api/recruitment';
import RecruitmentSummary from '../shared/RecruitmentSummary';
export const MyCandidates: React.FC = () => {
  const [items, setItems] = useState<Handoff[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<HandoffDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);
  const [outcome, setOutcome] = useState('fit');
  const [interview, setInterview] = useState('not_reported');
  const [comment, setComment] = useState('');
  const [reason, setReason] = useState('');
  // Codes are defined by the legacy seed; department cannot read the HR-only reference endpoint.
  const reasons = [{ code: 'experience', title: 'Недостаточно опыта' }, { code: 'other', title: 'Другая причина (пояснить)' }];
  useEffect(() => {
    let live = true; setLoading(true); setError('');
    api.handoffs('dept').then(({ items: rows }) => { if (live) { setItems(rows); setSelectedId(id => rows.some(r => r.attempt_id === id) ? id : rows[0]?.attempt_id || ''); setLoading(false); } }).catch(e => { if(live) { setItems([]); setSelectedId(''); setError(errorMessage(e)); setLoading(false); } });
    return () => { live = false; };
  }, [reload]);
  useEffect(() => {
    let live = true; setDetail(null); setComment(''); setReason(''); setOutcome('fit'); setInterview('not_reported');
    if (selectedId) api.handoff(selectedId, 'dept').then(d => { if(live) setDetail(d); }).catch(e => { if(live) setError(errorMessage(e)); });
    return () => { live = false; };
  }, [selectedId, reload]);
  const submit = async () => {
    if (!detail) return; setBusy(true); setError('');
    try {
      await request(`/applications/${detail.application_id}/feedback`, 'dept', { attempt_id: detail.attempt_id, outcome, interview_status: interview, contact_status: interview === 'yes' ? 'yes' : 'not_reported', comment, rejection_reason_code: outcome === 'not_fit' ? reason : null, supersedes_id: detail.latest_feedback?.feedback_id || null, request_id: crypto.randomUUID() });
      setNotice('Ответ сохранён и доступен HR. Итог рассмотрения принимает HR.'); setReload(n => n + 1);
    } catch(e) { setError(errorMessage(e)); } finally { setBusy(false); }
  };
  return <div data-tour="dept-page" className="max-w-[1240px] mx-auto px-6 py-8 space-y-5"><PageTitle title="Кандидаты, направленные к вам" subtitle={`${recruitmentContour === 'training' ? 'Учебный кабинет · ' : ''}Вы видите только свои передачи. Ответ сохраняется у конкретной передачи.`} right={<Btn onClick={() => setReload(n => n + 1)}>Обновить</Btn>} />
    {error && <div role="alert" className="bg-red-50 text-red-800 rounded-xl p-4">{error} <Btn onClick={() => setReload(n => n + 1)}>Повторить</Btn></div>}{notice && <p role="status" className="bg-[#E3F2E7] text-[#1D7A40] p-4 rounded-xl">{notice}</p>}
    <p className="text-[#4A5363]">Просрочено: <b className="text-[#A3171B]">{items.filter(i => i.deadline_status === 'overdue').length}</b></p>
    {loading ? <Card>Загрузка передач…</Card> : !items.length ? <Card>Вам пока не направляли кандидатов.</Card> : <div className="grid lg:grid-cols-[360px_1fr] gap-5 items-start"><div data-tour="dept-candidates-list" className="min-w-0"><Card className="space-y-3 !p-3">{items.map(i => <button key={i.attempt_id} className={`w-full flex gap-4 text-left rounded-xl border p-3 ${i.attempt_id === selectedId ? 'border-[#1F4FD1] bg-[#EEF3FE]' : 'border-[#E1E5EB] bg-white'}`} onClick={() => { setSelectedId(i.attempt_id); setNotice(''); }}><div className={`w-14 h-14 shrink-0 rounded-xl flex flex-col items-center justify-center ${i.deadline_status === 'overdue' ? 'bg-[#FCE8E8] text-[#A3171B]' : 'bg-[#F3F5F8]'}`}><b className="text-xl">{i.due_date.slice(8)}</b><span className="text-xs">{new Date(i.due_date).toLocaleDateString('ru-RU', { month: 'short' })}</span></div><div><b>{i.candidate_code}</b><p className="text-sm">{i.vacancy_title}</p><p className="text-sm mt-1">{deadlineLabel(i.deadline_status)}</p></div></button>)}</Card></div>
      <div data-tour="dept-candidate-detail" className="min-w-0"><Card className="space-y-5 min-w-0">{!detail ? <p>{error ? 'Сводка недоступна' : 'Загрузка сводки…'}</p> : <><h2 className="text-[22px] font-bold">{detail.candidate_code} · {detail.vacancy_title}</h2><p className="text-sm text-[#4A5363]">Направлен {new Date(detail.handed_off_at).toLocaleDateString('ru-RU')} · срок до {detail.due_date}</p><Badge tone="blue">{deadlineLabel(detail.deadline_status)}</Badge><div data-tour="dept-candidate-summary" className="max-h-96 overflow-auto"><RecruitmentSummary summary={detail.summary} /></div>
      {detail.latest_feedback && <div className="rounded-xl border border-[#9FD0AC] bg-[#E3F2E7] p-4"><b>Сохранён ответ: {feedbackLabel(detail.latest_feedback.outcome)}</b><p>{detail.latest_feedback.rejection_reason?.title} · {detail.latest_feedback.comment}</p></div>}
      {detail.status !== 'closed_without_response' && <div data-tour="dept-feedback-form" className="space-y-4 border-t pt-4"><h3 className="font-bold text-lg">{detail.latest_feedback ? 'Уточнить ответ' : 'Ответ сотруднику по подбору персонала'}</h3><label className="block">Результат<select className="block w-full border rounded-xl p-3 mt-2" value={outcome} onChange={e => setOutcome(e.target.value)}><option value="fit">Подошёл</option><option value="not_fit">Не подошёл</option><option value="pending">Рассмотрение продолжается</option></select></label><label className="block">Собеседование состоялось<select className="block w-full border rounded-xl p-3 mt-2" value={interview} onChange={e => setInterview(e.target.value)}><option value="not_reported">Не сообщено</option><option value="yes">Да</option><option value="no">Нет</option></select></label>{outcome === 'not_fit' && <select aria-label="Причина отказа" className="w-full border rounded-xl p-3" value={reason} onChange={e => setReason(e.target.value)}><option value="">Выберите причину</option>{reasons.map(r => <option key={r.code} value={r.code}>{r.title}</option>)}</select>}<textarea aria-label="Комментарий подразделения" className="w-full border rounded-xl p-3 min-h-28" placeholder="Причина и следующий шаг" value={comment} onChange={e => setComment(e.target.value)} /><Btn variant="primary" disabled={busy || !comment.trim() || (outcome === 'not_fit' && !reason)} onClick={submit}>Сохранить ответ и передать HR</Btn></div>}</> }</Card></div></div>}
  </div>;
};
export default MyCandidates;


