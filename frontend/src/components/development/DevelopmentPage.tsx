import { useEffect, useState } from 'react';
import { Card, Btn, Badge, PageTitle } from '../shared/ui';
import {
  developmentRequest as api, type Session, type Goal, type Plan, type Submission,
  type Progress, type ResultPackage, type ReviewResult,
} from '../../api/development';

const input = 'w-full rounded-lg border border-[#C9D0DB] bg-white px-3 py-2 text-[14px] text-[#141A24]';
const statusNames: Record<string, string> = {
  private: 'Личная цель', shared: 'Передана руководителю', proposed: 'Предложен',
  returned: 'На доработке', active: 'Согласован', closed: 'Завершён', reached: 'Цель достигнута',
  partial: 'Частичный результат', stopped: 'Прекращён', unsubmitted: 'Работа не предъявлена',
  waiting: 'Ожидает проверки', confirmed: 'Подтверждено', needs_revision: 'Нужна доработка',
  not_verified: 'Проверить невозможно',
};
const message = (error: unknown) => error instanceof Error ? error.message : 'Не удалось выполнить действие.';
type Run = (action: () => Promise<unknown>) => Promise<void>;

function Login({ onLogin }: { onLogin: (session: Session) => void }) {
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return <Card className="max-w-[520px] space-y-4">
    <h2 className="text-[18px] font-bold">Вход в развитие сотрудника</h2>
    <p className="text-[14px] text-[#4A5363]">Используйте учётную запись Workforce. Цели и планы доступны назначенным участникам.</p>
    <form className="space-y-3" onSubmit={async (event) => {
      event.preventDefault(); setBusy(true); setError('');
      try { onLogin(await api<Session>(null, '/sessions', { login, password })); }
      catch (e) { setError(message(e)); } finally { setBusy(false); }
    }}>
      <label className="block">Логин<input className={input} autoComplete="username" value={login} onChange={(e) => setLogin(e.target.value)} required /></label>
      <label className="block">Пароль<input className={input} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
      <Btn type="submit" variant="primary" disabled={busy}>{busy ? 'Входим…' : 'Войти'}</Btn>
      {error && <p role="alert" className="text-[#A3171B]">{error}</p>}
    </form>
  </Card>;
}

function GoalPanel({ goal, session, run, busy, onChanged }: {
  goal: Goal; session: Session; run: Run; busy: boolean; onChanged: () => Promise<void>;
}) {
  const [recipient, setRecipient] = useState('');
  const [planTitle, setPlanTitle] = useState('');
  const [criterion, setCriterion] = useState('');
  const [activity, setActivity] = useState('');
  const [resource, setResource] = useState('');
  const [reviewer, setReviewer] = useState(session.actor.actor_id);
  const owner = goal.owner_actor_id === session.actor.actor_id;
  return <Card className="space-y-4">
    <div className="flex items-center justify-between gap-4"><h2 className="text-[20px] font-bold">{goal.title}</h2><Badge>{statusNames[goal.status]}</Badge></div>
    <p className="whitespace-pre-wrap text-[#4A5363]">{goal.description}</p>
    {owner ? <form className="space-y-3 border-t border-[#E1E5EB] pt-4" onSubmit={(e) => {
      e.preventDefault();
      void run(async () => { await api(session.access_token, '/development/goals/' + goal.id + '/share', { expected_revision: goal.revision, recipient_actor_id: recipient }); await onChanged(); });
    }}>
      <label className="block text-[14px]">Код учётной записи руководителя<input className={input} value={recipient} onChange={(e) => setRecipient(e.target.value)} required /></label>
      <p className="text-[13px] text-[#4A5363]">Указанный руководитель получит цель после отправки.</p>
      <Btn type="submit" disabled={busy || !recipient.trim()} variant="primary">Передать цель руководителю</Btn>
    </form> : <form className="space-y-3 border-t border-[#E1E5EB] pt-4" onSubmit={(e) => {
      e.preventDefault();
      void run(async () => {
        await api(session.access_token, '/development/plans', {
          goal_id: goal.id, goal_revision: goal.revision, reviewer_actor_id: reviewer,
          title: planTitle, criteria: [{ key: 'result', text: criterion, required: true }],
          activities: [{ key: 'work', title: activity, criterion_keys: ['result'], resource_note: resource }],
        }); await onChanged();
      });
    }}>
      <h3 className="font-semibold">Предложить план</h3>
      <label className="block text-[14px]">Название плана<input className={input} value={planTitle} onChange={(e) => setPlanTitle(e.target.value)} required /></label>
      <label className="block text-[14px]">Критерий результата<textarea className={input} rows={2} value={criterion} onChange={(e) => setCriterion(e.target.value)} required /></label>
      <label className="block text-[14px]">Действие сотрудника<input className={input} value={activity} onChange={(e) => setActivity(e.target.value)} required /></label>
      <label className="block text-[14px]">Время и поддержка<input className={input} value={resource} onChange={(e) => setResource(e.target.value)} required /></label>
      <label className="block text-[14px]">Код учётной записи проверяющего<input className={input} value={reviewer} onChange={(e) => setReviewer(e.target.value)} required /></label>
      <Btn type="submit" variant="primary" disabled={busy}>Предложить план сотруднику</Btn>
    </form>}
  </Card>;
}

