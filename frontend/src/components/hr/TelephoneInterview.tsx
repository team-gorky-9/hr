import { useEffect, useState } from 'react';
import { Card, Btn, Badge, PageTitle } from '../shared/ui';
import { api, request, ApiError, errorMessage, type ApplicationDetail, type Guide, type Interview } from '../../api/recruitment';

interface TelephoneInterviewProps {
  applicationId?: string;
  onBackToCard?: () => void;
  onSaveResult?: (result: string) => void;
}

function requireGuideForApplication(guide: Guide, applicationId: string, interviewId?: string) {
  if (guide.application_id !== applicationId || guide.kind !== 'phone' ||
      (interviewId && guide.interview_id !== interviewId)) {
    throw new Error('Сервер вернул другой список вопросов. Обновите карточку отклика.');
  }
  return guide;
}

function evaluationNotice(detail: ApplicationDetail) {
  switch (detail.assessment_status) {
    case 'ready':
      return 'Можно сформировать вопросы по актуальной оценке этого отклика.';
    case 'mapping_required':
      return detail.applicability?.explanation || 'Публикация отклика ещё не сопоставлена с должностью. Проверьте исходную публикацию.';
    case 'not_applicable':
      return 'Профиль этой должности неприменим к публикации отклика. Проверьте исходную публикацию.';
    case 'no_approved_profile':
      return 'Для должности пока нет утверждённого профиля.';
    case 'stale':
      return 'Оценка устарела. Обновите её в карточке отклика перед формированием вопросов.';
    default:
      return 'Для подготовки вопросов нужна актуальная оценка по утверждённому профилю.';
  }
}

