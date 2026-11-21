import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  ApiError, api, assessmentLabel, deadlineLabel, errorMessage, feedbackLabel, readableAssessmentSummary, readableExplanation, recipientId,
  request, resultLabel, type ApplicationDetail, type CandidateApplication, type Evidence, type Handoff, type HandoffDetail, type HandoffPreview,
  type History, type Reason, type Stage, type Vacancy,
} from '../../api/recruitment';
import { Badge, Btn, Card, PageTitle } from '../shared/ui';
import RecruitmentSummary from '../shared/RecruitmentSummary';
import { ProfileOtherVacancies, ProfilePsychology, ProfileQuestions, profilePanel, profileTitle } from './CandidateProfileDetails';

interface CandidateCardProps {
  candidateId?: string;
  backLabel?: string;
  context?: ReactNode;
  databaseProfile?: boolean;
  profileApplication?: CandidateApplication;
  profileChannel?: string;
  onBack?: () => void;
  onRequestClarification?: () => void;
  onOpenArchive?: () => void;
  onReject?: () => void;
}

type Panel = 'handoff' | 'archive' | 'reject' | 'stage';
type CandidateSource = { text: string; version: number; is_current: boolean };
const field = 'w-full border border-[#C9D0DB] rounded-xl px-4 py-3 text-sm bg-white';
const profileField = 'w-full px-3 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24] focus:outline-none focus:border-[#1F4FD1]';
const profileLabel = 'block text-[12px] font-medium text-[#4A5363] mb-1';
const profileSubmit = 'flex-1 py-2 text-[13px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm text-center disabled:opacity-50';
const profileCancel = 'px-4 py-2 text-[13px] font-medium text-[#4A5363] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors';
const channelTitles: Record<string, string> = {
  hh_ru: 'HH.ru', rabota_rossii: '«Работа России»', city_site: 'Сайт администрации', email: 'Электронная почта',
  citizen_appeal: 'Обращение гражданина', internship: 'Практика', internal: 'Внутренний источник',
};
const extensionReasons = { illness: 'Болезнь', vacation: 'Отпуск', business_trip: 'Командировка', other: 'Другое' };

