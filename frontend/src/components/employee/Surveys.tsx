import { useEffect, useState, type FormEvent } from 'react';
import { Card, Btn, Badge } from '../shared/ui';

type Survey = {
  title: string;
  status: string;
  privacy_notice: string;
  questions: { key: string; text: string; min: number; max: number }[];
  topic_options: { key: string; label: string }[];
};

const env = (import.meta as ImportMeta & { env: Record<string, string> }).env;
const base = (env.VITE_FEEDBACK_API_BASE || '/feedback/api/v1/feedback').replace(/\/$/, '');
const cycleId = new URLSearchParams(window.location.search).get('cycle');
const validCycle = Boolean(cycleId && /^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i.test(cycleId));
const field = 'block w-full rounded-xl border border-[#C9D0DB] bg-white px-4 py-3';

async function surveyRequest<T>(suffix: string, init?: RequestInit): Promise<T> {
  const response = await fetch(base + '/cycles/' + cycleId + suffix, {
    ...init, credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer',
  });
  const result = await response.json().catch(() => null);
  if (!response.ok) {
    const code = result?.detail?.code;
    if (code === 'CODE_ALREADY_USED') throw new Error('Этот код уже использован.');
    if (code === 'INVALID_CODE') throw new Error('Проверьте код для этого опроса.');
    if (response.status === 409) throw new Error('Ответы на этот опрос больше не принимаются.');
    if (response.status === 404) throw new Error('Опрос по этому приглашению недоступен.');
    throw new Error('Не удалось выполнить запрос. Проверьте поля или повторите позже.');
  }
  if (!result) throw new Error('Сервис опросов недоступен.');
  return result as T;
}

export default function Surveys() {
  const [survey, setSurvey] = useState<Survey | null>(null);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [topic, setTopic] = useState('');
  const [code, setCode] = useState('');
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!validCycle) return;
    const controller = new AbortController();
    setError('');
    surveyRequest<Survey>('/form', { signal: controller.signal })
      .then((form) => { if (!controller.signal.aborted) setSurvey(form); })
      .catch((failure) => { if (!controller.signal.aborted) setError(failure.message); });
    return () => controller.abort();
  }, [reload]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!survey || busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await surveyRequest<{ accepted: boolean }>('/responses', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          access_code: code.trim(),
          answers: survey.questions.map(({ key }) => ({ question_key: key, value: Number(choices[key]) })),
          topic_key: topic,
        }),
      });
      if (!result.accepted) throw new Error('Ответы не приняты. Повторите запрос.');
      setCode('');
      setChoices({});
      setTopic('');
      setDone(true);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Не удалось отправить ответы.');
    } finally {
      setBusy(false);
    }
  }

  return <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
    <div className="bg-[#F1EDFF] rounded-3xl p-8 flex items-center gap-5">
      <div aria-hidden="true" className="w-16 h-16 shrink-0 bg-white rounded-2xl grid place-items-center text-[28px]">🛡</div>
      <div><h1 className="text-[32px] font-bold">Опросы</h1><p className="text-[#4A5363]">Анонимные опросы сотрудников</p></div>
    </div>
    <div className="grid lg:grid-cols-[2fr_1fr] gap-5 items-start">
      <Card className="space-y-4">
        {!validCycle && <p>{cycleId ? 'Ссылка на опрос некорректна. Проверьте приглашение.' : 'Откройте ссылку из приглашения на опрос.'}</p>}
        {validCycle && !survey && !error && <p>Загружаем опрос…</p>}
        {error && <p role="alert" className="text-[#A3171B]">{error}</p>}
        {error && !survey && <Btn variant="link" onClick={() => setReload((value) => value + 1)}>Повторить</Btn>}
        {done && <p role="status" className="text-[22px] font-bold text-[#1D7A40]">Спасибо, ответы приняты анонимно.</p>}
        {survey && !done && <>
          <h2 className="text-[24px] font-bold">{survey.title}</h2>
          {survey.status !== 'open' ? <Badge>Приём ответов завершён</Badge> : <form onSubmit={submit}>
            <fieldset disabled={busy} className="space-y-4">
              {survey.questions.map((question) => <label key={question.key} className="block space-y-2">
                <span className="font-semibold">{question.text}</span>
                <select className={field} required value={choices[question.key] ?? ''} onChange={(event) => {
                  const value = event.target.value;
                  setChoices((previous) => ({ ...previous, [question.key]: value }));
                }}>
                  <option value="">Выберите оценку</option>
                  {Array.from({ length: question.max - question.min + 1 }, (_, index) => question.min + index).map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </label>)}
              <label className="block space-y-2"><span className="font-semibold">Тема</span>
                <select className={field} required value={topic} onChange={(event) => setTopic(event.target.value)}>
                  <option value="">Выберите тему</option>
                  {survey.topic_options.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}
                </select>
              </label>
              <label className="block space-y-2"><span className="font-semibold">Одноразовый код из приглашения</span>
                <input className={field} type="password" autoComplete="off" value={code} minLength={20} maxLength={200} required onChange={(event) => setCode(event.target.value)} />
              </label>
              <Btn type="submit" variant="primary" disabled={busy}>{busy ? 'Отправляем…' : 'Отправить ответы'}</Btn>
            </fieldset>
          </form>}
        </>}
      </Card>
      {survey?.privacy_notice && <Card className="space-y-3"><h2 className="text-[20px] font-bold">Как сохраняются ответы</h2><p>{survey.privacy_notice}</p></Card>}
    </div>
  </div>;
}

