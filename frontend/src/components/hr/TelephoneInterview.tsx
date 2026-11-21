import React, { useEffect, useState } from 'react';
import { Card, Btn, Badge, PageTitle } from '../shared/ui';
import { api, request, ApiError, errorMessage, type Guide, type Interview } from '../../api/recruitment';
interface TelephoneInterviewProps { applicationId?: string; onBackToCard?: () => void; onSaveResult?: (result: string) => void }
export const TelephoneInterview: React.FC<TelephoneInterviewProps> = ({ applicationId = '', onBackToCard, onSaveResult }) => {
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
  const updateGuide = (g: Guide) => { setGuide(g); setNotes(Object.fromEntries([...g.core, ...g.clarifications].map(q => [q.question_id, q.answer?.text || '']))); };
  // The tab can be opened before any application is chosen (the app starts with a placeholder id).
  const chosen = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(applicationId);
  useEffect(() => {
    if (!chosen) { setLoading(false); return; }
    let live = true; setLoading(true); setError('');
    Promise.all([api.guide(applicationId).catch(e => { if (e instanceof ApiError && e.status === 404) return null; throw e; }), api.interviews(applicationId)])
      .then(([g, meetings]) => { if (live) { if (g) updateGuide(g); else setGuide(null); setInterviews(meetings.items); setLoading(false); } })
      .catch(e => { if (live) { setError(errorMessage(e)); setLoading(false); } });
    return () => { live = false; };
  }, [applicationId, chosen, reload]);
  const action = async (work: () => Promise<void>) => { setBusy(true); setError(''); setNotice(''); try { await work(); } catch(e) { setError(errorMessage(e)); } finally { setBusy(false); } };
  const createGuide = () => action(async () => { updateGuide(await request<Guide>(`/applications/${applicationId}/interview-guide`, 'hr', { kind: 'phone', regenerate: false, request_id: crypto.randomUUID() })); setInterviews((await api.interviews(applicationId)).items); });
  const current = interviews.find(i => i.id === guide?.interview_id);
  const completed = current ? ['continue', 'stop', 'no_answer'].includes(current.result) : false;
  const saveAnswers = async () => {
    if (!guide) return;
    for (const q of [...guide.core, ...guide.clarifications]) {
      const text = (notes[q.question_id] || '').trim();
      if (text && text !== q.answer?.text) {
        const saved = await request<{ text: string; revision: number }>(`/interviews/${guide.interview_id}/questions/${q.question_id}/answers`, 'hr', { text, source: 'phone', expected_revision: q.answer?.revision || 0, request_id: crypto.randomUUID() });
        q.answer = saved;
      }
    }
    updateGuide(await api.guide(applicationId));
  };
  const complete = () => action(async () => {
    if (!guide || !current) return;
    await saveAnswers();
    await request(`/interviews/${guide.interview_id}/outcome`, 'hr', { expected_revision: current.revision, result, occurred_at: new Date().toISOString(), summary });
    setNotice('Итог встречи сохранён. Этап отклика не изменён.'); setReload(n => n + 1); onSaveResult?.(result);
  });
  if (!chosen) return <div className="max-w-[1240px] mx-auto px-6 py-8 space-y-5"><PageTitle title="Телефонное интервью" subtitle="Вопросы, ответы кандидата и итог встречи" /><Card><p>Сначала выберите отклик: «Отклики по вакансиям» → вакансия → карточка отклика. Затем откройте эту вкладку — интервью будет по выбранному отклику.</p></Card></div>;
  return <div className="max-w-[1240px] mx-auto px-6 py-8 space-y-5"><Btn variant="link" onClick={onBackToCard}>← Карточка отклика</Btn><PageTitle title="Телефонное интервью" subtitle="Вопросы, ответы кандидата и итог встречи" />
    {error && <div role="alert" className="bg-red-50 text-red-800 p-4 rounded-xl">{error} <Btn onClick={() => setReload(n => n + 1)}>Повторить чтение</Btn></div>}{notice && <p role="status" className="bg-green-50 p-4 rounded-xl">{notice}</p>}
    {loading ? <Card>Загрузка интервью…</Card> : !guide ? <Card className="space-y-4"><h2 className="text-xl font-bold">Гайд ещё не сформирован</h2><p>Для подготовки вопросов нужна актуальная оценка по утверждённому профилю вакансии.</p><Btn variant="primary" disabled={busy || !applicationId} onClick={createGuide}>Сформировать гайд</Btn></Card> : <div className="grid grid-cols-[1.6fr_1fr] gap-6 items-start"><Card className="space-y-5"><div className="flex justify-between"><h2 className="text-xl font-bold">Вопросы к звонку</h2><Badge tone={guide.is_stale ? 'amber' : 'blue'}>Версия {guide.guide_version}{guide.is_stale ? ' · устарела' : ''}</Badge></div>
      {[...guide.core, ...guide.clarifications].map((q, i) => <div key={q.question_id} className="border border-[#E1E5EB] rounded-xl p-4 space-y-3"><b>{i + 1}. {q.question}</b><p className="text-sm text-[#616977]">{q.gap}</p>{q.criterion?.good_answer && <p className="text-sm">Ориентир: {q.criterion.good_answer}</p>}<textarea aria-label={`Ответ на вопрос ${i + 1}`} disabled={busy || completed} className="w-full border border-[#C9D0DB] rounded-xl p-3 min-h-24" placeholder="Ответ кандидата со слов" value={notes[q.question_id] || ''} onChange={e => setNotes(n => ({ ...n, [q.question_id]: e.target.value }))} /><p className="text-xs text-[#616977]">{q.answer ? `Сохранена ревизия ${q.answer.revision}` : 'Ответ ещё не сохранён'}</p></div>)}
      {guide.document_requests.map(d => <p key={d.requirement_id}>Запросить документ: {d.title} · {d.reason}</p>)}<Btn disabled={busy || completed} onClick={() => action(async () => { await saveAnswers(); setNotice('Ответы сохранены. Слова кандидата не подтверждают требование автоматически.'); })}>Сохранить ответы</Btn>
    </Card><Card className="space-y-4"><h2 className="text-xl font-bold">Итог встречи</h2>{completed ? <><Badge tone="green">Встреча завершена</Badge><p>{current?.summary}</p><p>{current?.result === 'no_answer' ? 'Кандидат не ответил' : current?.result === 'continue' ? 'Продолжить рассмотрение' : 'Остановить рассмотрение'}</p></> : <><select aria-label="Итог встречи" className="w-full border rounded-xl p-3" value={result} onChange={e => setResult(e.target.value)}><option value="continue">Продолжить рассмотрение</option><option value="stop">Остановить рассмотрение</option><option value="no_answer">Не удалось связаться</option></select><textarea aria-label="Обоснование итога" className="w-full border rounded-xl p-3 min-h-32" placeholder="Что установлено и какой следующий шаг" value={summary} onChange={e => setSummary(e.target.value)} /><Btn variant="primary" disabled={busy || !current || summary.trim().length < 5} onClick={complete}>Сохранить итог</Btn></>}<p className="text-sm text-[#616977]">Итог встречи не меняет этап отклика. Решение и передача выполняются в карточке.</p></Card></div>}
  </div>;
};
export default TelephoneInterview;
