import { useEffect, useState } from 'react';
import { Badge, Btn, Card } from '../shared/ui';
import {
  fixtureMentorId, studentsRequest,
  type StudentRole, type Opportunity, type StudentApplication, type Placement,
  type Task, type Submission, type ReviewResult, type CareerPackage,
} from '../../api/students';

const field = 'w-full px-3 py-2 rounded-lg border border-[#C9D0DB] bg-white text-[14px] text-[#141A24]';
const statusLabels: Record<string, string> = {
  draft: 'Черновик', published: 'Приём заявок', closed: 'Приём закрыт',
  submitted: 'Заявка подана', withdrawn: 'Отозвана', assigned: 'Место назначено', not_assigned: 'Не назначено',
  active: 'Практика идёт', completed: 'Завершена', stopped: 'Прекращена', partial: 'Частичный результат',
  task_required: 'Ожидается задание наставника', awaiting_submission: 'Ожидается работа студента',
  awaiting_review: 'Ожидается проверка наставника', needs_revision: 'Нужна доработка',
  not_verified: 'Результат не подтверждён', confirmed: 'Результат подтверждён',
  passed: 'Зачёт получен', not_passed: 'Зачёт не получен', unknown: 'Результат вуза ещё не получен',
};
const label = (value: string) => statusLabels[value] || 'Статус уточняется';
const date = (value: string) => new Date(value).toLocaleDateString('ru-RU');
const message = (error: unknown) => error instanceof Error ? error.message : 'Не удалось выполнить действие.';
type Perform = (path: string, body: unknown) => Promise<unknown>;

function CreateOpportunity({ perform, busy }: { perform: Perform; busy: boolean }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [starts, setStarts] = useState('');
  const [ends, setEnds] = useState('');
  return <Card>
    <h2 className="text-[18px] font-bold mb-4">Новое место практики</h2>
    <form className="grid grid-cols-2 gap-4" onSubmit={(event) => {
      event.preventDefault();
      void perform('/opportunities', { title, description, starts_on: starts, ends_on: ends, capacity: 1, mentor_actor_id: fixtureMentorId });
    }}>
      <label className="block text-[14px]">Название практики<input required className={field} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
      <div className="text-[14px] text-[#4A5363]">Одно учебное место<br />Назначенный наставник — department</div>
      <label className="block text-[14px] col-span-2">Задача подразделения<textarea required className={field} value={description} onChange={(e) => setDescription(e.target.value)} rows={2} /></label>
      <label className="block text-[14px]">Начало практики<input required type="date" className={field} value={starts} onChange={(e) => setStarts(e.target.value)} /></label>
      <label className="block text-[14px]">Окончание практики<input required type="date" min={starts} className={field} value={ends} onChange={(e) => setEnds(e.target.value)} /></label>
      <div className="col-span-2"><Btn type="submit" variant="primary" disabled={busy || !title.trim() || !description.trim()}>Создать черновик</Btn></div>
    </form>
  </Card>;
}

function ApplyForm({ opportunity, perform, busy }: { opportunity: Opportunity; perform: Perform; busy: boolean }) {
  const [university, setUniversity] = useState('');
  const [programme, setProgramme] = useState('');
  const [comment, setComment] = useState('');
  return <form className="mt-4 space-y-3" onSubmit={(event) => {
    event.preventDefault();
    void perform('/applications', { opportunity_id: opportunity.id, university_label: university, programme_label: programme, comment });
  }}>
    <label className="block text-[14px]">Вуз<input required className={field} value={university} onChange={(e) => setUniversity(e.target.value)} /></label>
    <label className="block text-[14px]">Учебная программа<input required className={field} value={programme} onChange={(e) => setProgramme(e.target.value)} /></label>
    <label className="block text-[14px]">Комментарий к заявке<textarea className={field} value={comment} onChange={(e) => setComment(e.target.value)} rows={2} /></label>
    <Btn type="submit" variant="primary" disabled={busy || !university.trim() || !programme.trim()}>Подать заявку на практику</Btn>
  </form>;
}

