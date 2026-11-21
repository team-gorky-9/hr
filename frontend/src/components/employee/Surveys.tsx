import React, { useEffect, useState, type FormEvent } from 'react';
import { feedbackApi, type DemoCycle, type SurveyForm, type SurveyResults } from '../../api/feedback';
import { Card, Btn, Badge } from '../shared/ui';

const cyclePattern = /^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i;
const failureMessage = (failure: unknown) => (failure instanceof Error ? failure.message : 'Сервис опросов недоступен.');

const scaleHints: Record<number, string> = {
  1: '1 — совсем не согласен',
  2: '2 — скорее не согласен',
  3: '3 — нейтрально',
  4: '4 — скорее согласен',
  5: '5 — полностью согласен',
};

const fallbackChanges = [
  'Сделали 2 переговорные для тихой работы',
  'Заменили 40 компьютеров в 3 департаментах',
  'Закупку кресел включили в план на 2027 год',
];

function useRead<T>(id: string, read: (id: string, signal: AbortSignal) => Promise<T>, enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!enabled) {
      setData(null);
      setError('');
      return;
    }
    const controller = new AbortController();
    setError('');
    setData(null);
    read(id, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(failureMessage(failure));
      });
    return () => controller.abort();
  }, [id, read, reload, enabled]);
  return { data, error, retry: () => setReload((value) => value + 1) };
}