function ReviewForm({ submission, plan, run, token, busy, refresh }: {
  submission: Submission; plan: Plan; run: Run; token: string; busy: boolean; refresh: () => Promise<void>;
}) {
  const [results, setResults] = useState<Record<string, { result: ReviewResult['result']; reason: string }>>(
    Object.fromEntries(submission.criterion_keys.map((key) => [key, { result: 'confirmed', reason: '' }]))
  );
  return <form className="space-y-3 border-t border-[#E1E5EB] pt-3" onSubmit={(event) => {
    event.preventDefault();
    void run(async () => {
      await api(token, '/development/submissions/' + submission.id + '/review', {
        results: submission.criterion_keys.map((key) => ({ criterion_key: key, ...results[key] })),
      }); await refresh();
    });
  }}>
    {submission.criterion_keys.map((key) => <div key={key} className="space-y-2">
      <p className="font-medium">{plan.criteria.find((row) => row.key === key)?.text ?? key}</p>
      <select aria-label="Результат проверки" className={input} value={results[key].result} onChange={(e) => setResults((old) => ({ ...old, [key]: { ...old[key], result: e.target.value as ReviewResult['result'] } }))}>
        <option value="confirmed">Подтверждено</option><option value="needs_revision">Нужна доработка</option><option value="not_verified">Проверить невозможно</option>
      </select>
      <label className="block text-[14px]">Основание заключения<textarea className={input} value={results[key].reason} rows={2} onChange={(e) => setResults((old) => ({ ...old, [key]: { ...old[key], reason: e.target.value } }))} required /></label>
    </div>)}
    <Btn type="submit" variant="primary" disabled={busy}>Сохранить заключение</Btn>
  </form>;
}