function ApplicationAction({ item, role, perform, busy }: { item: StudentApplication; role: StudentRole; perform: Perform; busy: boolean }) {
  const [reason, setReason] = useState('');
  return <div className="mt-3 space-y-2">
    <label className="block text-[14px]">{role === 'hr' ? 'Основание назначения или причина отказа' : 'Причина отзыва заявки'}
      <input className={field} value={reason} onChange={(e) => setReason(e.target.value)} />
    </label>
    <div className="flex gap-3">
      {role === 'hr' && <Btn variant="primary" disabled={busy || !reason.trim()} onClick={() => void perform('/applications/' + item.id + '/assign', { expected_revision: item.revision, confirmation_basis: reason })}>Назначить место</Btn>}
      <Btn disabled={busy || !reason.trim()} onClick={() => void perform('/applications/' + item.id + (role === 'hr' ? '/decline' : '/withdraw'), { expected_revision: item.revision, reason })}>{role === 'hr' ? 'Отказать с причиной' : 'Отозвать заявку'}</Btn>
    </div>
  </div>;
}

function TaskForm({ path, perform, busy }: { path: string; perform: Perform; busy: boolean }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [criterion, setCriterion] = useState('');
  return <form className="space-y-3" onSubmit={(event) => {
    event.preventDefault();
    void perform(path + '/tasks', { title, description, criteria: [{ key: 'result', text: criterion, required: true }] });
  }}>
    <label className="block text-[14px]">Название задания<input className={field} value={title} onChange={(e) => setTitle(e.target.value)} required /></label>
    <label className="block text-[14px]">Что нужно сделать<textarea className={field} rows={3} value={description} onChange={(e) => setDescription(e.target.value)} required /></label>
    <label className="block text-[14px]">Обязательный критерий результата<textarea className={field} rows={2} value={criterion} onChange={(e) => setCriterion(e.target.value)} required /></label>
    <Btn type="submit" variant="primary" disabled={busy || !title.trim() || !description.trim() || !criterion.trim()}>Опубликовать задание</Btn>
  </form>;
}

function SubmissionForm({ task, path, perform, busy }: { task: Task; path: string; perform: Perform; busy: boolean }) {
  const [text, setText] = useState('');
  const [url, setUrl] = useState('');
  return <form className="space-y-3 mt-4" onSubmit={async (event) => {
    event.preventDefault();
    const result = await perform(path + '/submissions', { task_version_id: task.id, text, ...(url.trim() ? { artifact_url: url.trim() } : {}) });
    if (result) { setText(''); setUrl(''); }
  }}>
    <label className="block text-[14px]">Моя работа<textarea className={field} rows={4} value={text} onChange={(e) => setText(e.target.value)} required /></label>
    <label className="block text-[14px]">Ссылка на материал · необязательно<input className={field} type="url" value={url} onChange={(e) => setUrl(e.target.value)} /></label>
    <Btn type="submit" variant="primary" disabled={busy || !text.trim()}>Отправить работу наставнику</Btn>
  </form>;
}

function ReviewForm({ task, submission, perform, busy }: { task: Task; submission: Submission; perform: Perform; busy: boolean }) {
  const [results, setResults] = useState<ReviewResult[]>(task.criteria.map((criterion) => ({ criterion_key: criterion.key, result: 'not_verified', reason: '' })));
  return <form className="space-y-3 mt-3" onSubmit={(event) => {
    event.preventDefault(); void perform('/submissions/' + submission.id + '/review', { results });
  }}>
    {task.criteria.map((criterion, index) => <div key={criterion.key} className="space-y-2">
      <p className="font-medium text-[14px]">{criterion.text}</p>
      <select aria-label={'Результат проверки ' + criterion.key} className={field} value={results[index].result} onChange={(e) => setResults((items) => items.map((item, i) => i === index ? { ...item, result: e.target.value as ReviewResult['result'] } : item))}>
        <option value="not_verified">Не подтверждено</option><option value="needs_revision">Нужна доработка</option><option value="confirmed">Подтверждено</option>
      </select>
      <label className="block text-[14px]">Основание проверки<textarea className={field} rows={2} value={results[index].reason} onChange={(e) => setResults((items) => items.map((item, i) => i === index ? { ...item, reason: e.target.value } : item))} required /></label>
    </div>)}
    <Btn type="submit" variant="primary" disabled={busy || results.some((item) => !item.reason.trim())}>Сохранить проверку</Btn>
  </form>;
}

