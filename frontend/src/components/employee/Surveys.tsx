import { useEffect, useState, type FormEvent } from 'react';
import { feedbackApi, type DemoCycle } from '../../api/feedback';
import { Card, Btn, Badge } from '../shared/ui';

const field = 'block w-full rounded-xl border border-[#C9D0DB] bg-white px-4 py-3';
const cyclePattern = /^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i;
const failureMessage = (failure: unknown) => failure instanceof Error ? failure.message : 'Сервис опросов недоступен.';

function useRead<T>(id: string, read: (id: string, signal: AbortSignal) => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError('');
    setData(null);
    read(id, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((failure) => { if (!controller.signal.aborted) setError(failureMessage(failure)); });
    return () => controller.abort();
  }, [id, read, reload]);
  return { data, error, retry: () => setReload((value) => value + 1) };
}

function LoadError({ error, retry }: { error: string; retry: () => void }) {
  return <Card className="space-y-2">
    <p role="alert" className="text-[#A3171B]">{error}</p>
    <Btn variant="link" onClick={retry}>Повторить</Btn>
  </Card>;
}

function Distribution({ title, options, count }: {
  title: string;
  options: { label: string; count?: number }[];
  count: number;
}) {
  return <figure className="space-y-2 rounded-xl border border-[#E1E5EB] p-4">
    <figcaption className="font-semibold">{title}</figcaption>
    {options.length && options.every((item) => item.count !== undefined) ? <ul className="space-y-2">
      {options.map((item) => <li key={item.label} className="grid grid-cols-[minmax(3rem,1fr)_2fr_auto] items-center gap-3 text-[14px]">
        <span>{item.label}</span>
        <span aria-hidden="true" className="h-3 overflow-hidden rounded-full bg-[#F1EDFF]">
          <span className="block h-full rounded-full bg-[#7C5CDB]" style={{ width: ((item.count ?? 0) / count) * 100 + '%' }} />
        </span>
        <span>{item.count}</span>
      </li>)}
    </ul> : <p className="text-[14px] text-[#4A5363]">Распределение скрыто по правилам публикации.</p>}
  </figure>;
}

function PublishedResults({ id, title }: { id: string; title: string }) {
  const { data, error, retry } = useRead(id, feedbackApi.results);
  if (error) return <LoadError error={error} retry={retry} />;
  if (!data) return <Card>Загружаем опубликованные итоги…</Card>;
  return <Card className="space-y-5">
    <div className="space-y-2"><Badge tone="green">Итоги опубликованы</Badge><h2 className="text-[24px] font-bold">{title}</h2></div>
    {data.groups.map((group) => <section key={group.key} className="space-y-3">
      <h3 className="text-[18px] font-bold">{group.label}</h3>
      {group.status === 'suppressed' ? <p className="text-[#4A5363]">Данные этой группы скрыты по правилам публикации.</p> : <>
        <p className="text-[#4A5363]">Ответов в группе: {group.response_count}</p>
        {data.questions.map((question, index) => <Distribution key={question.key} title={`${index + 1}. ${question.text}`}
          count={group.response_count} options={(group.scales.find((scale) => scale.question_key === question.key)?.categories ?? [])
            .map((category) => ({ label: String(category.value), count: category.status === 'shown' ? category.count : undefined }))} />)}
        <Distribution title="Темы, выбранные в ответах" count={group.response_count}
          options={data.topic_options.map((topic) => {
            const option = group.topics.find((entry) => entry.key === topic.key);
            return { label: topic.label, count: option?.status === 'shown' ? option.count : undefined };
          })} />
      </>}
    </section>)}
    <p className="text-[13px] text-[#4A5363]">{data.notice}</p>
  </Card>;
}