function PlanPanel({ plan, session, run, busy, refreshLists }: {
  plan: Plan; session: Session; run: Run; busy: boolean; refreshLists: () => Promise<void>;
}) {
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [error, setError] = useState('');
  const [respondNote, setRespondNote] = useState('');
  const [activityKey, setActivityKey] = useState(plan.activities[0]?.key ?? '');
  const [statement, setStatement] = useState('');
  const [artifact, setArtifact] = useState('');
  const [kind, setKind] = useState('text');
  const [closeReason, setCloseReason] = useState('');
  const [closeOutcome, setCloseOutcome] = useState('reached');
  const [purpose, setPurpose] = useState('');
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [resultPackage, setResultPackage] = useState<ResultPackage | null>(null);
  const [editTitle, setEditTitle] = useState(plan.title);
  const [editResource, setEditResource] = useState(plan.activities[0]?.resource_note ?? '');
  const owner = plan.owner_actor_id === session.actor.actor_id;
  const manager = plan.manager_actor_id === session.actor.actor_id;
  const reviewer = plan.reviewer_actor_id === session.actor.actor_id;
  const activity = plan.activities.find((row) => row.key === activityKey);
  async function refresh() {
    const [works, currentProgress] = await Promise.all([
      api<{items: Submission[]}>(session.access_token, '/development/plans/' + plan.id + '/submissions'),
      api<Progress>(session.access_token, '/development/plans/' + plan.id + '/progress'),
    ]);
    setSubmissions(works.items); setProgress(currentProgress); await refreshLists();
  }
  useEffect(() => {
    const controller = new AbortController(); setError('');
    Promise.all([
      api<{items: Submission[]}>(session.access_token, '/development/plans/' + plan.id + '/submissions', undefined, 'GET', controller.signal),
      api<Progress>(session.access_token, '/development/plans/' + plan.id + '/progress', undefined, 'GET', controller.signal),
    ]).then(([works, value]) => { setSubmissions(works.items); setProgress(value); })
      .catch((e) => { if (!controller.signal.aborted) setError(message(e)); });
    return () => controller.abort();
  }, [plan.id, plan.revision, session.access_token]);

  return <div className="space-y-5">
    <Card className="space-y-4">
      <div className="flex justify-between gap-4"><h2 className="text-[22px] font-bold">{plan.title}</h2><Badge>{statusNames[plan.status]}</Badge></div>
      <p className="text-[14px] text-[#4A5363]">Цель — {plan.goal_snapshot.title}</p>
      {plan.decision_note && <p className="bg-[#EEF3FE] rounded-lg p-3">{plan.decision_note}</p>}
      <div className="grid grid-cols-2 gap-5">
        <div><h3 className="font-semibold mb-2">Критерии результата</h3>{plan.criteria.map((criterion) => <div key={criterion.key} className="py-2 border-b border-[#E1E5EB]">
          <p>{criterion.text}</p><Badge>{statusNames[progress?.criteria.find((row) => row.key === criterion.key)?.state ?? 'unsubmitted']}</Badge>
        </div>)}</div>
        <div><h3 className="font-semibold mb-2">Договорённость о работе</h3>{plan.activities.map((row) => <div key={row.key} className="py-2 border-b border-[#E1E5EB]"><p className="font-medium">{row.title}</p><p className="text-[#4A5363]">{row.resource_note}</p></div>)}</div>
      </div>
      {error && <p role="alert" className="text-[#A3171B]">{error}</p>}
      {owner && plan.status === 'proposed' && <div className="space-y-3 border-t border-[#E1E5EB] pt-4">
        <label className="block">Ответ на предложение<textarea className={input} value={respondNote} onChange={(e) => setRespondNote(e.target.value)} rows={2} /></label>
        <div className="flex gap-3">
          {(['accept','return'] as const).map((decision) => <Btn key={decision} variant={decision === 'accept' ? 'primary' : 'secondary'} disabled={busy || !respondNote.trim()} onClick={() => void run(async () => { await api(session.access_token, '/development/plans/' + plan.id + '/respond', { expected_revision: plan.revision, decision, note: respondNote }); await refresh(); })}>
            {decision === 'accept' ? 'Принять план' : 'Вернуть на доработку'}
          </Btn>)}
        </div>
      </div>}
      {manager && ['returned','proposed'].includes(plan.status) && <form className="space-y-3 border-t border-[#E1E5EB] pt-4" onSubmit={(e) => {
        e.preventDefault(); void run(async () => {
          await api(session.access_token, '/development/plans/' + plan.id, {
            expected_revision: plan.revision, title: editTitle,
            activities: plan.activities.map((row, index) => index === 0 ? { ...row, resource_note: editResource } : row),
          }, 'PATCH'); await refresh();
        });
      }}>
        <h3 className="font-semibold">Уточнить предложение</h3>
        <label className="block">Название плана<input className={input} value={editTitle} onChange={(e) => setEditTitle(e.target.value)} required /></label>
        <label className="block">Время и поддержка первого действия<input className={input} value={editResource} onChange={(e) => setEditResource(e.target.value)} required /></label>
        <Btn type="submit" disabled={busy}>Сохранить уточнение</Btn>
      </form>}
      {plan.closure && <div className="bg-[#E3F2E7] rounded-xl p-4"><strong>{statusNames[plan.closure.outcome]}</strong><p>{plan.closure.reason}</p></div>}
    </Card>
    {owner && plan.status === 'active' && <Card>
      <form className="space-y-3" onSubmit={(event) => {
        event.preventDefault(); if (!activity) return;
        void run(async () => {
          await api(session.access_token, '/development/plans/' + plan.id + '/submissions', {
            activity_key: activity.key, criterion_keys: activity.criterion_keys, statement, artifact: { kind, value: artifact },
          }); setStatement(''); setArtifact(''); await refresh();
        });
      }}>
        <h3 className="text-[18px] font-bold">Предъявить работу</h3>
        <label className="block">Действие<select aria-label="Действие" className={input} value={activityKey} onChange={(e) => setActivityKey(e.target.value)}>{plan.activities.map((row) => <option key={row.key} value={row.key}>{row.title}</option>)}</select></label>
        <label className="block">Что сделано<textarea className={input} value={statement} onChange={(e) => setStatement(e.target.value)} rows={2} required /></label>
        <select aria-label="Вид свидетельства" className={input} value={kind} onChange={(e) => setKind(e.target.value)}><option value="text">Текст работы</option><option value="url">Ссылка на работу</option></select>
        <label className="block">Свидетельство<textarea className={input} value={artifact} onChange={(e) => setArtifact(e.target.value)} rows={4} required /></label>
        {kind === 'url' && <p className="text-[#4A5363] text-[13px]">Сохраняется ссылка. Доступ и изменение внешнего источника зависят от его владельца.</p>}
        <Btn type="submit" variant="primary" disabled={busy}>Отправить работу на проверку</Btn>
      </form>
    </Card>}
    <Card className="space-y-4">
      <h3 className="text-[18px] font-bold">Работы и заключения</h3>
      {submissions.length === 0 && <p className="text-[#4A5363]">Работ пока нет.</p>}
      {submissions.map((work) => <div key={work.id} className="border border-[#E1E5EB] rounded-xl p-4 space-y-3">
        <p className="font-semibold">{plan.activities.find((row) => row.key === work.activity_key)?.title} · попытка {work.attempt_no}</p>
        <p>{work.statement}</p>
        {work.artifact.kind === 'url'
          ? <a className="text-[#1F4FD1] underline break-all" href={work.artifact.value} target="_blank" rel="noreferrer">{work.artifact.value}</a>
          : <p className="bg-[#F6F7F9] rounded-lg p-3 whitespace-pre-wrap">{work.artifact.value}</p>}
        {work.review ? work.review.results.map((result) => <div key={result.criterion_key}><Badge tone={result.result === 'confirmed' ? 'green' : 'amber'}>{statusNames[result.result]}</Badge><p className="mt-1">{result.reason}</p></div>)
          : reviewer && plan.status === 'active' ? <ReviewForm submission={work} plan={plan} token={session.access_token} run={run} busy={busy} refresh={refresh} /> : <Badge>Ожидает проверки</Badge>}
      </div>)}
    </Card>
    {(owner || manager) && plan.status === 'active' && <Card>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void run(async () => {
        await api(session.access_token, '/development/plans/' + plan.id + '/close', { expected_revision: plan.revision, outcome: closeOutcome, reason: closeReason }); await refresh();
      }); }}>
        <h3 className="text-[18px] font-bold">Завершить план</h3>
        <select aria-label="Итог плана" className={input} value={closeOutcome} onChange={(e) => setCloseOutcome(e.target.value)}><option value="reached">Цель достигнута</option><option value="partial">Частичный результат</option><option value="stopped">Прекратить план</option></select>
        <label className="block">Основание итога<textarea className={input} value={closeReason} onChange={(e) => setCloseReason(e.target.value)} rows={2} required /></label>
        <Btn type="submit" disabled={busy}>Зафиксировать итог</Btn>
      </form>
    </Card>}
    {owner && plan.status === 'closed' && <Card>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void run(async () => {
        setResultPackage(await api<ResultPackage>(session.access_token, '/development/plans/' + plan.id + '/share-result', { criterion_keys: selectedKeys, purpose }));
      }); }}>
        <h3 className="text-[18px] font-bold">Выбранный результат для дальнейшего рассмотрения</h3>
        {plan.criteria.filter((row) => progress?.criteria.some((item) => item.key === row.key && item.state === 'confirmed')).map((row) => <label key={row.key} className="flex gap-2"><input type="checkbox" checked={selectedKeys.includes(row.key)} onChange={(e) => setSelectedKeys((old) => e.target.checked ? [...old, row.key] : old.filter((key) => key !== row.key))} />{row.text}</label>)}
        <label className="block">Цель передачи<input className={input} value={purpose} onChange={(e) => setPurpose(e.target.value)} required /></label>
        <Btn type="submit" variant="primary" disabled={busy || selectedKeys.length === 0}>Подготовить пакет</Btn>
      </form>
      {resultPackage && <div role="status" className="mt-4 rounded-xl bg-[#E3F2E7] p-4"><strong>Пакет подготовлен</strong><p>{resultPackage.purpose}</p>{resultPackage.items.map((item) => <p key={item.source_submission_id}>{item.criterion_text}</p>)}<p className="text-[13px] mt-2">Передача получателю ещё не выполнена.</p></div>}
    </Card>}
  </div>;
}

