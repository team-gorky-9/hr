import { useEffect, useRef, useState } from 'react';
import { archiveApi, contour, request, type Hit, type Vacancy, type Reserve, type TextSource, type History, type SearchResult } from '../../api/archive';
import { Card, Btn, Badge } from '../shared/ui';

const field = 'w-full px-3 py-2 text-[14px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24]';
const formatDate = (value: string | null) => value ? new Date(value).toLocaleDateString('ru-RU') : 'Не указана';
const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Не удалось выполнить запрос.';
const stages: Record<string, string> = {
  new: 'Новый отклик', screening: 'Первичный отбор', phone_interview: 'Телефонное интервью',
  sent_to_department: 'Передан в департамент', department_interview: 'Собеседование в департаменте',
  documents: 'Оформление документов', hired: 'Принят', rejected: 'Отказ', withdrawn: 'Кандидат отказался',
};

function CandidateArchive({ hit, vacancy, onBack }: { hit: Hit; vacancy: Vacancy; onBack: () => void }) {
  const [entries, setEntries] = useState<Reserve[]>([]);
  const [source, setSource] = useState<TextSource | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [applicationId, setApplicationId] = useState('');
  const [reason, setReason] = useState(hit.evidence?.fragment ?? '');
  const [basis, setBasis] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [historyError, setHistoryError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);
  const [createdId, setCreatedId] = useState('');
  const entry = entries.find((item) => item.candidate_id === hit.candidate_id);
  const historyRequest = useRef<AbortController | null>(null);
  useEffect(() => () => historyRequest.current?.abort(), []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    Promise.all([
      archiveApi.reserve(vacancy.position_id, controller.signal),
      hit.evidence ? archiveApi.source(hit.evidence.candidate_text_id, controller.signal) : Promise.resolve(null),
    ]).then(([list, text]) => { setEntries(list.items); setSource(text); })
      .catch((e) => { if (!controller.signal.aborted) setError(errorMessage(e)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [hit, vacancy.position_id, reload]);

  async function showHistory(id: string) {
    historyRequest.current?.abort();
    const controller = new AbortController(); historyRequest.current = controller;
    setApplicationId(id); setHistory(null); setHistoryError('');
    try { setHistory(await archiveApi.history(id, controller.signal)); }
    catch (e) { if (!controller.signal.aborted) setHistoryError(errorMessage(e)); }
  }

  async function save() {
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await archiveApi.save(hit.candidate_id, vacancy.position_id, reason, basis);
      setEntries((items) => [...items.filter((item) => item.reserve_id !== result.entry.reserve_id), result.entry]);
      setNotice(result.created ? 'Подборка сохранена.' : 'Действующая подборка уже существует.');
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  async function reconsider() {
    if (!entry) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await request<{ application_id: string; created: boolean }>('/archive/reconsiderations', {
        method: 'POST', body: JSON.stringify({
          candidate_id: hit.candidate_id, vacancy_id: vacancy.vacancy_id,
          reserve_id: entry.reserve_id, contour, confirmation,
        }),
      });
      setCreatedId(result.application_id);
      setNotice(result.created ? 'Новое рассмотрение создано.' : 'По этой вакансии уже есть рассмотрение. Открыта существующая запись.');
      await showHistory(result.application_id);
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  const quote = hit.evidence;
  const quoteMatches = source && quote && source.text.slice(quote.utf16_start, quote.utf16_end) === quote.fragment;
  return (
    <div className="space-y-5">
      <Btn variant="link" onClick={onBack}>← К результатам поиска</Btn>
      <Card>
        <h1 className="text-[24px] font-bold">{hit.candidate_code}</h1>
        <p className="text-[14px] text-[#4A5363] mt-1">Целевая вакансия — {vacancy.title}</p>
      </Card>
      {error && <div role="alert" className="bg-[#FCE8E8] border border-[#F3B8B8] rounded-xl p-4">{error} <Btn onClick={() => setReload((value) => value + 1)}>Повторить чтение</Btn></div>}
      {notice && <div role="status" className="bg-[#E3F2E7] border border-[#9FD0AC] rounded-xl p-4">{notice}</div>}
      <div className="grid grid-cols-[minmax(0,2fr)_minmax(320px,1fr)] gap-6 items-start">
        <div className="space-y-5">
          <Card>
            <h2 className="text-[18px] font-bold mb-3">Основание поиска</h2>
            {loading ? <p>Загружаем источник…</p> : source ? (
              <>
                <p className="text-[13px] text-[#4A5363] mb-3">Очищенное резюме · версия {source.version} · {source.is_current ? 'текущая' : 'историческая'}</p>
                <div className="whitespace-pre-wrap text-[14px] leading-relaxed bg-[#F8FAFC] rounded-xl p-4">
                  {quoteMatches && quote ? <>{source.text.slice(0, quote.utf16_start)}<mark className="bg-[#FFE39A]">{source.text.slice(quote.utf16_start, quote.utf16_end)}</mark>{source.text.slice(quote.utf16_end)}</> : source.text}
                </div>
                {quote && !quoteMatches && <p className="text-[#A3171B] mt-2">Позиция цитаты не совпала с источником. Проверьте текст.</p>}
              </>
            ) : <p>Результат получен по фильтрам. Текстовой цитаты в ответе нет.</p>}
          </Card>
          <Card>
            <h2 className="text-[18px] font-bold mb-3">Прежние рассмотрения</h2>
            {hit.applications.length === 0 && <p className="text-[#4A5363]">Прежних рассмотрений в ответе сервера нет.</p>}
            <div className="divide-y divide-[#E1E5EB]">
              {hit.applications.map((app) => (
                <button key={app.application_id} className="block w-full text-left py-3 hover:bg-[#F8FAFC]" onClick={() => showHistory(app.application_id)}>
                  <span className="font-medium text-[#1F4FD1]">{app.position_title || app.posting_title || app.external_position_title || 'Без названия'}</span>
                  <span className="block text-[13px] text-[#4A5363]">{stages[app.stage_code] || app.stage_code} · {formatDate(app.applied_at)} · {app.source === 'history' ? 'Архивная история' : 'Рассмотрение'}</span>
                </button>
              ))}
            </div>
            {createdId && <Btn variant="link" onClick={() => showHistory(createdId)}>Открыть созданное рассмотрение</Btn>}
            {historyError && <p role="alert" className="text-[#A3171B]">{historyError}</p>}
            {applicationId && !history && !historyError && <p>Читаем историю…</p>}
            {history && <div className="mt-4 pt-4 border-t border-[#E1E5EB]">
              <h3 className="font-semibold">Этап — {history.stage.title}</h3>
              {history.items.map((event) => <div key={event.seq} className="py-2 text-[14px]">
                {formatDate(event.created_at)} · {event.to_stage.title}
                {event.rejection_reason && <p>{event.rejection_reason.title}</p>}
                {event.comment && <p className="text-[#4A5363] whitespace-pre-wrap">{event.comment}</p>}
              </div>)}
            </div>}
          </Card>
        </div>
        <Card>
          <h2 className="text-[18px] font-bold mb-3">Подборка на целевую должность</h2>
          {loading ? <p>Читаем основание контакта…</p> : entry ? (
            <div className="space-y-3 text-[14px]">
              <Badge tone="green">Действующая запись</Badge>
              <p>{entry.reason}</p>
              <div><h3 className="font-semibold">Основание контакта</h3><p>{entry.contact_basis || 'Не указано'}</p></div>
              <p className="text-[#4A5363]">Добавлена {formatDate(entry.added_at)} · {entry.added_by?.login || 'Автор не указан'}<br />Срок — {entry.valid_until ? formatDate(entry.valid_until) : 'не установлен'}</p>
            </div>
          ) : <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void save(); }}>
            <p className="text-[14px] text-[#4A5363]">Запишите профессиональное основание и подтверждённое основание повторного контакта.</p>
            <label className="block text-[14px]">Почему рассматриваем<textarea className={field} value={reason} onChange={(e) => setReason(e.target.value)} rows={3} /></label>
            <label className="block text-[14px]">Основание контакта<textarea className={field} value={basis} onChange={(e) => setBasis(e.target.value)} rows={3} /></label>
            <Btn type="submit" variant="primary" disabled={busy || !reason.trim() || !basis.trim() || Boolean(error)}>Сохранить в подборку</Btn>
          </form>}
          <form className="mt-5 pt-4 border-t border-[#E1E5EB] space-y-3" onSubmit={(e) => { e.preventDefault(); void reconsider(); }}>
            <h3 className="font-semibold">Новое рассмотрение</h3>
            <p className="text-[14px] text-[#4A5363]">После обращения к кандидату запишите его согласие на выбранную вакансию.</p>
            <label className="block text-[14px]">Когда и как получено согласие<textarea className={field} rows={3} value={confirmation} onChange={(e) => setConfirmation(e.target.value)} /></label>
            <Btn type="submit" variant="primary" disabled={busy || loading || !entry?.contact_basis || !confirmation.trim() || Boolean(createdId)}>
              {busy ? 'Сохраняем…' : 'Начать рассмотрение'}
            </Btn>
          </form>
        </Card>
      </div>
    </div>
  );
}

export default function ArchivePage() {
  const [vacancies, setVacancies] = useState<Vacancy[]>([]);
  const [vacancyId, setVacancyId] = useState('');
  const [query, setQuery] = useState('');
  const [onlyReserve, setOnlyReserve] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [selected, setSelected] = useState<Hit | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const searchRequest = useRef<AbortController | null>(null);
  const vacancy = vacancies.find((item) => item.vacancy_id === vacancyId);
  useEffect(() => {
    const controller = new AbortController(); setError('');
    archiveApi.vacancies(controller.signal).then((response) => setVacancies(response.items.filter((item) => item.status === 'open')))
      .catch((e) => { if (!controller.signal.aborted) setError(errorMessage(e)); });
    return () => controller.abort();
  }, [reload]);
  useEffect(() => () => searchRequest.current?.abort(), []);
  async function search() {
    searchRequest.current?.abort();
    const controller = new AbortController(); searchRequest.current = controller;
    setLoading(true); setError(''); setResult(null);
    try { setResult(await archiveApi.search(query, onlyReserve, controller.signal)); }
    catch (e) { if (!controller.signal.aborted) setError(errorMessage(e)); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8">
      <div className="mb-5 flex justify-between items-start gap-4">
        <div><h1 className="text-[26px] font-bold">Архив кадров</h1><p className="text-[14px] text-[#616977]">Поиск под новую вакансию и повторное рассмотрение.</p></div>
        <Badge>{contour === 'training' ? 'Учебные записи' : 'Рабочие записи'}</Badge>
      </div>
      {selected && vacancy ? <CandidateArchive key={selected.candidate_id + vacancyId} hit={selected} vacancy={vacancy} onBack={() => setSelected(null)} /> : (
        <div className="space-y-5">
          <form className="bg-white border border-[#E1E5EB] rounded-2xl p-6 space-y-4" onSubmit={(e) => { e.preventDefault(); void search(); }}>
            <div className="grid grid-cols-2 gap-5">
              <label className="text-[14px] font-medium">Целевая вакансия<select aria-label="Целевая вакансия" className={field} value={vacancyId} onChange={(e) => { setVacancyId(e.target.value); setSelected(null); }}>
                <option value="">Выберите вакансию</option>
                {vacancies.map((item) => <option key={item.vacancy_id} value={item.vacancy_id}>{item.title}</option>)}
              </select></label>
              <label className="text-[14px] font-medium">Нужный опыт<input className={field} value={query} onChange={(e) => setQuery(e.target.value)} maxLength={512} placeholder="Например, анализ требований к ИС" /></label>
            </div>
            <div className="flex items-center gap-6">
              <Btn type="submit" variant="primary" disabled={loading || !vacancy || (!query.trim() && !onlyReserve)}>Найти кандидатов</Btn>
              <label className="text-[14px] flex gap-2"><input type="checkbox" checked={onlyReserve} onChange={(e) => setOnlyReserve(e.target.checked)} />Только действующие подборки</label>
            </div>
          </form>
          {error && <div role="alert" className="bg-[#FCE8E8] rounded-xl p-4">{error} <Btn onClick={() => { setReload((v) => v + 1); if (vacancy) void search(); }}>Повторить</Btn></div>}
          {loading && <Card>Ищем кандидатов…</Card>}
          {result && <>
            <p className="text-[14px] text-[#4A5363]">Найдено записей — {result.items.length}. {result.mode === 'lexical' ? 'Поиск по словам.' : result.mode === 'filters' ? 'Поиск по фильтрам.' : 'Гибридный поиск.'} {result.semantic_status === 'partial' && 'Смысловой индекс заполнен частично.'}</p>
            <div className="bg-white border border-[#E1E5EB] rounded-2xl overflow-hidden">
              <table className="w-full text-left text-[14px]">
                <thead className="bg-[#FAFBFD] border-b border-[#E1E5EB] text-[#616977]"><tr>
                  <th className="py-3.5 px-5">Кандидат</th><th className="py-3.5 px-3">Основание совпадения</th><th className="py-3.5 px-3">Подборка</th><th className="py-3.5 px-3">Прежние рассмотрения</th>
                </tr></thead>
                <tbody className="divide-y divide-[#E1E5EB]">
                  {result.items.map((hit) => <tr key={hit.candidate_id} className="hover:bg-[#F8FAFC]">
                    <td className="py-3.5 px-5"><button className="text-[#1F4FD1] hover:underline font-medium" onClick={() => setSelected(hit)}>{hit.candidate_code}</button></td>
                    <td className="py-3.5 px-3 max-w-[420px]">{hit.evidence?.fragment || 'Совпадение по выбранным фильтрам'}</td>
                    <td className="py-3.5 px-3">{hit.in_reserve ? 'Есть действующая' : 'Не найдена'}</td>
                    <td className="py-3.5 px-3">{hit.applications.length}</td>
                  </tr>)}
                </tbody>
              </table>
              {result.items.length === 0 && <p className="p-8 text-[#4A5363]">Совпадений нет. Измените описание опыта или фильтр.</p>}
            </div>
          </>}
        </div>
      )}
    </div>
  );
}