function ActiveSurvey({ id }: { id: string }) {
  const { data: survey, error: loadError, retry } = useRead(id, feedbackApi.form);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [topic, setTopic] = useState('');
  const [code, setCode] = useState('');
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!survey || busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await feedbackApi.submit(id, {
        access_code: code.trim(),
        answers: survey.questions.map(({ key }) => ({ question_key: key, value: Number(choices[key]) })),
        topic_key: topic,
      });
      if (!result.accepted) throw new Error('Ответы не приняты. Повторите запрос.');
      setCode('');
      setChoices({});
      setTopic('');
      setDone(true);
    } catch (failure) {
      setError(failureMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  if (loadError) return <LoadError error={loadError} retry={retry} />;
  if (!survey) return <Card>Загружаем опрос…</Card>;
  return <Card className="space-y-4">
    <div className="space-y-2">
      <Badge tone={survey.status === 'open' ? 'purple' : 'gray'}>{survey.status === 'open' ? 'Приём ответов открыт' : 'Опрос завершён'}</Badge>
      <h2 className="text-[24px] font-bold">{survey.title}</h2>
      <p className="text-[14px] text-[#4A5363]">Итоги пока не опубликованы.</p>
    </div>
    {error && <p role="alert" className="text-[#A3171B]">{error}</p>}
    {done && <p role="status" className="text-[18px] font-bold text-[#1D7A40]">Спасибо, ответы приняты анонимно.</p>}
    {survey.status === 'open' && !done && <form onSubmit={submit}>
      <fieldset disabled={busy} className="space-y-5">
        {survey.questions.map((question, index) => <label key={question.key} className="block space-y-2">
          <span className="font-semibold">{index + 1}. {question.text}</span>
          <select className={field} required value={choices[question.key] ?? ''} onChange={(event) => {
            const value = event.target.value;
            setChoices((previous) => ({ ...previous, [question.key]: value }));
          }}>
            <option value="">Выберите оценку от {question.min} до {question.max}</option>
            {Array.from({ length: question.max - question.min + 1 }, (_, position) => question.min + position).map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>)}
        <label className="block space-y-2"><span className="font-semibold">Какую тему стоит обсудить?</span>
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
    {survey.privacy_notice && <details className="border-t border-[#E1E5EB] pt-3 text-[14px] text-[#4A5363]">
      <summary className="cursor-pointer font-semibold">Как сохраняются ответы</summary><p className="mt-2">{survey.privacy_notice}</p>
    </details>}
  </Card>;
}

const catalog = (_id: string, signal: AbortSignal) => feedbackApi.catalog(signal);

export default function Surveys() {
  const { data, error, retry } = useRead('', catalog);
  const [choice, setChoice] = useState(() => {
    const id = new URLSearchParams(window.location.search).get('cycle') ?? '';
    return cyclePattern.test(id) ? id : '';
  });
  const cycles = data?.items ?? [];
  const selectedId = choice || cycles.find((cycle) => cycle.status === 'open')?.id || cycles[0]?.id;
  const selectedCycle = cycles.find((cycle) => cycle.id === selectedId);

  function select(cycle: DemoCycle) {
    setChoice(cycle.id);
    const url = new URL(window.location.href);
    url.searchParams.set('workspace', 'surveys');
    url.searchParams.set('cycle', cycle.id);
    window.history.replaceState(window.history.state, '', url);
  }

  return <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
    <div data-tour="employee-surveys-hero" className="bg-[#F1EDFF] rounded-3xl p-8 flex items-center gap-5">
      <div aria-hidden="true" className="w-16 h-16 shrink-0 bg-white rounded-2xl grid place-items-center text-[28px]">🛡</div>
      <div><h1 className="text-[32px] font-bold">Опросы</h1><p className="text-[#4A5363]">Анонимные опросы сотрудников</p></div>
    </div>
    <div data-tour="employee-surveys-workspace" className="grid lg:grid-cols-[2fr_1fr] gap-5 items-start">
      <aside className="space-y-3 lg:col-start-2">
        <Card className="space-y-3">
          <h2 className="text-[20px] font-bold">Учебные опросы</h2>
          {!data && !error && <p>Загружаем список…</p>}
          {error && <p role="alert" className="text-[#A3171B]">{error} <Btn variant="link" onClick={retry}>Повторить</Btn></p>}
          {data && !cycles.length && <p>Доступных учебных опросов пока нет.</p>}
          {cycles.length > 0 && <ul className="space-y-2">
            {cycles.map((cycle) => <li key={cycle.id}><button type="button" aria-pressed={cycle.id === selectedId}
              onClick={() => select(cycle)} className={`w-full space-y-2 text-left rounded-xl border p-3 transition-colors ${cycle.id === selectedId ? 'border-[#1F4FD1] bg-[#EEF3FE]' : 'border-[#E1E5EB] hover:bg-[#F3F5F8]'}`}>
              <span className="block font-semibold">{cycle.title}</span>
              <Badge tone={cycle.status === 'open' ? 'purple' : cycle.has_results ? 'green' : 'gray'}>
                {cycle.status === 'open' ? 'Текущий опрос' : cycle.has_results ? 'Итоги опубликованы' : 'Завершён'}
              </Badge>
            </button></li>)}
          </ul>}
        </Card>
      </aside>
      <div className="space-y-3 lg:row-start-1 lg:col-start-1">
        {selectedId ? selectedCycle?.has_results
          ? <PublishedResults key={selectedId} id={selectedId} title={selectedCycle.title} />
          : <ActiveSurvey key={selectedId} id={selectedId} />
          : data && <Card>Откройте ссылку из приглашения или выберите учебный опрос.</Card>}
      </div>
    </div>
  </div>;
}

