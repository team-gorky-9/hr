import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Badge, Btn, Card, PageTitle } from '../shared/ui';
import {
  downloadSupportDocument, supportFixtureActors, supportRequest, supportRoles,
  type SupportCase, type SupportDocument, type SupportEvent, type SupportRole, type SupportRule,
} from '../../api/support';

const field = 'mt-1 block w-full rounded-lg border border-[#C9D0DB] bg-white px-3 py-2 text-[14px] text-[#141A24]';
const statuses: Record<string, string> = {
  draft: 'Черновик', submitted: 'На проверке', needs_information: 'Нужно дополнить',
  ready_for_review: 'Готово к рассмотрению', decision_recorded: 'Решение записано',
  closed: 'Закрыто', withdrawn: 'Отозвано',
};
const outcomeNames: Record<string, string> = { approved: 'Помощь одобрена', declined: 'В помощи отказано', needs_information: 'Требуется дополнение' };
const executionNames: Record<string, string> = { unknown: 'Исполнение не подтверждено', failed: 'Ошибка исполнения', confirmed: 'Исполнение подтверждено' };
const date = (value?: string | null) => value ? new Date(value).toLocaleDateString('ru-RU') : '—';
const message = (error: unknown) => error instanceof Error ? error.message : 'Не удалось выполнить действие.';

function TextField({ label, value, onChange, multiline = false, required = true }: {
  label: string; value: string; onChange: (value: string) => void; multiline?: boolean; required?: boolean;
}) {
  return <label className="block text-[14px] font-medium">{label}{multiline
    ? <textarea className={field} rows={3} required={required} value={value} onChange={(e) => onChange(e.target.value)} />
    : <input className={field} required={required} value={value} onChange={(e) => onChange(e.target.value)} />}</label>;
}
function ActionForm({ title, action, busy, submit, children }: {
  title: string; action: string; busy: boolean; submit: () => void; children: ReactNode;
}) {
  return <form className="space-y-3" onSubmit={(e: FormEvent) => { e.preventDefault(); submit(); }}>
    <h3 className="text-[17px] font-bold">{title}</h3>{children}
    <Btn type="submit" variant="primary" disabled={busy}>{busy ? 'Сохраняем…' : action}</Btn>
  </form>;
}

type Command = (path: string, values: Record<string, unknown>, method?: string) => Promise<void>;

function Checklist({ item, rule, busy, command }: { item: SupportCase; rule: SupportRule; busy: boolean; command: Command }) {
  const submitted = new Set(item.submissions?.slice(-1)[0]?.document_ids ?? []);
  const documents = (item.documents ?? []).filter((doc) => submitted.has(doc.id));
  const [results, setResults] = useState<Record<string, string>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [publicMessage, setPublicMessage] = useState('');
  return <ActionForm title="Проверка комплекта" action="Сохранить проверку" busy={busy} submit={() => void command('completeness', {
    public_message: publicMessage,
    items: rule.required_items.map((required) => {
      const doc = documents.find((entry) => entry.item_key === required.key);
      const result = results[required.key] || (doc ? 'present' : 'missing');
      return { key: required.key, result, document_id: result === 'missing' ? null : doc?.id, reason: reasons[required.key] || '' };
    }),
  })}>
    {rule.required_items.map((required) => {
      const doc = documents.find((entry) => entry.item_key === required.key);
      const value = results[required.key] || (doc ? 'present' : 'missing');
      return <div className="space-y-2 border-b border-[#E1E5EB] pb-3" key={required.key}>
        <label className="block text-[14px] font-medium" htmlFor={'support-check-' + required.key}>{required.title}</label>
        <p className="text-[13px] text-[#4A5363]">{doc?.original_name || 'Файл в текущей подаче отсутствует'}</p>
        <select id={'support-check-' + required.key} className={field} value={value} onChange={(e) => setResults({ ...results, [required.key]: e.target.value })}>
          {doc ? <><option value="present">Принят</option><option value="unreadable">Нечитаемый</option><option value="needs_clarification">Нужно уточнение</option></> : <option value="missing">Отсутствует</option>}
        </select>
        {value !== 'present' && <TextField label={'Замечание — ' + required.title} value={reasons[required.key] || ''} onChange={(value) => setReasons({ ...reasons, [required.key]: value })} />}
      </div>;
    })}
    <TextField label="Сообщение сотруднику" multiline value={publicMessage} onChange={setPublicMessage} />
  </ActionForm>;
}