function PlacementResult({ placement, role, perform, busy }: { placement: Placement; role: StudentRole; perform: Perform; busy: boolean }) {
  const [outcome, setOutcome] = useState('completed');
  const [reason, setReason] = useState('');
  const [university, setUniversity] = useState('passed');
  const [source, setSource] = useState('');
  const [author, setAuthor] = useState('');
  const [occurred, setOccurred] = useState('');
  const [interestNote, setInterestNote] = useState('');
  const path = '/placements/' + placement.id;
  return <Card className="space-y-4">
    <h2 className="text-[18px] font-bold">Результат практики</h2>
    <div><h3 className="font-semibold">Принимающая сторона</h3><p>{placement.completion ? label(placement.completion.outcome) : 'Итог ещё не зафиксирован'}</p>{placement.completion && <p className="text-[14px] text-[#4A5363]">{placement.completion.reason}</p>}</div>
    {placement.status === 'active' && role !== 'candidate' && <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); void perform(path + '/complete', { expected_revision: placement.revision, outcome, reason }); }}>
      <select aria-label="Итог принимающей стороны" className={field} value={outcome} onChange={(e) => setOutcome(e.target.value)}><option value="completed">Завершена полностью</option><option value="partial">Частичный результат</option><option value="stopped">Прекращена</option></select>
      <label className="block text-[14px]">Основание итога<textarea className={field} value={reason} onChange={(e) => setReason(e.target.value)} rows={2} required /></label>
      <Btn type="submit" disabled={busy || !reason.trim()}>Зафиксировать итог практики</Btn>
    </form>}
    <div className="pt-4 border-t border-[#E1E5EB]"><h3 className="font-semibold">Результат вуза</h3><p>{label(placement.university_result?.result || 'unknown')}</p>{placement.university_result?.source_reference && <p className="text-[14px] text-[#4A5363]">{placement.university_result.source_reference} · {placement.university_result.source_author}</p>}</div>
    {role === 'hr' && <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); void perform(path + '/university-result', { expected_revision: placement.revision, result: university, source_reference: source, source_author: author, occurred_on: occurred }); }}>
      <select aria-label="Результат вуза" className={field} value={university} onChange={(e) => setUniversity(e.target.value)}><option value="passed">Зачёт получен</option><option value="not_passed">Зачёт не получен</option><option value="unknown">Результат неизвестен</option></select>
      <label className="block text-[14px]">Источник результата<input className={field} value={source} onChange={(e) => setSource(e.target.value)} required /></label>
      <label className="block text-[14px]">Автор внешнего результата<input className={field} value={author} onChange={(e) => setAuthor(e.target.value)} required /></label>
      <label className="block text-[14px]">Дата результата<input type="date" className={field} value={occurred} onChange={(e) => setOccurred(e.target.value)} required /></label>
      <Btn type="submit" disabled={busy || !source.trim() || !author.trim() || !occurred}>Записать результат вуза</Btn>
    </form>}
    <div className="pt-4 border-t border-[#E1E5EB]"><h3 className="font-semibold">Дальнейшее рассмотрение</h3><p>{placement.career_interest?.interested ? 'Студент выразил интерес' : 'Действующий интерес не заявлен'}</p></div>
    {role === 'candidate' && <div className="space-y-3">
      <label className="block text-[14px]">Пожелание о дальнейшей работе<textarea className={field} value={interestNote} onChange={(e) => setInterestNote(e.target.value)} rows={2} /></label>
      <Btn disabled={busy} onClick={() => void perform(path + '/career-interest', { expected_revision: placement.revision, interested: !placement.career_interest?.interested, note: interestNote })}>{placement.career_interest?.interested ? 'Отозвать интерес' : 'Выразить интерес к работе'}</Btn>
    </div>}
  </Card>;
}