export default function DevelopmentPage() {
  const [session, setSession] = useState<Session | null>(null);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selected, setSelected] = useState<{ kind: 'goal' | 'plan'; id: string } | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function refresh() {
    if (!session) return;
    const [goalList, planList] = await Promise.all([
      api<{items: Goal[]}>(session.access_token, '/development/goals'),
      api<{items: Plan[]}>(session.access_token, '/development/plans'),
    ]);
    setGoals(goalList.items); setPlans(planList.items);
  }
  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    setGoals([]); setPlans([]); setSelected(null); setError('');
    Promise.all([
      api<{items: Goal[]}>(session.access_token, '/development/goals', undefined, 'GET', controller.signal),
      api<{items: Plan[]}>(session.access_token, '/development/plans', undefined, 'GET', controller.signal),
    ]).then(([goalList, planList]) => { setGoals(goalList.items); setPlans(planList.items); })
      .catch((e) => { if (!controller.signal.aborted) setError(message(e)); });
    return () => controller.abort();
  }, [session]);
  async function run(action: () => Promise<unknown>) {
    setBusy(true); setError('');
    try { await action(); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  const goal = selected?.kind === 'goal' ? goals.find((row) => row.id === selected.id) : undefined;
  const plan = selected?.kind === 'plan' ? plans.find((row) => row.id === selected.id) : undefined;
  const employee = session?.actor.grants.some((grant) => grant.role === 'employee');
  return <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
    <PageTitle title="Развитие сотрудника" subtitle="Цель, договорённость о работе и подтверждённый результат." />
    {!session ? <Login onLogin={setSession} /> : <>
      <div className="flex justify-between items-center gap-4 text-[14px]">
        <div><strong>{session.actor.login}</strong><span className="text-[#4A5363]"> · код для назначения {session.actor.actor_id}</span></div>
        <Btn disabled={busy} onClick={() => void run(async () => { await api(session.access_token, '/session', undefined, 'DELETE'); setSession(null); })}>Выйти</Btn>
      </div>
      {error && <div role="alert" className="bg-[#FCE8E8] rounded-xl p-4">{error} <Btn onClick={() => void run(refresh)} disabled={busy}>Обновить данные</Btn></div>}
      <div className="grid grid-cols-[300px_minmax(0,1fr)] items-start gap-5">
        <Card className="space-y-3">
          <h2 className="text-[17px] font-bold">Цели и планы</h2>
          {employee && <Btn onClick={() => setSelected(null)}>Новая цель</Btn>}
          {goals.length === 0 && plans.length === 0 && <p className="text-[#4A5363]">Доступных целей и планов пока нет.</p>}
          {plans.map((row) => <button key={row.id} className={`block w-full text-left p-3 rounded-lg border ${selected?.id === row.id ? 'border-[#1F4FD1] bg-[#EEF3FE]' : 'border-[#E1E5EB]'}`} onClick={() => setSelected({ kind: 'plan', id: row.id })}><strong>{row.title}</strong><span className="block text-[13px] text-[#4A5363]">{statusNames[row.status]}</span></button>)}
          {goals.map((row) => <button key={row.id} className={`block w-full text-left p-3 rounded-lg border ${selected?.id === row.id ? 'border-[#1F4FD1] bg-[#EEF3FE]' : 'border-[#E1E5EB]'}`} onClick={() => setSelected({ kind: 'goal', id: row.id })}><strong>{row.title}</strong><span className="block text-[13px] text-[#4A5363]">{statusNames[row.status]}</span></button>)}
        </Card>
        <div>
          {goal && <GoalPanel key={goal.id} goal={goal} session={session} run={run} busy={busy} onChanged={refresh} />}
          {plan && <PlanPanel key={plan.id} plan={plan} session={session} run={run} busy={busy} refreshLists={refresh} />}
          {!selected && employee && <Card><form className="space-y-3" onSubmit={(e) => {
            e.preventDefault(); void run(async () => {
              const created = await api<Goal>(session.access_token, '/development/goals', { title, description });
              await refresh(); setSelected({ kind: 'goal', id: created.id }); setTitle(''); setDescription('');
            });
          }}>
            <h2 className="text-[20px] font-bold">Личная цель</h2>
            <label className="block">Название цели<input className={input} value={title} onChange={(e) => setTitle(e.target.value)} required /></label>
            <label className="block">Рабочая задача и исходные основания<textarea className={input} value={description} onChange={(e) => setDescription(e.target.value)} rows={4} required /></label>
            <p className="text-[13px] text-[#4A5363]">Цель доступна вам до явной передачи руководителю.</p>
            <Btn type="submit" variant="primary" disabled={busy}>Сохранить личную цель</Btn>
          </form></Card>}
          {!selected && !employee && <Card>Выберите направленную вам цель или план.</Card>}
        </div>
      </div>
    </>}
  </div>;
}