function CaseActions({ role, item, rule, busy, command, upload, onError }: {
  role: SupportRole; item: SupportCase; rule?: SupportRule; busy: boolean;
  command: Command; upload: (key: string, file: File) => Promise<void>; onError: (text: string) => void;
}) {
  const [statement, setStatement] = useState(item.statement || '');
  const [text, setText] = useState('');
  const [source, setSource] = useState('');
  const [sourceAuthor, setSourceAuthor] = useState('');
  const [basis, setBasis] = useState('');
  const [outcome, setOutcome] = useState('approved');
  const [decidedOn, setDecidedOn] = useState('');
  const [execution, setExecution] = useState('unknown');
  const editable = role === 'employee' && ['draft', 'needs_information'].includes(item.status);
  return <div className="space-y-5">
    {role === 'employee' && item.status === 'draft' && <ActionForm title="Текст заявления" action="Сохранить текст" busy={busy} submit={() => void command('', { statement }, 'PATCH')}>
      <TextField label="Заявление" multiline value={statement} onChange={setStatement} />
    </ActionForm>}
    {editable && rule && <div className="space-y-3">
      <h3 className="text-[17px] font-bold">Приложения к заявлению</h3>
      {rule.required_items.map((required) => <label key={required.key} className="block text-[14px] font-medium">
        {required.title}<input className={field} type="file" disabled={busy} onChange={(e) => {
          const file = e.target.files?.[0]; if (file) void upload(required.key, file);
          e.target.value = '';
        }} />
      </label>)}
      <p className="text-[13px] text-[#4A5363]">До 10 МБ на файл. Загруженные приложения войдут в отправленную версию.</p>
      {item.status === 'draft' && <Btn variant="primary" disabled={busy} onClick={() => void command('submit', {})}>Подать заявление</Btn>}
      {item.status === 'needs_information' && <ActionForm title="Ответ на запрос" action="Отправить дополнение" busy={busy} submit={() => {
        const latest = new Map((item.documents ?? []).filter((doc) => doc.visibility === 'applicant').map((doc) => [doc.item_key, doc.id]));
        void command('addenda', { text, document_ids: [...latest.values()] });
      }}>
        <TextField label="Пояснение к дополнению" multiline value={text} onChange={setText} />
      </ActionForm>}
    </div>}
    {role === 'coordinator' && <ActionForm title="Назначить ответственных" action="Назначить проверяющего и секретаря" busy={busy} submit={() => void command('assign', {
      specialist_actor_id: supportFixtureActors.specialist, secretary_actor_id: supportFixtureActors.secretary, assignment_basis: basis,
    })}>
      <p className="text-[14px]">Учебные участники — проверяющий specialist и секретарь secretary.</p>
      <TextField label="Основание назначения" value={basis} onChange={setBasis} />
    </ActionForm>}
    {role === 'specialist' && ['submitted', 'needs_information', 'ready_for_review'].includes(item.status) && <>
      <ActionForm title="Проверка статуса сотрудника" action="Подтвердить по источнику" busy={busy} submit={() => void command('staff-confirmation', { state: 'confirmed', source_reference: source })}>
        <p className="text-[14px]">Текущий статус — {item.staff_status === 'confirmed' ? 'подтверждён' : 'не подтверждён'}.</p>
        <TextField label="Источник кадрового подтверждения" value={source} onChange={setSource} />
      </ActionForm>
      {rule && <Checklist key={item.submissions?.slice(-1)[0]?.submission_revision} item={item} rule={rule} busy={busy} command={command} />}
    </>}
    {role === 'secretary' && item.status === 'ready_for_review' && <ActionForm title="Записать внешнее решение" action="Сохранить решение" busy={busy} submit={() => void command('decision', {
      outcome, public_explanation: text, source_reference: source, source_author: sourceAuthor, decided_on: decidedOn, recording_basis: basis,
    })}>
      <label htmlFor="support-outcome" className="block text-[14px] font-medium">Результат рассмотрения</label>
      <select id="support-outcome" className={field} value={outcome} onChange={(e) => setOutcome(e.target.value)}>
        <option value="approved">Одобрено</option><option value="declined">Отказ</option><option value="needs_information">Нужно дополнение</option>
      </select>
      <TextField label="Объяснение сотруднику" multiline value={text} onChange={setText} />
      <TextField label="Реквизиты внешнего решения" value={source} onChange={setSource} />
      <TextField label="Автор внешнего решения" value={sourceAuthor} onChange={setSourceAuthor} />
      <label className="block text-[14px] font-medium">Дата решения<input className={field} type="date" required value={decidedOn} onChange={(e) => setDecidedOn(e.target.value)} /></label>
      <TextField label="Основание регистрации" value={basis} onChange={setBasis} />
    </ActionForm>}
    {role === 'coordinator' && item.status === 'decision_recorded' && <ActionForm title="Назначить исполнителя" action="Назначить исполнителя" busy={busy} submit={() => void command('executor-assignment', { executor_actor_id: supportFixtureActors.executor, assignment_basis: source })}>
      <p className="text-[14px]">Учебный регистратор исполнения — executor.</p>
      <TextField label="Основание назначения исполнителя" value={source} onChange={setSource} />
    </ActionForm>}
    {role === 'executor' && item.extract?.outcome === 'approved' && item.status === 'decision_recorded' && <ActionForm title="Записать исполнение" action="Сохранить факт исполнения" busy={busy} submit={() => void command('execution', {
      status: execution, source_reference: source, source_author: sourceAuthor, occurred_on: decidedOn || null, note: text,
    })}>
      <label htmlFor="support-execution" className="block text-[14px] font-medium">Состояние исполнения</label>
      <select id="support-execution" className={field} value={execution} onChange={(e) => setExecution(e.target.value)}>
        <option value="unknown">Не подтверждено</option><option value="confirmed">Подтверждено источником</option><option value="failed">Ошибка исполнения</option>
      </select>
      <TextField label="Источник исполнения" value={source} onChange={setSource} />
      <TextField label="Автор источника" value={sourceAuthor} onChange={setSourceAuthor} />
      <label className="block text-[14px] font-medium">Дата исполнения<input className={field} type="date" value={decidedOn} onChange={(e) => setDecidedOn(e.target.value)} /></label>
      <TextField label="Комментарий к исполнению" multiline value={text} onChange={setText} />
    </ActionForm>}
    {role === 'specialist' && item.status === 'decision_recorded' && <ActionForm title="Закрыть дело" action="Закрыть дело" busy={busy} submit={() => void command('close', { reason: text })}>
      <TextField label="Основание закрытия" multiline value={text} onChange={setText} />
    </ActionForm>}
    {(item.documents ?? []).length > 0 && <div className="space-y-2 border-t border-[#E1E5EB] pt-4">
      <h3 className="font-bold">Документы дела</h3>
      {(item.documents ?? []).map((doc) => <button key={doc.id} type="button" className="block text-left text-[14px] text-[#1F4FD1] hover:underline" onClick={() => {
        void downloadSupportDocument(role, item, doc).catch((e) => onError(message(e)));
      }}>{doc.original_name} · {Math.ceil(doc.size_bytes / 1024)} КБ</button>)}
    </div>}
  </div>;
}