function PracticeDetail({ id, role, token, onBack }: { id: string; role: StudentRole; token: string; onBack: () => void }) {
  const [placement, setPlacement] = useState<Placement | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [purpose, setPurpose] = useState('');
  const [contact, setContact] = useState('');
  const [careerPackage, setCareerPackage] = useState<CareerPackage | null>(null);
  const [keys, setKeys] = useState<string[]>([]);
  const path = '/placements/' + id;
  useEffect(() => {
    const controller = new AbortController(); setError('');
    Promise.all([
      studentsRequest<Placement>(token, path, undefined, controller.signal),
      studentsRequest<{ current: Task | null; items: Task[] }>(token, path + '/tasks', undefined, controller.signal),
      studentsRequest<{ items: Submission[] }>(token, path + '/submissions', undefined, controller.signal),
    ]).then(([participation, assignment, work]) => {
      setPlacement(participation); setTask(assignment.current); setTasks(assignment.items); setSubmissions(work.items);
    }).catch((e) => { if (!controller.signal.aborted) setError(message(e)); });
    return () => controller.abort();
  }, [id, token, revision, path]);
  const perform: Perform = async (url, body) => {
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await studentsRequest<unknown>(token, url, body);
      setNotice('Изменение сохранено.'); setRevision((value) => value + 1); return result;
    } catch (e) { setError(message(e)); return null; }
    finally { setBusy(false); }
  };
  const latest = submissions[submissions.length - 1];
  const confirmed = latest?.review?.results.filter((result) => result.result === 'confirmed') || [];
  return <div className="space-y-5">
    <Btn variant="link" onClick={onBack}>← К практике</Btn>
    {error && <div role="alert" className="p-4 rounded-xl bg-[#FCE8E8] text-[#A3171B]">{error} <Btn onClick={() => setRevision((v) => v + 1)}>Обновить данные</Btn></div>}
    {notice && <div role="status" className="p-4 rounded-xl bg-[#E3F2E7] text-[#1D7A40]">{notice}</div>}
    {!placement ? <Card>Загружаем участие…</Card> : <>
      <Card><h1 className="text-[24px] font-bold">Моя практика</h1><p className="mt-1 text-[#4A5363]">{date(placement.starts_on)} — {date(placement.ends_on)}</p><div className="mt-3 flex gap-2"><Badge>{label(placement.status)}</Badge><Badge tone="blue">{label(placement.work_state || 'task_required')}</Badge></div></Card>
      <div className="grid grid-cols-[minmax(0,2fr)_minmax(320px,1fr)] items-start gap-5">
        <div className="space-y-5">
          <Card>
            <h2 className="text-[18px] font-bold mb-3">Задание</h2>
            {task ? <><h3 className="font-semibold">{task.title} · версия {task.version}</h3><p className="my-3 whitespace-pre-wrap text-[#4A5363]">{task.description}</p><ul className="list-disc pl-5">{task.criteria.map((criterion) => <li key={criterion.key}>{criterion.text}{criterion.required && ' · обязательно'}</li>)}</ul></> : role === 'department' && placement.status === 'active' ? <TaskForm path={path} perform={perform} busy={busy} /> : <p>Наставник ещё не опубликовал задание.</p>}
            {task && role === 'candidate' && placement.status === 'active' && (!latest || latest.review) && <SubmissionForm task={task} path={path} perform={perform} busy={busy} />}
          </Card>
          <Card className="space-y-4">
            <h2 className="text-[18px] font-bold">Работы и обратная связь</h2>
            {submissions.length === 0 && <p className="text-[#4A5363]">Работа ещё не отправлена.</p>}
            {submissions.map((submission) => {
              const version = tasks.find((item) => item.id === submission.task_version_id);
              return <div key={submission.id} className="border-t border-[#E1E5EB] pt-4 space-y-2">
                <h3 className="font-semibold">Попытка {submission.attempt_no} · {date(submission.submitted_at)}</h3>
                <p className="whitespace-pre-wrap text-[14px]">{submission.text}</p>
                {submission.artifact_url && <a className="text-[#1F4FD1] underline" href={submission.artifact_url} target="_blank" rel="noreferrer">Открыть внешний материал</a>}
                {submission.review ? submission.review.results.map((result) => <div key={result.criterion_key} className="p-3 bg-[#F3F5F8] rounded-lg text-[14px]"><strong>{label(result.result)}</strong><p>{result.reason}</p></div>) : role === 'department' && version && placement.status === 'active' ? <ReviewForm task={version} submission={submission} perform={perform} busy={busy} /> : <p className="text-[#4A5363]">Ожидается проверка наставника.</p>}
              </div>;
            })}
          </Card>
          {role === 'hr' && placement.career_interest?.interested && <Card className="space-y-3">
            <h2 className="text-[18px] font-bold">Пакет для дальнейшего рассмотрения</h2>
            {confirmed.length === 0 ? <p>Подтверждённых результатов последней попытки пока нет.</p> : <form className="space-y-3" onSubmit={async (event) => {
              event.preventDefault();
              const result = await perform(path + '/career-package', { criterion_keys: keys, purpose, contact_basis: contact });
              if (result) setCareerPackage(result as CareerPackage);
            }}>
              {confirmed.map((result) => <label key={result.criterion_key} className="flex items-center gap-2"><input type="checkbox" checked={keys.includes(result.criterion_key)} onChange={(e) => setKeys((values) => e.target.checked ? [...values, result.criterion_key] : values.filter((value) => value !== result.criterion_key))} />{task?.criteria.find((criterion) => criterion.key === result.criterion_key)?.text || result.criterion_key}</label>)}
              <label className="block text-[14px]">Цель передачи<input className={field} required value={purpose} onChange={(e) => setPurpose(e.target.value)} /></label>
              <label className="block text-[14px]">Основание дальнейшего контакта<input className={field} required value={contact} onChange={(e) => setContact(e.target.value)} /></label>
              <Btn type="submit" disabled={busy || !keys.length || !purpose.trim() || !contact.trim()}>Подготовить пакет</Btn>
            </form>}
            {careerPackage && <div role="status" className="rounded-xl p-3 bg-[#E3F2E7]">Пакет подготовлен. Передача в архив ожидает подтверждения. Диплом не подтверждён.</div>}
          </Card>}
        </div>
        <PlacementResult placement={placement} role={role} perform={perform} busy={busy} />
      </div>
    </>}
  </div>;
}

