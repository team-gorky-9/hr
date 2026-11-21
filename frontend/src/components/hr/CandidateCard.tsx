import React, { useEffect, useState } from 'react';
import { Card, Btn, Badge, PageTitle } from '../shared/ui';
import { api, request, recipientId, resultLabel, assessmentLabel, deadlineLabel, feedbackLabel, errorMessage, type ApplicationDetail, type History, type Handoff, type Stage, type Reason, type Evidence } from '../../api/recruitment';

interface CandidateCardProps {
  candidateId?: string; initialLoading?: boolean; onBack?: () => void; onRequestClarification?: () => void;
  onReject?: () => void; onSendToHead?: () => void; onSaveToReserve?: () => void; onManualCheck?: () => void; onReevaluate?: () => void;
}
const field = 'w-full border border-[#C9D0DB] rounded-xl px-4 py-3 text-[14px] bg-white';
export const CandidateCard: React.FC<CandidateCardProps> = ({ candidateId = '', onBack, onRequestClarification }) => {
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [stages, setStages] = useState<Stage[]>([]);
  const [reasons, setReasons] = useState<Reason[]>([]);
  const [source, setSource] = useState<{ text: string; version: number; is_current: boolean } | null>(null);
  const [sourceError, setSourceError] = useState('');
  const [highlight, setHighlight] = useState<Evidence | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);
  const [panel, setPanel] = useState<'stage' | 'handoff' | null>(null);
  const [target, setTarget] = useState('');
  const [reason, setReason] = useState('');
  const [comment, setComment] = useState('');
  const [confirmSkip, setConfirmSkip] = useState(false);
  const recipient = recipientId;
  const [summary, setSummary] = useState<{ summary_revision: string; markdown: string } | null>(null);
  const [newDate, setNewDate] = useState('');
  const [extensionComment, setExtensionComment] = useState('');
  const [selectedAttempt, setSelectedAttempt] = useState('');
  const [attemptDetail, setAttemptDetail] = useState<Handoff | null>(null);
  useEffect(() => {
    let live = true;
    setLoading(true); setError(''); setDetail(null); setSource(null); setHighlight(null); setSourceError('');
    Promise.all([api.application(candidateId), api.history(candidateId), api.applicationHandoffs(candidateId), api.stages(), api.reasons()])
      .then(async ([d, h, attempts, s, r]) => {
        if (!live) return;
        setDetail(d); setHistory(h); setHandoffs(attempts.items); setStages(s.items); setReasons(r.items); setLoading(false);
        if (d.candidate.current_text_id) {
          try { const text = await api.source(d.candidate.current_text_id); if (live) setSource(text); }
          catch (e) { if (live) setSourceError(errorMessage(e)); }
        } else setSourceError('У кандидата нет доступного текста источника.');
      }).catch(e => { if (live) { setError(errorMessage(e)); setLoading(false); } });
    return () => { live = false; };
  }, [candidateId, reload]);
  const action = async (work: () => Promise<void>) => {
    setBusy(true); setError(''); setNotice('');
    try { await work(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  };
  const openHandoff = () => action(async () => { setSummary(await api.summary(candidateId)); setPanel('handoff'); });
  const sendHandoff = () => action(async () => {
    if (!summary || !history || !detail) return;
    const handoff = { recipient_user_id: recipient, channel: 'cabinet', summary_revision: summary.summary_revision, request_id: crypto.randomUUID() };
    if (['sent_to_department', 'department_interview'].includes(detail.stage.code)) {
      await request(`/applications/${candidateId}/handoffs`, 'hr', { expected_seq: history.last_seq || 0, handoff });
    } else {
      await request(`/applications/${candidateId}/stage`, 'hr', { to_stage_code: 'sent_to_department', expected_seq: history.last_seq || 0, comment, confirm_skip: confirmSkip, handoff });
    }
    setPanel(null); setComment(''); setNotice('Передача сохранена. Получатель видит сводку и срок в своём кабинете.'); setReload(n => n + 1);
  });
  const moveStage = () => action(async () => {
    await request(`/applications/${candidateId}/stage`, 'hr', { to_stage_code: target, expected_seq: history?.last_seq || 0, comment, confirm_skip: confirmSkip, rejection_reason_code: ['rejected', 'withdrawn'].includes(target) ? reason : null });
    setPanel(null); setComment(''); setNotice('Решение HR сохранено в истории.'); setReload(n => n + 1);
  });
  const showEvidence = (e: Evidence) => action(async () => { setSource(await api.source(e.candidate_text_id)); setHighlight(e); setSourceError(''); });
  const extend = (attempt: Handoff) => action(async () => {
    await request(`/applications/${candidateId}/handoffs/${attempt.attempt_id}/deadline`, 'hr', { new_due_date: newDate, expected_due_date: attempt.due_date, reason_code: 'other', comment: extensionComment, request_id: crypto.randomUUID() });
    setSelectedAttempt(''); setNotice('Новый срок и причина сохранены.'); setReload(n => n + 1);
  });
  if (loading || !detail) return <div className="max-w-[1240px] mx-auto p-8 space-y-4"><Btn onClick={onBack}>← Отклики</Btn><p role={error ? 'alert' : undefined}>{error || 'Загрузка карточки…'}</p>{error && <Btn onClick={() => setReload(n => n + 1)}>Повторить</Btn>}</div>;
  return <div className="max-w-[1240px] mx-auto px-6 py-6 space-y-5">
    <Btn variant="link" onClick={onBack}>← Отклики · {detail.vacancy?.title || detail.posting_title}</Btn>
    <PageTitle title={detail.candidate.code} subtitle={detail.candidate.headline || detail.vacancy?.title || 'Карточка отклика'} right={<Badge tone="blue">{detail.stage.title}</Badge>} />
    <p className="text-sm text-[#616977]">{detail.candidate.is_training ? 'Учебная запись · ' : ''}Персональные данные скрыты</p>
    {error && <div role="alert" className="p-4 bg-red-50 text-red-800 rounded-xl">{error} <Btn onClick={() => setReload(n => n + 1)}>Перечитать</Btn></div>}
    {notice && <div role="status" className="p-4 bg-[#E3F2E7] text-[#1D7A40] rounded-xl">{notice}</div>}
    <div className="grid grid-cols-[1.15fr_1fr] gap-6 items-start">
      <div className="space-y-5">
        <Card className="space-y-4"><h2 className="text-xl font-bold">Результат рассмотрения</h2><Badge tone={detail.assessment?.is_stale ? 'amber' : 'blue'}>{assessmentLabel(detail.assessment_status)}</Badge><p>{detail.assessment?.summary || 'Нет готового вывода. Отсутствие сведений не означает несоответствие.'}</p>
          <h3 className="font-bold">Обязательные требования</h3>
          {detail.assessment?.formal_checks.length ? detail.assessment.formal_checks.map(c => <div key={c.requirement_id} className="border border-[#E1E5EB] rounded-xl p-4 space-y-2"><div className="font-semibold">{c.description}</div><Badge tone={c.result === 'met' ? 'green' : c.result === 'not_met' ? 'red' : 'amber'}>{resultLabel(c.result)}{c.is_preliminary ? ' · предварительно' : ''}</Badge><p className="text-sm">{c.explanation}</p>{c.evidence.map((e, i) => <button key={i} onClick={() => showEvidence(e)} className="block text-left text-sm text-[#1F4FD1]">«{e.quote}» ↗</button>)}</div>) : <p className="text-[#616977]">Требования ещё не оценены.</p>}
          <h3 className="font-bold">Компетенции и основания</h3>
          {detail.assessment?.competency_scores.map((c, i) => <div key={i} className="border border-[#E1E5EB] rounded-xl p-4"><b>{c.name}</b><p className="text-sm mt-2">{c.explanation || 'Сведений недостаточно'}</p>{c.evidence.map((e, j) => <button key={j} onClick={() => showEvidence(e)} className="block text-left text-sm text-[#1F4FD1] mt-2">«{e.quote}» ↗</button>)}</div>)}
        </Card>
        <Card className="space-y-3"><h2 className="text-xl font-bold">Действия HR</h2><div className="flex flex-wrap gap-3"><Btn variant="primary" disabled={busy || detail.stage.is_final || history?.source !== 'response'} onClick={onRequestClarification}>Телефонное интервью</Btn><Btn disabled={busy || detail.stage.is_final || history?.source !== 'response'} onClick={openHandoff}>Передать руководителю</Btn><Btn disabled={busy || detail.stage.is_final || history?.source !== 'response'} onClick={() => { setPanel('stage'); setTarget(''); setComment(''); }}>Изменить этап / решение</Btn><Btn onClick={() => setReload(n => n + 1)}>Обновить</Btn></div><p className="text-sm text-[#616977]">Ответ подразделения сохраняется отдельно. Итоговое решение принимает HR.</p>
          {panel === 'stage' && <div className="space-y-3 border-t pt-4"><select aria-label="Новый этап" className={field} value={target} onChange={e => setTarget(e.target.value)}><option value="">Выберите этап</option>{stages.filter(s => s.code !== 'sent_to_department' && s.code !== detail.stage.code).map(s => <option key={s.code} value={s.code}>{s.title}</option>)}</select>{['rejected', 'withdrawn'].includes(target) && <select aria-label="Причина решения" className={field} value={reason} onChange={e => setReason(e.target.value)}><option value="">Выберите причину</option>{reasons.filter(r => target !== 'withdrawn' || r.side === 'candidate').map(r => <option key={r.code} value={r.code}>{r.title}</option>)}</select>}<textarea aria-label="Обоснование решения" className={field} placeholder="Обоснование решения" value={comment} onChange={e => setComment(e.target.value)} /><label className="block text-sm"><input type="checkbox" checked={confirmSkip} onChange={e => setConfirmSkip(e.target.checked)} /> Подтверждаю возврат или пропуск этапов с указанной причиной</label><Btn variant="primary" disabled={busy || !target || !comment.trim() || (['rejected', 'withdrawn'].includes(target) && !reason)} onClick={moveStage}>Сохранить решение</Btn></div>}
          {panel === 'handoff' && <div className="space-y-3 border-t pt-4"><h3 className="font-bold">Сводка перед отправкой</h3><pre className="whitespace-pre-wrap text-sm max-h-64 overflow-auto bg-[#F6F7F9] p-4 rounded-xl">{summary?.markdown}</pre><p className="text-sm">{recipient ? 'Получатель: представитель департамента (учебная учётная запись стенда)' : 'Получатель кабинета не настроен. Передача пока недоступна.'}</p><textarea className={field} placeholder="Комментарий HR и основание перехода" value={comment} onChange={e => setComment(e.target.value)} /><label className="block text-sm"><input type="checkbox" checked={confirmSkip} onChange={e => setConfirmSkip(e.target.checked)} /> Подтверждаю пропуск этапов с указанной причиной</label><p className="text-sm text-[#616977]">Срок ответа рассчитывается сервером: 10 рабочих дней. Просмотр сводки не создаёт передачу.</p><Btn variant="primary" disabled={busy || !recipient || !comment.trim()} onClick={sendHandoff}>Подтвердить передачу</Btn></div>}
        </Card>
      </div>
      <Card className="space-y-4 sticky top-4"><h2 className="text-xl font-bold">Текст источника</h2>{sourceError ? <p role="alert">{sourceError}</p> : source ? <><p className="text-sm text-[#616977]">Версия {source.version} · {source.is_current ? 'текущая' : 'предыдущая'}</p><pre className="whitespace-pre-wrap font-sans text-[14px] leading-7 max-h-[650px] overflow-auto">{highlight ? <>{source.text.slice(0, highlight.utf16_start)}<mark className="bg-[#FFF4CC]">{source.text.slice(highlight.utf16_start, highlight.utf16_end)}</mark>{source.text.slice(highlight.utf16_end)}</> : source.text}</pre></> : <p>Загрузка источника…</p>}</Card>
    </div>
    <Card className="space-y-4"><h2 className="text-xl font-bold">Передачи и ответы подразделения</h2>{!handoffs.length && <p>Передач пока нет.</p>}{handoffs.map(a => <div key={a.attempt_id} className="border border-[#E1E5EB] p-4 rounded-xl space-y-3"><div className="flex justify-between"><b>{a.recipient_name} · {a.recipient_department}</b><Badge tone={a.deadline_status === 'overdue' ? 'red' : 'blue'}>{deadlineLabel(a.deadline_status)}</Badge></div><p className="text-sm">Передан {new Date(a.handed_off_at).toLocaleString('ru-RU')} · срок {a.due_date} · переносов {a.extensions_count}</p>{a.latest_feedback && <p className="bg-[#E3F2E7] rounded-xl p-3">{feedbackLabel(a.latest_feedback.outcome)} · {a.latest_feedback.rejection_reason?.title} {a.latest_feedback.comment}</p>}<div className="flex gap-3"><Btn onClick={() => action(async () => setAttemptDetail(await api.handoff(a.attempt_id, 'hr')))}>Сводка и история</Btn>{a.status === 'awaiting_response' && <Btn onClick={() => { setSelectedAttempt(a.attempt_id); setNewDate(''); setExtensionComment(''); }}>Перенести срок</Btn>}</div>{selectedAttempt === a.attempt_id && <div className="flex gap-3"><input aria-label="Новый срок" type="date" className={field} min={a.due_date} value={newDate} onChange={e => setNewDate(e.target.value)} /><input aria-label="Причина переноса" className={field} placeholder="Причина переноса" value={extensionComment} onChange={e => setExtensionComment(e.target.value)} /><Btn disabled={busy || !newDate || !extensionComment.trim()} onClick={() => extend(a)}>Сохранить</Btn></div>}</div>)}
      {attemptDetail && <div className="bg-[#F6F7F9] rounded-xl p-4 space-y-3"><Btn onClick={() => setAttemptDetail(null)}>Закрыть сводку</Btn><pre className="whitespace-pre-wrap font-sans text-sm">{attemptDetail.markdown}</pre>{attemptDetail.feedback_history?.map(f => <p key={f.feedback_id}>{new Date(f.received_at).toLocaleString('ru-RU')} · {feedbackLabel(f.outcome)} · {f.comment}</p>)}{attemptDetail.deadline_extensions?.map((e, i) => <p key={i}>{e.previous_due_date} → {e.new_due_date} · {e.reason_title} · {e.comment}</p>)}</div>}
    </Card>
    <Card><h2 className="text-xl font-bold mb-4">История этапов</h2><div className="space-y-3">{history?.items.map(e => <div key={e.seq} className="border-b border-[#E1E5EB] pb-3"><b>{e.to_stage.title}</b> · {new Date(e.created_at).toLocaleString('ru-RU')} · {e.actor?.login}<p className="text-sm mt-1">{e.comment} {e.rejection_reason?.title}</p></div>)}</div></Card>
  </div>;
};
export default CandidateCard;