export function CandidateCard({
  candidateId: applicationId = '', backLabel = 'Отклики', context, databaseProfile = false, profileApplication, profileChannel, onBack, onRequestClarification, onOpenArchive,
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
  const [validUntil, setValidUntil] = useState('');
  const [confirmSkip, setConfirmSkip] = useState(false);
  const [summary, setSummary] = useState<HandoffPreview | null>(null);
  const [attemptDetail, setAttemptDetail] = useState<HandoffDetail | null>(null);
  const [extension, setExtension] = useState<{ attemptId: string; dueDate: string } | null>(null);
  const [newDate, setNewDate] = useState('');
  const [extensionReason, setExtensionReason] = useState('');
  const [extensionComment, setExtensionComment] = useState('');
  const [requestId, setRequestId] = useState('');
  const [inArchive, setInArchive] = useState(false);
  const sourceLocation = useRef<HTMLDetailsElement>(null);

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
    setReason(''); setComment(''); setContactBasis(''); setValidUntil(''); setConfirmSkip(false); setSummary(null);
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
      history.source === 'response' ? applicationId : null, comment, contactBasis, validUntil || undefined);
    setInArchive(true);
    setPanel(null);
    setNotice(saved.created ? 'Основание для повторного контакта сохранено в архиве.' : 'Подборка с этой должностью уже есть в архиве.');
  });

  const showEvidence = (evidence: Evidence) => action(async () => {
    setSource(await api.source(evidence.candidate_text_id)); setHighlight(evidence); setSourceError('');
    if (databaseProfile && sourceLocation.current) {
      sourceLocation.current.open = true;
      sourceLocation.current.scrollIntoView({ block: 'start' });
    }
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
  const displayName = detail.candidate.contacts?.full_name || detail.candidate.code;
  const vacancyTitle = detail.vacancy?.title || detail.posting_title;
  const contacts = detail.candidate.contacts;
  const sourceName = profileChannel ? channelTitles[profileChannel] : undefined;
  const appliedDate = profileApplication?.applied_at?.split('-').reverse().join('.');
  const sourceLabel = profileApplication?.source === 'response' ? 'Внешний отклик'
    : profileApplication?.source === 'history' ? 'История откликов' : 'Рассмотрение HR';
  const headingDetails = [sourceLabel, sourceName, appliedDate, detail.candidate.is_training && 'Учебная запись'].filter(Boolean).join(' · ');
  const overdue = handoffs.some(attempt => attempt.deadline_status === 'overdue');
  const awaiting = handoffs.some(attempt => attempt.status === 'awaiting_response');
  const profileStatus = detail.stage.is_final ? detail.stage.title
    : overdue ? 'Просрочен ответ департамента' : awaiting ? 'Ждёт решения департамента' : inArchive ? 'В архиве кадров' : detail.stage.title;
  const profileStatusClass = detail.stage.code === 'rejected' || overdue ? 'bg-[#FDE8E8] text-[#C5221F]'
    : inArchive ? 'bg-[#E6F4EA] text-[#15803D]' : 'bg-[#EDF3FD] text-[#1F4FD1]';
  const unknownChecks = detail.assessment?.formal_checks.filter(item => item.result === 'unknown') ?? [];
  const missingInformation = Array.isArray(detail.candidate.card?.missing)
    ? detail.candidate.card.missing.filter((item): item is string => typeof item === 'string')
    : [];
  const gaps = [...new Set([...unknownChecks.map(item => item.description), ...missingInformation])];
  const actionClass = 'w-full py-2.5 px-4 text-[14px] font-medium rounded-lg transition-colors shadow-sm text-center disabled:opacity-50 disabled:cursor-not-allowed';
  const secondaryAction = `${actionClass} text-[#141A24] bg-white border border-[#E1E5EB] hover:bg-[#F3F5F8]`;
  const formField = databaseProfile ? profileField : field;
  const formLabel = databaseProfile ? profileLabel : 'block text-sm';
  const blueForm = databaseProfile ? 'border border-[#BFDBFE] rounded-xl p-4 bg-[#F8FAFF] space-y-3' : 'space-y-3 border-t pt-4';
  const cancelForm = () => { setPanel(null); setError(''); };
  const formButtons = (label: string, submit: () => void, disabled: boolean) => databaseProfile
    ? <div className="flex items-center gap-2 pt-1">
      <button type="button" className={profileSubmit} disabled={disabled} onClick={submit}>{label}</button>
      <button type="button" className={profileCancel} disabled={busy} onClick={cancelForm}>Отмена</button>
    </div> : <Btn variant="primary" disabled={disabled} onClick={submit}>{label}</Btn>;
  const sourcePanel = <Card className="space-y-3 min-w-0">
    <h2 className="text-xl font-bold">Текст источника</h2>
    {sourceError ? <p role="alert">{sourceError}</p> : source ? <>
      <p className="text-sm text-[#616977]">Версия {source.version} · {source.is_current ? 'текущая' : 'предыдущая'}</p>
      <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-7 max-h-[650px] overflow-auto">{highlight ? <>
        {source.text.slice(0, highlight.utf16_start)}<mark className="bg-[#FFF4CC]">{source.text.slice(highlight.utf16_start, highlight.utf16_end)}</mark>{source.text.slice(highlight.utf16_end)}
      </> : source.text}</pre>
    </> : <p>Загрузка источника…</p>}
  </Card>;

  return <div className={databaseProfile ? 'max-w-[1240px] mx-auto px-4 sm:px-6 py-6' : 'max-w-[1240px] mx-auto px-4 sm:px-6 py-6 space-y-5'}>
    {databaseProfile ? <div className="mb-5">
      <nav className="text-[14px] text-[#616977] flex items-center gap-1.5 font-normal">
        <button type="button" onClick={onBack} className="hover:text-[#1F4FD1] hover:underline transition-colors">Единая база</button>
        <span>›</span><span className="text-[#141A24] font-medium">{displayName}</span>
      </nav>
    </div> : <div className="flex justify-between gap-3">
      <Btn variant="link" onClick={onBack}>← {backLabel}</Btn>
      <Btn variant="link" onClick={() => setReload(value => value + 1)}>Обновить</Btn>
    </div>}
    {!databaseProfile && context}
    {databaseProfile ? <div className={profilePanel + ' mb-6'}>
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div>
          <h1 className="text-[24px] font-bold text-[#141A24] tracking-tight mb-1">{displayName}</h1>
          {vacancyTitle && <p className="text-[14px] text-[#4A5363] mb-1">Вакансия «{vacancyTitle}»</p>}
          <p className="text-[13px] text-[#616977]">{headingDetails}</p>
          {context}
        </div>
        <div className="flex flex-col sm:items-end gap-2">
          {contacts && <span className="text-[13px] text-[#4A5363] font-medium">
            {contacts.phone && <a href={'tel:' + contacts.phone.replace(/[^+\d]/g, '')}>{contacts.phone}</a>}
            {contacts.phone && contacts.email && ' · '}
            {contacts.email && <a href={'mailto:' + contacts.email}>{contacts.email}</a>}
          </span>}
          <span className={`${profileStatusClass} px-3 py-1 rounded-full text-[12px] font-medium whitespace-nowrap`}>{profileStatus}</span>
        </div>
      </div>
    </div> : <Card className="space-y-3">
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
    </Card>}
    {error && <div role="alert" className="p-4 bg-red-50 text-red-800 rounded-xl">{error}</div>}
    {notice && <div role="status" className="p-4 bg-[#E3F2E7] text-[#1D7A40] rounded-xl">{notice}</div>}
    <div className={databaseProfile ? 'grid grid-cols-1 lg:grid-cols-12 gap-6 items-start' : 'grid lg:grid-cols-[1.15fr_1fr] gap-6 items-start'}>
      <div className={databaseProfile ? 'lg:col-span-8 space-y-6' : 'space-y-5 min-w-0'}>
        <div className={profilePanel}>
          <div className="mb-4">
            <h2 className={profileTitle + ' mb-0.5'}>Сравнение с профилем должности</h2>
            <p className="text-[13px] text-[#616977]">{readableAssessmentSummary(detail.assessment?.summary) || assessmentLabel(detail.assessment_status)}</p>
            {detail.assessment?.is_stale && <p className="text-[13px] text-[#616977]">Оценка устарела.</p>}
          </div>
          {detail.assessment && (detail.assessment.formal_checks.length || (databaseProfile && detail.assessment.competency_scores.length)) ? <div className="border border-[#E1E5EB] rounded-xl overflow-hidden">
            <table className="w-full text-left text-[13px]">
              <thead className="bg-[#FAFBFD] border-b border-[#E1E5EB] text-[#616977] font-medium">
                <tr><th className="py-3 px-4 w-[34%]">Требование профиля</th><th className="py-3 px-4 w-[46%]">Что в резюме</th><th className="py-3 px-4 w-[20%] text-right sm:text-left">Итог</th></tr>
              </thead>
              <tbody className="divide-y divide-[#E1E5EB]">
                {detail.assessment.formal_checks.map(check => <tr key={check.requirement_id} className="hover:bg-[#F8FAFC]">
                  <td className="py-3.5 px-4 font-medium text-[#141A24]">{check.description}</td>
                  <td className="py-3.5 px-4 text-[#4A5363]">
                    {readableExplanation(check.explanation) && <p>{readableExplanation(check.explanation)}</p>}
                    {check.evidence.map((evidence, index) => <button key={index} onClick={() => showEvidence(evidence)} className="block text-left text-[#1F4FD1]">«{evidence.quote}» ↗</button>)}
                    {!check.evidence.length && !readableExplanation(check.explanation) && <p className="text-[#616977]">Сведений нет</p>}
                  </td>
                  <td className="py-3.5 px-4 text-right sm:text-left">
                    <span className={`inline-block px-2.5 py-0.5 rounded-full text-[12px] font-medium ${check.result === 'met' ? 'bg-[#E6F4EA] text-[#15803D]' : check.result === 'not_met' ? 'bg-[#FDE8E8] text-[#C5221F]' : 'bg-[#FEF3E6] text-[#B45309]'}`}>{resultLabel(check.result)}{check.is_preliminary ? ' · предварительно' : ''}</span>
                  </td>
                </tr>)}
                {databaseProfile && detail.assessment.competency_scores.map((item, index) => <tr key={index} className="hover:bg-[#F8FAFC]">
                  <td className="py-3.5 px-4 font-medium text-[#141A24]">{item.name}</td>
                  <td className="py-3.5 px-4 text-[#4A5363]">
                    {readableExplanation(item.explanation) && <p>{readableExplanation(item.explanation)}</p>}
                    {item.evidence.map((evidence, position) => <button key={position} type="button" onClick={() => showEvidence(evidence)} className="block text-left text-[#1F4FD1]">«{evidence.quote}» ↗</button>)}
                  </td>
                  <td className="py-3.5 px-4 text-right sm:text-left"><span className="inline-block px-2.5 py-0.5 rounded-full text-[12px] font-medium bg-[#F3F4F6] text-[#4B5563] whitespace-nowrap">Компетенция</span></td>
                </tr>)}
              </tbody>
            </table>
          </div> : <p className="text-[#616977]">Требования ещё не оценены.</p>}
          {!databaseProfile && Boolean(detail.assessment?.competency_scores.length) && <h3 className="font-bold">Компетенции и основания</h3>}
          {!databaseProfile && detail.assessment?.competency_scores.map((item, index) => <div key={index} className="border border-[#E1E5EB] rounded-xl p-4">
            <b>{item.name}</b>
            <p className="text-sm mt-2">{readableExplanation(item.explanation) || 'Сведений недостаточно'}</p>
            {item.evidence.map((evidence, index) => <button key={index} onClick={() => showEvidence(evidence)} className="block text-left text-sm text-[#1F4FD1] mt-2">«{evidence.quote}» ↗</button>)}
          </div>)}
          {databaseProfile && <details ref={sourceLocation}>
            <summary className="text-[13px] text-[#616977] hover:text-[#1F4FD1] hover:underline transition-colors">Текст источника</summary>
            {sourcePanel}
          </details>}
        </div>
        {databaseProfile && <>
          <div className={profilePanel}>
            <h2 className={profileTitle + ' mb-2'}>Недостающие данные</h2>
            {gaps.length ? <ul className="text-[13px] text-[#4A5363] space-y-1">{gaps.map(item => <li key={item}>• {item}</li>)}</ul>
              : <p className="text-[13px] text-[#616977]">Недостающие сведения пока не отмечены.</p>}
          </div>
          <ProfileQuestions applicationId={applicationId} canReadGuide={history?.source === 'response'} onInterview={canMove ? onRequestClarification : undefined} />
          <ProfilePsychology />
        </>}
        {!databaseProfile && sourcePanel}
      </div>
      <div className={databaseProfile ? 'lg:col-span-4 space-y-6' : 'space-y-5 min-w-0'}>
        <div className={profilePanel}>
          <h2 className={profileTitle + ' mb-4'}>Действия</h2>
          {(!databaseProfile || !panel) && <div className="space-y-3">
            <button type="button" className={`${actionClass} text-white bg-[#1F4FD1] hover:bg-[#1841B2]`} disabled={busy || !canMove} onClick={() => openPanel('handoff')}>Направить в департамент</button>
            <button type="button" className={secondaryAction} disabled={busy} onClick={() => openPanel('archive')}>В архив кадров</button>
            <button type="button" className={secondaryAction} disabled={busy || !canMove} onClick={() => openPanel('reject')}>Отклонить с причиной</button>
            <p className="text-[12px] text-[#616977] pt-1">ИИ подсказывает, решение принимает человек</p>
          </div>}
          {panel === 'handoff' && <div className={blueForm}>
            <h3 className="font-bold">Сводка перед отправкой</h3>
            {summary ? <div className="max-h-[30rem] overflow-auto"><RecruitmentSummary summary={summary.summary} /></div> : busy ? <p>Загрузка сводки…</p> : <Btn onClick={() => openPanel('handoff')}>Повторить загрузку сводки</Btn>}
            <label className={formLabel}>Ответственный
              <input className={formField} readOnly value={recipientId ? 'Настроенный представитель подразделения' : 'Получатель не назначен'} />
            </label>
            {alreadyAssigned && ['sent_to_department', 'department_interview'].includes(detail.stage.code) && <p className={formLabel}>Дополнительную передачу настраивают для другого разрешённого адресата.</p>}
            <label className={formLabel}>Срок ответа<input className={formField} readOnly value="10 рабочих дней" /></label>
            <label className={formLabel}>Комментарий HR<textarea rows={2} className={formField} value={comment} onChange={e => setComment(e.target.value)} /></label>
            <label className={formLabel}><input type="checkbox" checked={confirmSkip} onChange={e => setConfirmSkip(e.target.checked)} /> Подтверждаю пропуск этапов по указанной причине</label>
            {formButtons(databaseProfile ? 'Направить' : 'Подтвердить передачу', sendHandoff, busy || !summary || !recipientId || !comment.trim())}
          </div>}
          {panel === 'archive' && <div className={blueForm}>
            {databaseProfile && <h3 className="text-[14px] font-bold text-[#141A24]">Перенести резюме в архив кадров</h3>}
            <label className={formLabel}>Целевая должность<select className={formField} value={target} onChange={e => setTarget(e.target.value)}><option value="">Выберите должность</option>
              {distinctPositions.map(item => <option key={item.position_id} value={item.position_id}>{item.title}</option>)}
            </select></label>
            {databaseProfile && <label className={formLabel}>Срок хранения<input type="date" className={formField} value={validUntil} onChange={e => setValidUntil(e.target.value)} /></label>}
            <label className={formLabel}>Почему в архив<textarea rows={2} className={formField} value={comment} onChange={e => setComment(e.target.value)} /></label>
            <label className={formLabel}>Основание повторного контакта<textarea rows={2} className={formField} value={contactBasis} onChange={e => setContactBasis(e.target.value)} /></label>
            {formButtons(databaseProfile ? 'Перенести в архив' : 'Сохранить в архиве', saveArchive, busy || !target || !comment.trim() || !contactBasis.trim())}
          </div>}
          {(panel === 'stage' || panel === 'reject') && <div className={databaseProfile && panel === 'reject'
            ? 'border border-[#F8B4B4] rounded-xl p-4 bg-[#FFF5F5] space-y-3' : 'space-y-3 border-t pt-4'}>
            {databaseProfile && panel === 'reject' && <h3 className="text-[14px] font-bold text-[#991B1B]">Отклонить отклик</h3>}
            {panel === 'stage' && <label className="block text-sm">Новый этап<select className={field} value={target} onChange={e => { setTarget(e.target.value); setReason(''); }}><option value="">Выберите этап</option>
              {stages.filter(item => !['sent_to_department', 'rejected', detail.stage.code].includes(item.code)).map(item => <option key={item.code} value={item.code}>{item.title}</option>)}
            </select></label>}
            {databaseProfile && panel === 'reject' ? <fieldset>
              <legend className="text-[12px] font-medium text-[#4A5363] mb-1.5">Причина</legend>
              <div className="space-y-1.5 text-[13px] text-[#141A24]">
                {stageReasons.map(item => <label className="flex items-center gap-2 cursor-pointer" key={item.code}>
                  <input type="radio" name="rejectReason" value={item.code} checked={item.code === reason}
                    onChange={e => setReason(e.target.value)} className="text-[#1F4FD1] focus:ring-[#1F4FD1]" /><span>{item.title}</span>
                </label>)}
              </div>
            </fieldset> : ['rejected', 'withdrawn'].includes(target) && <label className="block text-sm">Причина решения<select className={field} value={reason} onChange={e => setReason(e.target.value)}><option value="">Выберите причину</option>
              {stageReasons.map(item => <option key={item.code} value={item.code}>{item.title}</option>)}
            </select></label>}
            <label className={formLabel}>Обоснование решения<textarea rows={3} className={formField} value={comment} onChange={e => setComment(e.target.value)} /></label>
            {panel === 'stage' && <label className="block text-sm"><input type="checkbox" checked={confirmSkip} onChange={e => setConfirmSkip(e.target.checked)} /> Подтверждаю возврат или пропуск этапов по указанной причине</label>}
            {formButtons(panel === 'reject' ? 'Сохранить отказ' : 'Сохранить этап', moveStage,
              busy || !target || !comment.trim() || (['rejected', 'withdrawn'].includes(target) && !reason))}
          </div>}
          {panel && !databaseProfile && <Btn variant="link" disabled={busy} onClick={cancelForm}>Отмена</Btn>}
          {databaseProfile && inArchive && onOpenArchive && <button type="button" onClick={onOpenArchive}
            className="text-[13px] font-medium text-[#1F4FD1] hover:underline">Открыть архив кадров</button>}
        </div>
        {databaseProfile && <ProfileOtherVacancies candidateId={detail.candidate.candidate_id}
          currentPosition={detail.vacancy?.position_code} currentVacancy={detail.vacancy?.vacancy_id} />}
        {!databaseProfile && onOpenArchive && <div className="text-sm text-[#4A5363]">{inArchive && <p>Подборка сохранена</p>}<Btn variant="link" onClick={onOpenArchive}>Открыть архив кадров</Btn></div>}
        {!databaseProfile && <div className="flex flex-wrap gap-3">
          {onRequestClarification && <Btn disabled={busy || !canMove} onClick={onRequestClarification}>Телефонное интервью</Btn>}
          {canMove && <Btn disabled={busy} onClick={() => openPanel('stage')}>Изменить этап</Btn>}
        </div>}
        <div className={profilePanel}>
          <h2 className={profileTitle + ' mb-3'}>История</h2>
          <div className="space-y-2 text-[13px] text-[#4A5363] leading-relaxed">
            {!history?.items.length && <div>Переходов пока нет.</div>}
            {history?.items.map(item => <div key={item.seq}>
              {new Date(item.created_at).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })} · {item.to_stage.title}
              {item.rejection_reason?.title && ' · ' + item.rejection_reason.title}{item.comment && <p>{item.comment}</p>}
            </div>)}
          </div>
          {databaseProfile && canMove && <button type="button" disabled={busy} onClick={() => openPanel('stage')}
            className="text-[13px] font-medium text-[#1F4FD1] hover:underline">Изменить этап</button>}
        </div>
      </div>
    </div>
    {(!databaseProfile || handoffs.length > 0) && <Card className="space-y-4">
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
    </Card>}
  </div>;
}
export default CandidateCard;