function SelectedInterview({ applicationId, onBackToCard, onSaveResult }: TelephoneInterviewProps & { applicationId: string }) {
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [guide, setGuide] = useState<Guide | null>(null);
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [result, setResult] = useState('continue');
  const [summary, setSummary] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);

  function updateGuide(next: Guide) {
    setGuide(next);
    setNotes(Object.fromEntries([...next.core, ...next.clarifications].map(question => [question.question_id, question.answer?.text || ''])));
  }

  function phoneMeetings(response: { application_id: string; items: Interview[] }) {
    if (response.application_id !== applicationId || response.items.some(item => item.application_id !== applicationId)) {
      throw new Error('Сервер вернул собеседование другого отклика. Обновите карточку.');
    }
    return response.items.filter(item => item.kind === 'phone');
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    const loadGuide = api.guide(applicationId, controller.signal).catch(error => {
      if (error instanceof ApiError && error.status === 404 && error.code === 'GUIDE_NOT_FOUND') return null;
      throw error;
    });
    Promise.all([
      api.application(applicationId, controller.signal),
      loadGuide,
      api.interviews(applicationId, controller.signal),
    ]).then(([application, savedGuide, meetings]) => {
      if (controller.signal.aborted) return;
      if (application.application_id !== applicationId) throw new Error('Сервер вернул другую карточку отклика.');
      const phones = phoneMeetings(meetings);
      const exactGuide = savedGuide ? requireGuideForApplication(savedGuide, applicationId) : null;
      setDetail(application);
      setInterviews(phones);
      if (exactGuide) updateGuide(exactGuide);
      else setGuide(null);
    }).catch(error => {
      if (!controller.signal.aborted) { setDetail(null); setGuide(null); setInterviews([]); setError(errorMessage(error)); }
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [applicationId, reload]);

  async function action(work: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); }
    catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }

  const createGuide = () => action(async () => {
    if (detail?.assessment_status !== 'ready') return;
    const response = await request<Guide>(`/applications/${applicationId}/interview-guide`, 'hr', {
      kind: 'phone', regenerate: false, request_id: crypto.randomUUID(),
    });
    const exactGuide = requireGuideForApplication(response, applicationId);
    setInterviews(phoneMeetings(await api.interviews(applicationId)));
    updateGuide(exactGuide);
  });

  const current = interviews.find(item => item.id === guide?.interview_id);
  const completed = current ? ['continue', 'stop', 'no_answer'].includes(current.result) : false;
  const questions = guide ? [...guide.core, ...guide.clarifications] : [];
  const canSave = Boolean(guide && current && !completed && !loading && !busy);

  async function saveAnswers() {
    if (!guide || !current) return;
    for (const question of questions) {
      const text = (notes[question.question_id] || '').trim();
      if (!text || text === question.answer?.text) continue;
      const saved = await request<{ text: string; revision: number }>(
        `/interviews/${guide.interview_id}/questions/${question.question_id}/answers`, 'hr', {
          text, source: 'phone', expected_revision: question.answer?.revision || 0, request_id: crypto.randomUUID(),
        },
      );
      const updateAnswer = (items: Guide['core']) => items.map(item => item.question_id === question.question_id
        ? { ...item, answer: saved } : item);
      setGuide(previous => previous && {
        ...previous, core: updateAnswer(previous.core), clarifications: updateAnswer(previous.clarifications),
      });
    }
    updateGuide(requireGuideForApplication(await api.guide(applicationId), applicationId, guide.interview_id));
  }

  const complete = () => action(async () => {
    if (!guide || !current) return;
    await saveAnswers();
    await request(`/interviews/${guide.interview_id}/outcome`, 'hr', {
      expected_revision: current.revision, result, occurred_at: new Date().toISOString(), summary,
    });
    setNotice('Итог встречи сохранён. Этап отклика не изменён.');
    setReload(value => value + 1);
    onSaveResult?.(result);
  });

  const vacancyTitle = detail?.vacancy?.title || detail?.posting_title;
  const context = detail && [detail.candidate.contacts?.full_name || detail.candidate.code, vacancyTitle].filter(Boolean).join(' · ');
  const differsFromVacancy = detail?.target_position_code && detail.target_position_code !== detail.vacancy?.position_code;

  return <div className="max-w-[1240px] mx-auto px-6 py-8 space-y-5">
    <Btn variant="link" onClick={onBackToCard}>← Карточка отклика</Btn>
    <PageTitle title="Телефонное собеседование" subtitle={context || 'Вопросы, ответы кандидата и итог встречи'} />
    {differsFromVacancy && detail.posting_title && <p className="text-sm text-[#616977]">
      Профиль для собеседования определён по подтверждённой публикации «{detail.posting_title}».
    </p>}
    {error && <div role="alert" className="bg-red-50 text-red-800 p-4 rounded-xl">
      {error} <Btn onClick={() => setReload(value => value + 1)}>Повторить чтение</Btn>
    </div>}
    {notice && <p role="status" className="bg-green-50 p-4 rounded-xl">{notice}</p>}
    {loading ? <Card>Загрузка собеседования…</Card> : detail && (!guide ? <Card className="space-y-4">
      <h2 className="text-xl font-bold">Вопросы ещё не сформированы</h2>
      <p>{evaluationNotice(detail)}</p>
      {detail.assessment_status === 'ready' && <Btn variant="primary" disabled={busy} onClick={createGuide}>
        {busy ? 'Формирование…' : 'Сформировать вопросы'}
      </Btn>}
    </Card> : <div className="grid lg:grid-cols-[1.6fr_1fr] gap-6 items-start">
      <Card className="space-y-5">
        <div className="flex justify-between">
          <h2 className="text-xl font-bold">Вопросы к звонку</h2>
          <Badge tone={guide.is_stale ? 'amber' : 'blue'}>Версия {guide.guide_version}{guide.is_stale ? ' · устарела' : ''}</Badge>
        </div>
        {questions.map((question, index) => <div key={question.question_id} className="border border-[#E1E5EB] rounded-xl p-4 space-y-3">
          <b>{index + 1}. {question.question}</b>
          {question.gap && <p className="text-sm text-[#616977]">{question.gap}</p>}
          {question.criterion?.good_answer && <p className="text-sm">Ориентир: {question.criterion.good_answer}</p>}
          <textarea aria-label={`Ответ на вопрос ${index + 1}`} disabled={!canSave} className="w-full border border-[#C9D0DB] rounded-xl p-3 min-h-24"
            placeholder="Ответ кандидата со слов" value={notes[question.question_id] || ''}
            onChange={event => setNotes(previous => ({ ...previous, [question.question_id]: event.target.value }))} />
          <p className="text-xs text-[#616977]">{question.answer ? `Сохранена ревизия ${question.answer.revision}` : 'Ответ ещё не сохранён'}</p>
        </div>)}
        {guide.document_requests.map(document => <p key={document.requirement_id}>Запросить документ: {document.title}{document.reason && ' · ' + document.reason}</p>)}
        <Btn disabled={!canSave} onClick={() => action(async () => {
          await saveAnswers(); setNotice('Ответы сохранены. Слова кандидата не подтверждают требование автоматически.');
        })}>Сохранить ответы</Btn>
      </Card>
      <Card className="space-y-4">
        <h2 className="text-xl font-bold">Итог встречи</h2>
        {completed ? <><Badge tone="green">Встреча завершена</Badge><p>{current?.summary}</p>
          <p>{current?.result === 'no_answer' ? 'Кандидат не ответил' : current?.result === 'continue' ? 'Продолжить рассмотрение' : 'Остановить рассмотрение'}</p>
        </> : <>
          <select aria-label="Итог встречи" className="w-full border rounded-xl p-3" value={result} onChange={event => setResult(event.target.value)}>
            <option value="continue">Продолжить рассмотрение</option><option value="stop">Остановить рассмотрение</option><option value="no_answer">Не удалось связаться</option>
          </select>
          <textarea aria-label="Обоснование итога" className="w-full border rounded-xl p-3 min-h-32" placeholder="Что установлено и какой следующий шаг"
            value={summary} onChange={event => setSummary(event.target.value)} />
          <Btn variant="primary" disabled={!canSave || summary.trim().length < 5} onClick={complete}>Сохранить итог</Btn>
        </>}
        <p className="text-sm text-[#616977]">Итог встречи не меняет этап отклика. Решение и передача выполняются в карточке.</p>
      </Card>
    </div>)}
  </div>;
}

export function TelephoneInterview({ applicationId = '', ...props }: TelephoneInterviewProps) {
  const chosen = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(applicationId);
  if (chosen) return <SelectedInterview key={applicationId} applicationId={applicationId} {...props} />;
  return <div className="max-w-[1240px] mx-auto px-6 py-8 space-y-5">
    <PageTitle title="Телефонное собеседование" subtitle="Вопросы, ответы кандидата и итог встречи" />
    <Card><p>Откройте телефонное собеседование из карточки выбранного отклика.</p></Card>
  </div>;
}

export default TelephoneInterview;
