import { useEffect, useState, type ReactNode } from 'react';
import {
  ApiError, api, assessmentLabel, deadlineLabel, errorMessage, feedbackLabel, readableExplanation, recipientId,
  request, resultLabel, type ApplicationDetail, type Evidence, type Handoff, type HandoffDetail, type HandoffPreview,
  type History, type Reason, type Stage, type Vacancy,
} from '../../api/recruitment';
import { Badge, Btn, Card, PageTitle } from '../shared/ui';
import RecruitmentSummary from '../shared/RecruitmentSummary';

interface CandidateCardProps {
  candidateId?: string;
  backLabel?: string;
  context?: ReactNode;
  onBack?: () => void;
  onRequestClarification?: () => void;
  onOpenArchive?: () => void;
  onReject?: () => void;
}

type Panel = 'handoff' | 'archive' | 'reject' | 'stage';
type CandidateSource = { text: string; version: number; is_current: boolean };
const field = 'w-full border border-[#C9D0DB] rounded-xl px-4 py-3 text-sm bg-white';
const extensionReasons = { illness: 'Болезнь', vacation: 'Отпуск', business_trip: 'Командировка', other: 'Другое' };

export function CandidateCard({
  candidateId: applicationId = '', backLabel = 'Отклики', context, onBack, onRequestClarification, onOpenArchive,
}: CandidateCardProps) {
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [stages, setStages] = useState<Stage[]>([]);
  const [reasons, setReasons] = useState<Reason[]>([]);
  const [vacancies, setVacancies] = useState<Vacancy[]>([]);
  const [source, setSource] = useState<CandidateSource | null>(null);
  const [sourceError, setSourceError] = useState('');
  const [highlight, setHighlight] = useState<Evidence | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [target, setTarget] = useState('');
  const [reason, setReason] = useState('');
  const [comment, setComment] = useState('');
  const [contactBasis, setContactBasis] = useState('');
  const [confirmSkip, setConfirmSkip] = useState(false);
  const [summary, setSummary] = useState<HandoffPreview | null>(null);
  const [attemptDetail, setAttemptDetail] = useState<HandoffDetail | null>(null);
  const [extension, setExtension] = useState<{ attemptId: string; dueDate: string } | null>(null);
  const [newDate, setNewDate] = useState('');
  const [extensionReason, setExtensionReason] = useState('');
  const [extensionComment, setExtensionComment] = useState('');
  const [requestId, setRequestId] = useState('');
  const [inArchive, setInArchive] = useState(false);

  useEffect(() => {
    let live = true;
    setLoading(true); setError(''); setDetail(null); setSource(null); setHighlight(null); setSourceError('');
    if (!applicationId) {
      setError('Сначала выберите отклик.');
      setLoading(false);
      return;
    }
    Promise.all([api.application(applicationId), api.history(applicationId), api.applicationHandoffs(applicationId), api.stages(), api.reasons()])
      .then(async ([application, events, attempts, stageList, reasonList]) => {
        if (!live) return;
        setDetail(application); setHistory(events); setHandoffs(attempts.items);
        setStages(stageList.items); setReasons(reasonList.items); setLoading(false);
        const textId = application.candidate.current_text_id;
        if (!textId) { setSourceError('У кандидата нет доступного текста источника.'); return; }
        try { const text = await api.source(textId); if (live) setSource(text); }
        catch (error) { if (live) setSourceError(errorMessage(error)); }
      }).catch(error => { if (live) { setError(errorMessage(error)); setLoading(false); } });
    return () => { live = false; };
  }, [applicationId, reload]);

  const action = async (work: () => Promise<void>) => {
    setBusy(true); setError(''); setNotice('');
    try { await work(); }
    catch (error) {
      if (error instanceof ApiError && ['SUMMARY_CHANGED', 'STALE_STAGE_FORM', 'DEADLINE_CONFLICT', 'ASSESSMENT_STALE'].includes(error.code)) {
        setPanel(null); setExtension(null); setAttemptDetail(null);
        setReload(value => value + 1);
        setNotice('Данные отклика изменились. Откройте действие заново и проверьте обновлённые сведения.');
      } else {
        setError(errorMessage(error));
      }
    } finally { setBusy(false); }
  };

  function openPanel(next: Panel) {
    setPanel(next); setTarget(next === 'reject' ? 'rejected' : '');
    setReason(''); setComment(''); setContactBasis(''); setConfirmSkip(false); setSummary(null);
    setRequestId(crypto.randomUUID()); setError(''); setNotice('');
    if (next === 'handoff') {
      void action(async () => setSummary(await api.summary(applicationId)));
    }
    if (next === 'archive') {
      void action(async () => {
        const { items } = await api.vacancies();
        setVacancies(items);
        setTarget(items.find(item => item.vacancy_id === detail?.vacancy?.vacancy_id)?.position_id || '');
      });
    }
  }

  const sendHandoff = () => action(async () => {
    if (!summary || !history || !detail || !recipientId) return;
    const handoff = { recipient_user_id: recipientId, channel: 'cabinet', summary_revision: summary.summary_revision, request_id: requestId };
    if (['sent_to_department', 'department_interview'].includes(detail.stage.code)) {
      await request(`/applications/${applicationId}/handoffs`, 'hr', { expected_seq: history.last_seq || 0, handoff });
    } else {
      await request(`/applications/${applicationId}/stage`, 'hr', {
        to_stage_code: 'sent_to_department', expected_seq: history.last_seq || 0, comment, confirm_skip: confirmSkip, handoff,
      });
    }
    setPanel(null); setNotice('Передача сохранена. Получатель видит сводку и срок в своём кабинете.');
    setReload(value => value + 1);
  });

  const moveStage = () => action(async () => {
    if (!history) return;
    await request(`/applications/${applicationId}/stage`, 'hr', {
      to_stage_code: target, expected_seq: history.last_seq || 0, comment, confirm_skip: confirmSkip,
      rejection_reason_code: ['rejected', 'withdrawn'].includes(target) ? reason : null,
    });
    setPanel(null); setNotice('Решение сохранено в истории отклика.'); setReload(value => value + 1);
  });

  const saveArchive = () => action(async () => {
    if (!detail || !history) return;
    const saved = await api.saveToArchive(detail.candidate.candidate_id, target,
      history.source === 'response' ? applicationId : null, comment, contactBasis);
    setInArchive(true);
    setPanel(null);
    setNotice(saved.created ? 'Основание для повторного контакта сохранено в архиве.' : 'Подборка с этой должностью уже есть в архиве.');
  });

  const showEvidence = (evidence: Evidence) => action(async () => {
    setSource(await api.source(evidence.candidate_text_id)); setHighlight(evidence); setSourceError('');
  });
  const extend = () => action(async () => {
    if (!extension) return;
    await request(`/applications/${applicationId}/handoffs/${extension.attemptId}/deadline`, 'hr', {
      new_due_date: newDate, expected_due_date: extension.dueDate, reason_code: extensionReason,
      comment: extensionComment, request_id: requestId,
    });
    setExtension(null); setAttemptDetail(null); setNotice('Новый срок и причина сохранены.'); setReload(value => value + 1);
  });

  if (loading || !detail) return <div className="max-w-[1240px] mx-auto p-6 space-y-4">
    <Btn variant="link" onClick={onBack}>← {backLabel}</Btn>
    {context}
    <p role={error ? 'alert' : undefined}>{error || 'Загрузка карточки…'}</p>
    {error && applicationId && <Btn onClick={() => setReload(value => value + 1)}>Повторить</Btn>}
  </div>;

  const canMove = history?.source === 'response' && !detail.stage.is_final;
  const stageReasons = reasons.filter(item => target === 'withdrawn' ? item.side !== 'employer' : item.side !== 'candidate');
  const alreadyAssigned = handoffs.some(attempt => !attempt.access_revoked_at);
  const distinctPositions = [...new Map(vacancies.map(item => [item.position_id, item])).values()];
  const extendsPastDue = extension && newDate > extension.dueDate;

  return <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-6 space-y-5">
    <div className="flex justify-between gap-3">
      <Btn variant="link" onClick={onBack}>← {backLabel}</Btn>
      <Btn variant="link" onClick={() => setReload(value => value + 1)}>Обновить</Btn>
    </div>
    {context}
    <Card className="space-y-3">
      <PageTitle title={detail.candidate.contacts?.full_name || detail.candidate.code}
        subtitle={detail.vacancy?.title || detail.posting_title || detail.candidate.headline || 'Карточка отклика'}
        right={<Badge tone="blue">{detail.stage.title}</Badge>} />
      {detail.candidate.headline && detail.vacancy && <p className="text-[#4A5363]">{detail.candidate.headline}</p>}
      {detail.candidate.contacts ? <p className="flex flex-wrap gap-x-3 text-sm">
        {detail.candidate.contacts.phone && <a className="text-[#1F4FD1]" href={'tel:' + detail.candidate.contacts.phone.replace(/[^+\d]/g, '')}>{detail.candidate.contacts.phone}</a>}
        {detail.candidate.contacts.email && <a className="text-[#1F4FD1]" href={'mailto:' + detail.candidate.contacts.email}>{detail.candidate.contacts.email}</a>}
        {detail.candidate.contacts.city && <span>{detail.candidate.contacts.city}</span>}
        {detail.candidate.is_training && <span className="text-[#616977]">Учебная запись, контакты вымышленные.</span>}
      </p> : <p className="text-sm text-[#616977]">{detail.candidate.is_training ? 'Учебная запись · ' : ''}Контакты не показаны</p>}
    </Card>
    {error && <div role="alert" className="p-4 bg-red-50 text-red-800 rounded-xl">{error}</div>}
    {notice && <div role="status" className="p-4 bg-[#E3F2E7] text-[#1D7A40] rounded-xl">{notice}</div>}
    <div className="grid lg:grid-cols-[1.65fr_1fr] gap-5 items-start">
      <div className="space-y-5 min-w-0">
        <Card className="space-y-4"><h2 className="text-xl font-bold">Сравнение с профилем должности</h2>
          <Badge tone={detail.assessment?.is_stale ? 'amber' : 'blue'}>{assessmentLabel(detail.assessment_status)}</Badge>
          <p>{detail.assessment?.summary || 'Данных для вывода пока недостаточно.'}</p>
          {detail.assessment?.formal_checks.length ? <div className="overflow-x-auto rounded-xl border border-[#E1E5EB]">
            <table className="w-full min-w-[32rem] text-left text-sm">
              <thead className="bg-[#FAFBFD] text-[#4A5363]">
                <tr><th className="p-3 font-semibold">Требование профиля</th><th className="p-3 font-semibold">Что в резюме</th><th className="p-3 font-semibold">Итог</th></tr>
              </thead>
              <tbody className="divide-y divide-[#E1E5EB]">
                {detail.assessment.formal_checks.map(check => <tr key={check.requirement_id}>
                  <td className="p-3">{check.description}</td>
                  <td className="p-3 space-y-1">
                    {readableExplanation(check.explanation) && <p>{readableExplanation(check.explanation)}</p>}
                    {check.evidence.map((evidence, index) => <button key={index} onClick={() => showEvidence(evidence)} className="block text-left text-[#1F4FD1]">«{evidence.quote}» ↗</button>)}
                    {!check.evidence.length && !readableExplanation(check.explanation) && <p className="text-[#616977]">Сведений нет</p>}
                  </td>
                  <td className="p-3"><Badge tone={check.result === 'met' ? 'green' : check.result === 'not_met' ? 'red' : 'amber'}>{resultLabel(check.result)}{check.is_preliminary ? ' · предварительно' : ''}</Badge></td>
                </tr>)}
              </tbody>
            </table>
          </div> : <p className="text-[#616977]">Требования ещё не оценены.</p>}
          {Boolean(detail.assessment?.competency_scores.length) && <h3 className="font-bold">Компетенции и основания</h3>}
          {detail.assessment?.competency_scores.map((item, index) => <div key={index} className="border border-[#E1E5EB] rounded-xl p-4">
            <b>{item.name}</b>
            <p className="text-sm mt-2">{readableExplanation(item.explanation) || 'Сведений недостаточно'}</p>
            {item.evidence.map((evidence, index) => <button key={index} onClick={() => showEvidence(evidence)} className="block text-left text-sm text-[#1F4FD1] mt-2">«{evidence.quote}» ↗</button>)}
          </div>)}
        </Card>
        <Card className="space-y-3 min-w-0">
          <h2 className="text-xl font-bold">Текст источника</h2>
          {sourceError ? <p role="alert">{sourceError}</p> : source ? <>
            <p className="text-sm text-[#616977]">Версия {source.version} · {source.is_current ? 'текущая' : 'предыдущая'}</p>
            <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-7 max-h-[650px] overflow-auto">{highlight ? <>
              {source.text.slice(0, highlight.utf16_start)}<mark className="bg-[#FFF4CC]">{source.text.slice(highlight.utf16_start, highlight.utf16_end)}</mark>{source.text.slice(highlight.utf16_end)}
            </> : source.text}</pre>
          </> : <p>Загрузка источника…</p>}
        </Card>
      </div>
      <div className="space-y-5 min-w-0">
        <Card className="space-y-3">
          <h2 className="text-xl font-bold">Действия</h2>
          <div className="grid gap-2">
            <Btn className="text-left" variant="primary" disabled={busy || !canMove} onClick={() => openPanel('handoff')}>Направить в департамент</Btn>
            <Btn className="text-left" disabled={busy} onClick={() => openPanel('archive')}>В архив кадров</Btn>
            <Btn className="text-left" disabled={busy || !canMove} onClick={() => openPanel('reject')}>Отклонить с причиной</Btn>
          </div>
          <p className="text-sm text-[#616977]">Итоговое решение принимает HR.</p>
          {panel === 'handoff' && <div className="space-y-3 border-t pt-4">
            <h3 className="font-bold">Сводка перед отправкой</h3>
            {summary ? <div className="max-h-[30rem] overflow-auto"><RecruitmentSummary summary={summary.summary} /></div> : busy ? <p>Загрузка сводки…</p> : <Btn onClick={() => openPanel('handoff')}>Повторить загрузку сводки</Btn>}
            <p className="text-sm">{recipientId ? 'Получатель · настроенный представитель подразделения' : 'Назначьте получателя в настройках стенда.'}</p>
            {alreadyAssigned && ['sent_to_department', 'department_interview'].includes(detail.stage.code) && <p className="text-sm">Дополнительную передачу настраивают для другого разрешённого адресата.</p>}
            <label className="block text-sm">Комментарий HR<textarea className={field} value={comment} onChange={e => setComment(e.target.value)} /></label>
            <label className="block text-sm"><input type="checkbox" checked={confirmSkip} onChange={e => setConfirmSkip(e.target.checked)} /> Подтверждаю пропуск этапов по указанной причине</label>
            <p className="text-sm text-[#616977]">Срок ответа · 10 рабочих дней.</p>
            <Btn variant="primary" disabled={busy || !summary || !recipientId || !comment.trim()} onClick={sendHandoff}>Подтвердить передачу</Btn>
          </div>}
          {panel === 'archive' && <div className="space-y-3 border-t pt-4">
            <label className="block text-sm">Должность<select className={field} value={target} onChange={e => setTarget(e.target.value)}><option value="">Выберите должность</option>
              {distinctPositions.map(item => <option key={item.position_id} value={item.position_id}>{item.title}</option>)}
            </select></label>
            <label className="block text-sm">Почему сохранить<textarea className={field} value={comment} onChange={e => setComment(e.target.value)} /></label>
            <label className="block text-sm">Основание повторного контакта<textarea className={field} value={contactBasis} onChange={e => setContactBasis(e.target.value)} /></label>
            <Btn variant="primary" disabled={busy || !target || !comment.trim() || !contactBasis.trim()} onClick={saveArchive}>Сохранить в архиве</Btn>
          </div>}
          {(panel === 'stage' || panel === 'reject') && <div className="space-y-3 border-t pt-4">
            {panel === 'stage' && <label className="block text-sm">Новый этап<select className={field} value={target} onChange={e => { setTarget(e.target.value); setReason(''); }}><option value="">Выберите этап</option>
              {stages.filter(item => !['sent_to_department', 'rejected', detail.stage.code].includes(item.code)).map(item => <option key={item.code} value={item.code}>{item.title}</option>)}
            </select></label>}
            {['rejected', 'withdrawn'].includes(target) && <label className="block text-sm">Причина решения<select className={field} value={reason} onChange={e => setReason(e.target.value)}><option value="">Выберите причину</option>
              {stageReasons.map(item => <option key={item.code} value={item.code}>{item.title}</option>)}
            </select></label>}
            <label className="block text-sm">Обоснование решения<textarea className={field} value={comment} onChange={e => setComment(e.target.value)} /></label>
            {panel === 'stage' && <label className="block text-sm"><input type="checkbox" checked={confirmSkip} onChange={e => setConfirmSkip(e.target.checked)} /> Подтверждаю возврат или пропуск этапов по указанной причине</label>}
            <Btn variant="primary" disabled={busy || !target || !comment.trim() || (['rejected', 'withdrawn'].includes(target) && !reason)} onClick={moveStage}>
              {panel === 'reject' ? 'Сохранить отказ' : 'Сохранить этап'}
            </Btn>
          </div>}
          {panel && <Btn variant="link" disabled={busy} onClick={() => { setPanel(null); setError(''); }}>Отмена</Btn>}
        </Card>
        {onOpenArchive && <div className="text-sm text-[#4A5363]">{inArchive && <p>Подборка сохранена</p>}<Btn variant="link" onClick={onOpenArchive}>Открыть архив кадров</Btn></div>}
        <div className="flex flex-wrap gap-3">
          {onRequestClarification && <Btn disabled={busy || !canMove} onClick={onRequestClarification}>Телефонное интервью</Btn>}
          {canMove && <Btn disabled={busy} onClick={() => openPanel('stage')}>Изменить этап</Btn>}
        </div>
        <Card className="space-y-3">
          <h2 className="text-xl font-bold">История этапов</h2>
          {!history?.items.length && <p>Переходов пока нет.</p>}
          {history?.items.map(item => <div key={item.seq} className="border-b border-[#E1E5EB] pb-3 text-sm">
            <b>{item.to_stage.title}</b> · {new Date(item.created_at).toLocaleString('ru-RU')}<p>{item.comment} {item.rejection_reason?.title}</p>
          </div>)}
        </Card>
      </div>
    </div>
    <Card className="space-y-4">
      <h2 className="text-xl font-bold">Передачи и ответы подразделения</h2>
      {!handoffs.length && <p>Передач пока нет.</p>}
      {handoffs.map(attempt => <div key={attempt.attempt_id} className="border border-[#E1E5EB] p-4 rounded-xl space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2"><b>{attempt.recipient_name} · {attempt.recipient_department}</b>
          <Badge tone={attempt.deadline_status === 'overdue' ? 'red' : attempt.deadline_status === 'due_soon' ? 'amber' : 'blue'}>{deadlineLabel(attempt.deadline_status)}</Badge>
        </div>
        <p className="text-sm">Передан {new Date(attempt.handed_off_at).toLocaleString('ru-RU')} · срок {attempt.due_date} · переносов {attempt.extensions_count}</p>
        {attempt.overdue_notice && <p className="text-sm text-[#A3171B]">{attempt.overdue_notice}</p>}
        {attempt.business_days_left != null && attempt.business_days_left >= 0 && <p className="text-sm">Осталось рабочих дней: {attempt.business_days_left}</p>}
        {attempt.latest_feedback && <p className="bg-[#E3F2E7] rounded-xl p-3">{feedbackLabel(attempt.latest_feedback.outcome)} · {attempt.latest_feedback.rejection_reason?.title} {attempt.latest_feedback.comment}</p>}
        <div className="flex flex-wrap gap-3">
          <Btn disabled={busy} onClick={() => action(async () => setAttemptDetail(await api.handoff(attempt.attempt_id, 'hr')))}>Сводка и история</Btn>
          {attempt.status === 'awaiting_response' && <Btn disabled={busy} onClick={() => {
            setExtension({ attemptId: attempt.attempt_id, dueDate: attempt.due_date }); setRequestId(crypto.randomUUID());
            setNewDate(''); setExtensionReason(''); setExtensionComment('');
          }}>Продлить срок</Btn>}
        </div>
        {extension?.attemptId === attempt.attempt_id && <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">Новый срок<input type="date" className={field} value={newDate} min={attempt.due_date} onChange={e => setNewDate(e.target.value)} /></label>
          <label className="text-sm">Причина<select className={field} value={extensionReason} onChange={e => setExtensionReason(e.target.value)}><option value="">Выберите причину</option>
            {Object.entries(extensionReasons).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
          </select></label>
          <label className="text-sm">Комментарий<input className={field} value={extensionComment} onChange={e => setExtensionComment(e.target.value)} /></label>
          <Btn disabled={busy || !extendsPastDue || !extensionReason || (extensionReason === 'other' && !extensionComment.trim())} onClick={extend}>Сохранить</Btn>
          <Btn variant="link" disabled={busy} onClick={() => setExtension(null)}>Отмена</Btn>
        </div>}
        {attemptDetail?.attempt_id === attempt.attempt_id && <div className="space-y-3">
          <Btn variant="link" onClick={() => setAttemptDetail(null)}>Закрыть сводку</Btn>
          <RecruitmentSummary summary={attemptDetail.summary} />
          {attemptDetail.feedback_history.map(item => <p key={item.feedback_id}>{new Date(item.received_at).toLocaleString('ru-RU')} · {feedbackLabel(item.outcome)} · {item.comment}</p>)}
          {attemptDetail.deadline_extensions.map(item => <p key={item.extension_id}>{item.previous_due_date} → {item.new_due_date} · {item.reason_title}{item.was_overdue && ' · срок был просрочен'} · {item.comment}</p>)}
        </div>}
      </div>)}
    </Card>
  </div>;
}
export default CandidateCard;