export default function SupportPage() {
  const [role, setRole] = useState<SupportRole>('employee');
  const [rules, setRules] = useState<SupportRule[]>([]);
  const [cases, setCases] = useState<SupportCase[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<SupportCase | null>(null);
  const [history, setHistory] = useState<SupportEvent[]>([]);
  const [statement, setStatement] = useState('');
  const [ruleId, setRuleId] = useState('');
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(''); setDetail(null); setHistory([]);
    Promise.all([
      supportRequest<SupportRule[]>(role, '/rules', { signal: controller.signal }),
      supportRequest<SupportCase[]>(role, '/cases', { signal: controller.signal }),
    ]).then(([available, rows]) => { setRules(available); setCases(rows); setRuleId((id) => available.some((r) => r.id === id) ? id : available[0]?.id || ''); })
      .catch((e) => { if (!controller.signal.aborted) setError(message(e)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [role, reload]);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController(); setDetail(null); setHistory([]); setError('');
    if (role === 'coordinator') {
      setDetail(cases.find((item) => item.id === selectedId) || null);
      return;
    }
    Promise.all([
      supportRequest<SupportCase>(role, '/cases/' + selectedId, { signal: controller.signal }),
      supportRequest<SupportEvent[]>(role, '/cases/' + selectedId + '/history', { signal: controller.signal }),
    ]).then(([item, events]) => { setDetail(item); setHistory(events); })
      .catch((e) => { if (!controller.signal.aborted) setError(message(e)); });
    return () => controller.abort();
  }, [selectedId, role, cases]);

  async function command(path: string, values: Record<string, unknown>, method = 'POST') {
    if (!detail) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await supportRequest(role, '/cases/' + detail.id + (path ? '/' + path : ''), {
        method, body: JSON.stringify({ expected_revision: detail.revision, ...values }),
      });
      setNotice('Изменение сохранено.'); setReload((value) => value + 1);
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  async function upload(key: string, file: File) {
    if (!detail) return;
    if (file.size === 0 || file.size > 10 * 1024 * 1024) { setError('Выберите непустой файл размером до 10 МБ.'); return; }
    setBusy(true); setError(''); setNotice('');
    const body = new FormData(); body.set('file', file); body.set('item_key', key); body.set('expected_revision', String(detail.revision));
    try {
      await supportRequest<SupportDocument>(role, '/cases/' + detail.id + '/documents', { method: 'POST', body });
      setNotice('Документ загружен.'); setReload((value) => value + 1);
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  async function create() {
    setBusy(true); setError('');
    try {
      const item = await supportRequest<SupportCase>(role, '/cases', { method: 'POST', body: JSON.stringify({ rule_version_id: ruleId, statement }) });
      setCreating(false); setSelectedId(item.id); setStatement(''); setReload((value) => value + 1);
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  const rule = rules.find((entry) => entry.id === detail?.rule_version_id);
  return <div className="mx-auto max-w-[1240px] space-y-5 px-4 py-8 sm:px-6">
    <PageTitle title="Материальная помощь" subtitle="Заявление, документы и личный результат рассмотрения." right={<Badge>API · учебные условия</Badge>} />
    <div className="flex items-center gap-4">
      <label htmlFor="support-role" className="text-[14px] text-[#4A5363]">Учебная роль</label>
      <select id="support-role" className={field + ' !mt-0 !w-auto'} value={role} disabled={busy} onChange={(e) => {
        setRole(e.target.value as SupportRole); setCases([]); setSelectedId(''); setCreating(false); setNotice('');
      }}>{supportRoles.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
      <Btn onClick={() => setReload((value) => value + 1)} disabled={busy}>Обновить</Btn>
      {role === 'employee' && <Btn variant="primary" onClick={() => { setCreating(true); setSelectedId(''); setNotice(''); }}>Новое заявление</Btn>}
    </div>
    {error && <div role="alert" className="rounded-xl border border-[#F3B8B8] bg-[#FCE8E8] p-4">{error}</div>}
    {notice && <div role="status" className="rounded-xl border border-[#9FD0AC] bg-[#E3F2E7] p-4">{notice}</div>}
    {loading && <Card>Загружаем дела…</Card>}
    {creating ? <Card><ActionForm title="Новое заявление" action="Сохранить черновик" busy={busy} submit={() => void create()}>
      <label htmlFor="support-rule" className="block text-[14px] font-medium">Условия подачи</label>
      <select id="support-rule" className={field} value={ruleId} onChange={(e) => setRuleId(e.target.value)} required>
        {rules.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
      </select>
      <p className="text-[14px] text-[#4A5363]">{rules.find((item) => item.id === ruleId)?.required_items.map((item) => item.title).join(' · ')}</p>
      <TextField label="Заявление" value={statement} onChange={setStatement} multiline />
    </ActionForm></Card> : <div className="grid grid-cols-[330px_minmax(0,1fr)] items-start gap-5">
      <Card className="!p-3 space-y-2">
        {!loading && cases.length === 0 && <p className="p-3 text-[#4A5363]">Доступных дел пока нет.</p>}
        {cases.map((item) => <button type="button" key={item.id} onClick={() => { setSelectedId(item.id); setNotice(''); }} className={`block w-full rounded-xl border p-3 text-left ${selectedId === item.id ? 'border-[#1F4FD1] bg-[#EEF3FE]' : 'border-[#E1E5EB] bg-white hover:bg-[#F8F9FB]'}`}>
          <span className="block truncate font-semibold">{item.number || 'Черновик заявления'}</span>
          <span className="block text-[13px] text-[#4A5363]">{date(item.submitted_at || item.created_at)}</span>
          <Badge tone={item.status === 'needs_information' ? 'amber' : item.status === 'closed' ? 'green' : 'blue'}>{statuses[item.status] || item.status}</Badge>
        </button>)}
      </Card>
      {detail ? <div className="space-y-5">
        <Card className="space-y-3">
          <h2 className="text-[20px] font-bold">{detail.number ? 'Заявление о помощи' : 'Черновик заявления'}</h2>
          <p className="text-[13px] text-[#4A5363] break-all">{detail.number || detail.id} · редакция {detail.revision}</p>
          {detail.statement && <p className="whitespace-pre-wrap">{detail.statement}</p>}
          {detail.public_message && <div className="rounded-xl bg-[#EEF3FE] p-4"><strong>Сообщение по делу</strong><p>{detail.public_message}</p></div>}
          {detail.extract && <div className="rounded-xl border border-[#9FD0AC] bg-[#E3F2E7] p-4 space-y-1">
            <h3 className="font-bold">Личная выписка</h3><p>{outcomeNames[detail.extract.outcome]} · {date(detail.extract.decided_on)}</p>
            <p>{detail.extract.public_explanation}</p><p className="text-[13px]">Версия {detail.extract.version}</p>
          </div>}
          {detail.extract?.outcome === 'approved' && <p className="font-medium">{executionNames[detail.execution?.status || 'unknown']}{detail.execution?.occurred_on ? ' · ' + date(detail.execution.occurred_on) : ''}</p>}
        </Card>
        <Card><CaseActions key={role + detail.id} role={role} item={detail} rule={rule} busy={busy} command={command} upload={upload} onError={setError} /></Card>
        {history.length > 0 && <Card><h3 className="font-bold mb-3">История дела</h3><div className="space-y-2 text-[14px]">
          {history.map((event) => <p key={event.id}>{date(event.recorded_at)} · {event.public.message || eventNames[event.action] || 'Изменение дела'}</p>)}
        </div></Card>}
      </div> : !loading && <Card>Выберите дело из списка.</Card>}
    </div>}
  </div>;
}
const eventNames: Record<string, string> = {
  draft_created: 'Черновик создан', draft_edited: 'Текст обновлён', document_uploaded: 'Документ загружен',
  submitted: 'Заявление подано', assigned: 'Ответственные назначены', staff_confirmation: 'Кадровое основание проверено',
  completeness_reviewed: 'Комплект проверен', addendum_submitted: 'Дополнение получено',
  decision_recorded: 'Решение зарегистрировано', decision_corrected: 'Решение исправлено',
  execution_recorded: 'Исполнение зарегистрировано', closed: 'Дело закрыто', withdrawn: 'Заявление отозвано',
};