export default function StudentsWorkspace({ token, role = 'candidate' }: { token: string; role?: StudentRole }) {
  return <PracticeWorkspace key={token + ':' + role} token={token} role={role} />;
}

function StudentsHero() {
  return <section className="bg-[#FF6A3D] rounded-2xl p-8 lg:p-12 text-white shadow-sm">
    <span className="inline-block bg-white/95 text-[#C2410C] text-[12px] font-bold px-3 py-1 rounded-full mb-4 shadow-sm">
      Для студентов и выпускников
    </span>
    <h1 className="text-[32px] sm:text-[38px] font-bold tracking-tight mb-3">
      Практика в администрации — не для галочки
    </h1>
    <p className="text-[15px] sm:text-[16px] text-white/95 leading-relaxed max-w-2xl">
      Реальные задачи города, наставник из департамента и шанс попасть в студенческий резерв.
    </p>
  </section>;
}

function PracticeWorkspace({ token, role }: { token: string; role: StudentRole }) {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [applications, setApplications] = useState<StudentApplication[]>([]);
  const [placements, setPlacements] = useState<Placement[]>([]);
  const [selected, setSelected] = useState('');
  const [applying, setApplying] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState('');
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    Promise.all([
      role === 'department' ? Promise.resolve({ items: [] as Opportunity[] }) : studentsRequest<{ items: Opportunity[] }>(token, '/opportunities', undefined, controller.signal),
      role === 'department' ? Promise.resolve({ items: [] as StudentApplication[] }) : studentsRequest<{ items: StudentApplication[] }>(token, '/applications', undefined, controller.signal),
      studentsRequest<{ items: Placement[] }>(token, '/placements', undefined, controller.signal),
    ]).then(([places, requests, assigned]) => { setOpportunities(places.items); setApplications(requests.items); setPlacements(assigned.items); })
      .catch((e) => { if (!controller.signal.aborted) setError(message(e)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [role, token, refresh]);
  const perform: Perform = async (path, body) => {
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await studentsRequest<unknown>(token, path, body);
      setNotice('Изменение сохранено.'); setApplying(''); setCreateOpen(false); setRefresh((value) => value + 1); return result;
    } catch (e) { setError(message(e)); return null; }
    finally { setBusy(false); }
  };
  return <div className={role === 'candidate' ? 'space-y-10' : 'max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5'}>
    {role === 'candidate' ? <StudentsHero /> : <div className="flex items-center justify-between gap-5">
      <div><h1 className="text-[26px] font-bold">Практика студентов</h1><p className="text-[14px] text-[#616977]">Место, задание и подтверждённый результат.</p></div>
    </div>}
    {selected ? <PracticeDetail key={role + selected} id={selected} role={role} token={token} onBack={() => { setSelected(''); setRefresh((value) => value + 1); }} /> : <>
      {error && <div role="alert" className="bg-[#FCE8E8] p-4 rounded-xl text-[#A3171B]">{error} <Btn onClick={() => setRefresh((value) => value + 1)}>Повторить</Btn></div>}
      {notice && <div role="status" className="bg-[#E3F2E7] p-4 rounded-xl text-[#1D7A40]">{notice}</div>}
      {loading ? <Card>Загружаем практику…</Card> : <>
        {role === 'hr' && <Btn variant="primary" onClick={() => setCreateOpen((value) => !value)}>{createOpen ? 'Закрыть форму' : 'Создать место практики'}</Btn>}
        {createOpen && role === 'hr' && <CreateOpportunity perform={perform} busy={busy} />}
        {role !== 'department' && <section>
          <h2 className="text-[20px] font-bold text-[#141A24] mb-4">{role === 'candidate' ? 'Практика и стажировки' : 'Места практики'}</h2>
          {opportunities.length === 0 && <Card>Доступных мест пока нет.</Card>}
          <div className={role === 'candidate' ? 'grid grid-cols-1 md:grid-cols-3 gap-5' : 'space-y-3'}>
          {opportunities.map((opportunity) => {
            const applied = applications.some((item) => item.opportunity_id === opportunity.id && ['submitted', 'assigned'].includes(item.status));
            if (role === 'candidate') {
              return <article key={opportunity.id} className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm flex flex-col justify-between hover:shadow-md transition-shadow min-w-0">
                <div>
                  <span className="inline-block bg-[#FEF7E0] text-[#B06000] text-[12px] font-medium px-2.5 py-1 rounded-md mb-3">Практика</span>
                  <h3 className="text-[17px] font-bold text-[#141A24] mb-1.5 break-words">{opportunity.title}</h3>
                  <p className="text-[13px] text-[#616977] mb-3">{date(opportunity.starts_on)} — {date(opportunity.ends_on)} · свободных мест {opportunity.available_places ?? 0}</p>
                  <p className="text-[13px] text-[#4A5363] leading-relaxed mb-6 break-words">{opportunity.description}</p>
                </div>
                <div>
                  <button type="button" disabled={busy || applied} onClick={() => setApplying(opportunity.id)} className="px-6 py-2.5 bg-[#1F4FD1] hover:bg-[#1841B2] text-white text-[14px] font-medium rounded-lg transition-colors shadow-sm disabled:opacity-60">
                    {applied ? 'Заявка уже подана' : 'Откликнуться'}
                  </button>
                  {applying === opportunity.id && <ApplyForm opportunity={opportunity} perform={perform} busy={busy} />}
                </div>
              </article>;
            }
            return <Card key={opportunity.id}>
              <div className="flex items-start justify-between gap-4"><div><h3 className="text-[18px] font-bold">{opportunity.title}</h3><p className="text-[14px] text-[#4A5363] mt-1">{opportunity.description}</p></div><Badge>{label(opportunity.status)}</Badge></div>
              <p className="my-3 text-[14px]">{date(opportunity.starts_on)} — {date(opportunity.ends_on)} · свободных мест {opportunity.available_places ?? 0}</p>
              {role === 'hr' && opportunity.status === 'draft' && <Btn disabled={busy} onClick={() => void perform('/opportunities/' + opportunity.id + '/publish', { expected_revision: opportunity.revision })}>Опубликовать место</Btn>}
            </Card>;
          })}
          </div>
        </section>}
        {role !== 'department' && <Card className="space-y-4"><h2 className="text-[20px] font-bold">{role === 'hr' ? 'Заявки на практику' : 'Мои заявки'}</h2>
          {!applications.length && <p className="text-[#4A5363]">Заявок на практику пока нет.</p>}
          {applications.map((item) => <div key={item.id} className="border-t border-[#E1E5EB] pt-3">
            <div className="flex justify-between gap-3"><strong>{opportunities.find((place) => place.id === item.opportunity_id)?.title || 'Заявка на практику'}</strong><Badge>{label(item.status)}</Badge></div>
            <p className="text-[14px] text-[#4A5363]">{item.university_label} · {item.programme_label}</p>
            {item.comment && <p className="text-[14px]">{item.comment}</p>}{item.reason && <p className="text-[14px]">{item.reason}</p>}
            {item.status === 'submitted' && <ApplicationAction item={item} role={role} perform={perform} busy={busy} />}
          </div>)}
        </Card>}
        <Card className="space-y-3"><h2 className="text-[20px] font-bold">{role === 'hr' ? 'Назначенные участия' : 'Моя практика'}</h2>
          {placements.length === 0 && <p className="text-[#4A5363]">Назначенных участий пока нет.</p>}
          {placements.map((item) => <button key={item.id} onClick={() => setSelected(item.id)} className="w-full flex items-center justify-between gap-3 border-t border-[#E1E5EB] py-3 text-left">
            <div><span className="font-semibold text-[#1F4FD1]">{opportunities.find((place) => place.id === item.opportunity_id)?.title || 'Практика'} · {date(item.starts_on)} — {date(item.ends_on)}</span><p className="text-[13px] text-[#4A5363]">Открыть задание и результат</p></div><Badge>{label(item.status)}</Badge>
          </button>)}
        </Card>
      </>}
    </>}
  </div>;
}