function ActiveSurveyCard({ id }: { id: string }) {
  const { data: survey, error, retry } = useRead<SurveyForm>(id, feedbackApi.form, Boolean(id));
  const [step, setStep] = useState(0);
  const [choices, setChoices] = useState<Record<string, number>>({});
  const [topic, setTopic] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [done, setDone] = useState(false);

  useEffect(() => {
    setStep(0);
    setChoices({});
    setTopic('');
    setCode('');
    setSubmitError('');
    setDone(false);
  }, [id]);

  if (error) {
    return (
      <Card className="space-y-3">
        <p role="alert" className="text-[#A3171B]">{error}</p>
        <Btn variant="link" onClick={retry}>Повторить</Btn>
      </Card>
    );
  }
  if (!survey) {
    return <Card className="space-y-3"><p className="text-[16px] text-[#4A5363]">Загружаем анкету…</p></Card>;
  }

  const totalQuestions = survey.questions.length;
  const topicStep = totalQuestions;
  const confirmStep = totalQuestions + 1;
  const totalSteps = totalQuestions + 2;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!survey || busy) return;
    setSubmitError('');
    const answers = survey.questions.map((question) => ({ question_key: question.key, value: choices[question.key] }));
    if (answers.some((item) => !Number.isInteger(item.value))) {
      setSubmitError('Ответьте на все вопросы перед отправкой.');
      return;
    }
    if (!topic) {
      setSubmitError('Выберите тему для обсуждения.');
      return;
    }
    if (code.trim().length < 20) {
      setSubmitError('Введите одноразовый код из приглашения.');
      return;
    }
    setBusy(true);
    try {
      const result = await feedbackApi.submit(id, { access_code: code.trim(), answers, topic_key: topic });
      if (!result.accepted) throw new Error('Ответы не приняты. Повторите запрос.');
      setDone(true);
      setCode('');
    } catch (failure) {
      setSubmitError(failureMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  if (survey.status !== 'open') {
    return (
      <Card className="space-y-3">
        <div className="flex items-center gap-3"><Badge tone="gray">Завершён</Badge></div>
        <h2 className="text-[24px] font-bold">{survey.title}</h2>
        <p className="text-[16px] text-[#4A5363]">Приём ответов по этому опросу завершён.</p>
      </Card>
    );
  }

  if (done) {
    return (
      <Card className="space-y-4">
        <div className="py-10 text-center space-y-3">
          <div className="text-[22px] font-bold text-[#1D7A40]">Спасибо! Ответы приняты анонимно</div>
          <p className="text-[15px] text-[#4A5363]">Одноразовый код погашен, ответы не связаны с вашей учётной записью.</p>
          <Btn onClick={() => { setDone(false); setStep(0); setChoices({}); setTopic(''); setCode(''); }}>Пройти с новым кодом</Btn>
        </div>
      </Card>
    );
  }

  const currentQuestion = step < totalQuestions ? survey.questions[step] : null;
  const scaleValues = currentQuestion
    ? Array.from({ length: currentQuestion.max - currentQuestion.min + 1 }, (_, i) => currentQuestion.min + i)
    : [];
  const canNext = currentQuestion
    ? Number.isInteger(choices[currentQuestion.key])
    : step === topicStep
      ? Boolean(topic)
      : false;

  return (
    <Card className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone="purple">Новый</Badge>
        <span className="text-[15px] text-[#4A5363]">
          Шаг {step + 1} из {totalSteps} · около 2 минут · {survey.title}
        </span>
      </div>

      {currentQuestion && (
        <>
          <h2 className="text-[24px] font-bold">{currentQuestion.text}</h2>
          <div className="space-y-3">
            {scaleValues.map((value) => {
              const selected = choices[currentQuestion.key] === value;
              const label = currentQuestion.min === 1 && currentQuestion.max === 5 && scaleHints[value]
                ? scaleHints[value]
                : `Оценка ${value}`;
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => setChoices((prev) => ({ ...prev, [currentQuestion.key]: value }))}
                  className={`w-full text-left rounded-xl border-2 px-5 py-4 text-[18px] transition-colors ${
                    selected ? 'border-[#1F4FD1] bg-[#EEF3FE]' : 'border-[#E1E5EB] bg-white hover:bg-[#F8F9FB]'
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
          <div className="flex flex-wrap items-center gap-4 pt-1">
            <Btn variant="primary" disabled={!canNext} onClick={() => setStep(step + 1)}>Дальше</Btn>
            {step > 0 && <Btn variant="link" onClick={() => setStep(step - 1)}>Назад</Btn>}
          </div>
        </>
      )}

      {step === topicStep && (
        <>
          <h2 className="text-[24px] font-bold">Какую тему стоит обсудить в первую очередь?</h2>
          <div className="space-y-3">
            {survey.topic_options.map((option) => {
              const selected = topic === option.key;
              return (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => setTopic(option.key)}
                  className={`w-full text-left rounded-xl border-2 px-5 py-4 text-[18px] transition-colors ${
                    selected ? 'border-[#1F4FD1] bg-[#EEF3FE]' : 'border-[#E1E5EB] bg-white hover:bg-[#F8F9FB]'
                  }`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
          <div className="flex flex-wrap items-center gap-4 pt-1">
            <Btn variant="primary" disabled={!canNext} onClick={() => setStep(confirmStep)}>Дальше</Btn>
            <Btn variant="link" onClick={() => setStep(Math.max(0, totalQuestions - 1))}>Назад</Btn>
          </div>
        </>
      )}

      {step === confirmStep && (
        <form onSubmit={submit} className="space-y-4">
          <h2 className="text-[24px] font-bold">Подтвердите отправку одноразовым кодом</h2>
          <p className="text-[15px] text-[#4A5363]">
            Код проверяет право участия и сразу гасится. Ответы сохраняются без привязки к сотруднику.
          </p>
          <label className="block space-y-2">
            <span className="text-[15px] font-semibold">Одноразовый код из приглашения</span>
            <input
              type="password"
              autoComplete="off"
              minLength={20}
              maxLength={200}
              required
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder="Вставьте код из приглашения"
              className="w-full rounded-xl border border-[#C9D0DB] bg-white px-4 py-3 text-[16px] outline-none focus:border-[#1F4FD1]"
            />
          </label>
          {submitError && <p role="alert" className="text-[#A3171B] text-[15px]">{submitError}</p>}
          <div className="flex flex-wrap items-center gap-4">
            <Btn type="submit" variant="primary" disabled={busy}>{busy ? 'Отправляем…' : 'Отправить ответы'}</Btn>
            <Btn type="button" variant="link" onClick={() => setStep(topicStep)}>Назад</Btn>
          </div>
        </form>
      )}

      {survey.privacy_notice && (
        <details className="border-t border-[#E1E5EB] pt-3 text-[14px] text-[#4A5363]">
          <summary className="cursor-pointer font-semibold">Как сохраняются ответы</summary>
          <p className="mt-2">{survey.privacy_notice}</p>
        </details>
      )}
    </Card>
  );
}

function PublishedResultsCard({ cycle }: { cycle: DemoCycle }) {
  const { data, error, retry } = useRead<SurveyResults>(cycle.id, feedbackApi.results, Boolean(cycle.id));

  if (error) {
    return (
      <Card className="space-y-3">
        <h2 className="text-[22px] font-bold">Итоги опроса «{cycle.title}»</h2>
        <p role="alert" className="text-[#A3171B]">{error}</p>
        <Btn variant="link" onClick={retry}>Повторить</Btn>
      </Card>
    );
  }
  if (!data) {
    return (
      <Card className="space-y-3">
        <h2 className="text-[22px] font-bold">Итоги опроса «{cycle.title}»</h2>
        <p className="text-[15px] text-[#4A5363]">Загружаем опубликованные итоги…</p>
      </Card>
    );
  }

  const shownGroups = data.groups.filter(
    (group): group is Extract<SurveyResults['groups'][number], { status: 'shown' }> => group.status === 'shown'
  );
  const totalResponses = shownGroups.reduce((sum, group) => sum + group.response_count, 0);

  const topicRows = data.topic_options.map((topic) => {
    let known = false;
    let count = 0;
    for (const group of shownGroups) {
      const entry = group.topics.find((item) => item.key === topic.key);
      if (entry && entry.status === 'shown') {
        known = true;
        count += entry.count;
      }
    }
    const pct = totalResponses > 0 ? Math.round((count / totalResponses) * 100) : 0;
    return { key: topic.key, label: topic.label, known, count, pct };
  });

  const maxPct = Math.max(1, ...topicRows.map((row) => row.pct));

  return (
    <Card className="space-y-3">
      <h2 className="text-[22px] font-bold">Итоги опроса «{cycle.title}»</h2>
      <p className="text-[15px] text-[#4A5363]">
        {totalResponses > 0
          ? `Ответили ${totalResponses} сотрудников · опубликованные итоги`
          : 'Детальное распределение скрыто по правилам анонимности.'}
      </p>
      {shownGroups.length > 0 && topicRows.some((row) => row.known) ? (
        topicRows.map((row) => (
          <div key={row.key} className="flex items-center gap-4 text-[17px]">
            <span className="w-[200px] shrink-0">{row.label}</span>
            <div className="flex-1 h-[30px] rounded-md bg-[#F0F2F6] overflow-hidden">
              <div
                className="h-full bg-[#7C5CDB] rounded-md"
                style={{ width: `${row.known ? (row.pct / maxPct) * 100 : 0}%` }}
              />
            </div>
            <span className="w-10 font-bold text-right">{row.known ? row.pct : '—'}</span>
            <span className="text-[#4A5363]">{row.known ? '%' : ''}</span>
          </div>
        ))
      ) : (
        <p className="text-[15px] text-[#4A5363]">Данные скрыты правилами порога публикации.</p>
      )}
      {data.notice && <p className="text-[14px] text-[#4A5363] pt-1">{data.notice}</p>}
    </Card>
  );
}

const catalogRead = (_id: string, signal: AbortSignal) => feedbackApi.catalog(signal);

export const Surveys: React.FC = () => {
  const { data, error, retry } = useRead('', catalogRead);
  const [selectedOpenId, setSelectedOpenId] = useState(() => {
    const id = new URLSearchParams(window.location.search).get('cycle') ?? '';
    return cyclePattern.test(id) ? id : '';
  });
  const [selectedPublishedId, setSelectedPublishedId] = useState('');

  const cycles = data?.items ?? [];
  const openCycle =
    cycles.find((cycle) => cycle.id === selectedOpenId && cycle.status === 'open') ||
    cycles.find((cycle) => cycle.status === 'open') ||
    cycles[0];
  const publishedCycle =
    cycles.find((cycle) => cycle.id === selectedPublishedId && cycle.has_results) ||
    cycles.find((cycle) => cycle.has_results);

  function selectCycle(cycle: DemoCycle) {
    if (cycle.status === 'open') {
      setSelectedOpenId(cycle.id);
    }
    if (cycle.has_results) {
      setSelectedPublishedId(cycle.id);
    }
    const url = new URL(window.location.href);
    url.searchParams.set('workspace', 'surveys');
    url.searchParams.set('cycle', cycle.id);
    window.history.replaceState(window.history.state, '', url);
  }

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
      <div data-tour="employee-surveys-hero" className="bg-[#F1EDFF] rounded-3xl p-8 flex items-center gap-5">
        <div aria-hidden="true" className="w-[64px] h-[64px] shrink-0 bg-white rounded-2xl flex items-center justify-center text-[28px]">🛡</div>
        <div>
          <h1 className="text-[32px] font-bold">Опросы</h1>
          <p className="text-[18px] text-[#4A5363]">Все опросы анонимные: руководитель видит только общую сводку, а не ваши ответы.</p>
        </div>
      </div>

      <div data-tour="employee-surveys-workspace" className="grid lg:grid-cols-[2fr_1fr] gap-5 items-start">
        {openCycle ? (
          <ActiveSurveyCard key={openCycle.id} id={openCycle.id} />
        ) : (
          <Card className="space-y-3">
            {!data && !error && <p className="text-[16px] text-[#4A5363]">Загружаем опросы…</p>}
            {error && (
              <p role="alert" className="text-[#A3171B]">
                {error} <Btn variant="link" onClick={retry}>Повторить</Btn>
              </p>
            )}
            {data && !cycles.length && <p className="text-[16px] text-[#4A5363]">Открытых опросов пока нет.</p>}
          </Card>
        )}

        <Card className="space-y-3 min-h-[300px]">
          <h2 className="text-[22px] font-bold">Все опросы</h2>
          {!data && !error && <p className="text-[15px] text-[#4A5363]">Загружаем список…</p>}
          {error && (
            <p role="alert" className="text-[#A3171B] text-[15px]">
              {error} <Btn variant="link" onClick={retry}>Повторить</Btn>
            </p>
          )}
          {data && !cycles.length && <p className="text-[15px] text-[#4A5363]">Опросов пока нет.</p>}
          {cycles.map((cycle) => {
            const active = cycle.id === openCycle?.id || cycle.id === publishedCycle?.id;
            const tone = cycle.status === 'open' ? 'purple' : cycle.has_results ? 'green' : 'gray';
            const badgeText = cycle.status === 'open' ? 'Новый' : cycle.has_results ? 'Итоги' : 'Завершён';
            return (
              <button
                key={cycle.id}
                type="button"
                onClick={() => selectCycle(cycle)}
                className={`w-full flex items-center justify-between gap-3 text-left text-[16px] rounded-xl px-3 py-2 transition-colors ${
                  active ? 'bg-[#EEF3FE] text-[#141A24]' : 'hover:bg-[#F3F5F8]'
                }`}
              >
                <span>{cycle.title}</span>
                <Badge tone={tone}>{badgeText}</Badge>
              </button>
            );
          })}
        </Card>
      </div>

      <div className="grid lg:grid-cols-[2fr_1fr] gap-5 items-start">
        {publishedCycle ? (
          <PublishedResultsCard key={publishedCycle.id} cycle={publishedCycle} />
        ) : (
          <Card className="space-y-3">
            <h2 className="text-[22px] font-bold">Итоги опросов</h2>
            <p className="text-[15px] text-[#4A5363]">Опубликованные итоги появятся здесь после завершения опроса.</p>
          </Card>
        )}

        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Что изменили по итогам</h2>
          {fallbackChanges.map((t) => (
            <div key={t} className="flex items-center gap-3 text-[17px]">
              <span className="w-6 h-6 rounded bg-[#1F4FD1] text-white flex items-center justify-center text-[14px] shrink-0">✓</span>
              <span>{t}</span>
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
};

export default Surveys;
