import { useEffect, useState } from 'react';
import { archiveApi, contour, request, type Vacancy } from '../../api/archive';
import ReportBars from '../report/ReportBars';
import ReportPage from '../report/ReportPage';
import { Badge, Btn, Card, Kpi, PageTitle } from '../shared/ui';

type Funnel = {
  as_of: string;
  total_applications: number;
  stages: { code: string; title: string; reached_count: number }[];
  closures: { stage_code: string; reason_title: string; count: number }[];
  open_waits: {
    total: number;
    due_soon_total: number;
    overdue_total: number;
    by_department: { department: string; total: number; due_soon_total: number; overdue_total: number }[];
  };
};

const field = 'w-full rounded-lg border border-[#E1E5EB] bg-white px-3 py-2 text-[14px]';
const views = [
  { id: 'dashboard', label: 'Дашборд' },
  { id: 'config', label: 'Настройка отчёта' },
  { id: 'ready', label: 'Готовый отчёт' },
] as const;
type AnalyticsView = typeof views[number]['id'];

export default function AnalyticsDashboard() {
  const [view, setView] = useState<AnalyticsView>('dashboard');
  const [vacancies, setVacancies] = useState<Vacancy[]>([]);
  const [vacancy, setVacancy] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const invalidDates = Boolean(from && to && from > to);

  useEffect(() => {
    const controller = new AbortController();
    archiveApi.vacancies(controller.signal).then(({ items }) => setVacancies(items)).catch(() => {
      if (!controller.signal.aborted) setVacancies([]);
    });
    return () => controller.abort();
  }, [reload]);

  useEffect(() => {
    setFunnel(null);
    setError('');
    if (invalidDates) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ contour });
    if (vacancy) params.set('vacancy_id', vacancy);
    if (from) params.set('period_from', from);
    if (to) params.set('period_to', to);
    request<Funnel>('/analytics/funnel?' + params, { signal: controller.signal }).then(setFunnel).catch((failure) => {
      if (!controller.signal.aborted) setError(failure.message);
    });
    return () => controller.abort();
  }, [vacancy, from, to, invalidDates, reload]);

  const rejections = new Map<string, number>();
  for (const closure of funnel?.closures ?? []) {
    if (closure.stage_code !== 'rejected') continue;
    rejections.set(closure.reason_title, (rejections.get(closure.reason_title) ?? 0) + closure.count);
  }

  return <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-6 space-y-6">
    <div className="flex justify-end">
      <nav className="flex flex-wrap gap-1 rounded-lg border border-[#E1E5EB] bg-white p-1 text-xs" aria-label="Аналитика и отчёты">
        {views.map((item) => <button key={item.id} type="button" aria-pressed={view === item.id} onClick={() => setView(item.id)}
          className={'rounded px-2.5 py-1 font-medium ' + (view === item.id ? 'bg-[#1F4FD1] text-white shadow-sm' : 'text-[#4A5363] hover:text-[#141A24]')}>{item.label}</button>)}
      </nav>
    </div>
    {view !== 'dashboard' ? <>
      <Btn variant="link" onClick={() => setView('dashboard')}>← Аналитика и отчёты</Btn>
      <ReportPage embeddedView={view} onPrepared={() => setView('ready')} />
    </> : <>
      <Card className="space-y-5">
        <PageTitle title="Аналитика и отчёты" subtitle={funnel ? 'Состояние подбора · ' + new Date(funnel.as_of).toLocaleString('ru-RU') : 'Состояние подбора'}
          right={<Btn variant="primary" onClick={() => setView('config')}>Сформировать отчёт</Btn>} />
        <div className="flex flex-wrap gap-4 border-t border-[#E1E5EB] pt-4 text-[14px]">
          <label className="min-w-0 max-w-full">Вакансия<select className={field} value={vacancy} onChange={(event) => setVacancy(event.target.value)}>
            <option value="">Все вакансии</option>
            {vacancies.map((item) => <option key={item.vacancy_id} value={item.vacancy_id}>{item.title}</option>)}
          </select></label>
          <label>Закрытые с<input className={field} type="date" value={from} onChange={(event) => setFrom(event.target.value)} /></label>
          <label>Закрытые по<input className={field} type="date" value={to} onChange={(event) => setTo(event.target.value)} /></label>
        </div>
      </Card>
      {invalidDates && <Card><p role="alert">Дата начала должна предшествовать дате окончания или совпадать с ней.</p></Card>}
      {error && <Card><p role="alert" className="text-[#A3171B]">{error}</p><Btn variant="link" onClick={() => setReload((value) => value + 1)}>Повторить</Btn></Card>}
      {!funnel && !error && !invalidDates && <Card>Загружаем данные подбора…</Card>}
      {funnel && <>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Kpi label="Отклики" value={funnel.total_applications} />
          <Kpi label="Открытые передачи" value={funnel.open_waits.total} />
          <Kpi label="Срок подходит" value={funnel.open_waits.due_soon_total} />
          <Kpi label="Просрочены" value={funnel.open_waits.overdue_total} />
        </div>
        <div className="grid gap-5 lg:grid-cols-2">
          <ReportBars title="Воронка подбора" points={funnel.stages.map((stage) => ({ label: stage.title, value: stage.reached_count }))} />
          <ReportBars title="Причины отказов за период" points={Array.from(rejections, ([label, value]) => ({ label, value }))} color="#C2410C" />
        </div>
        <Card className="overflow-x-auto">
          <h2 className="mb-4 text-[20px] font-bold">Ожидание ответов подразделений</h2>
          {funnel.open_waits.by_department.length ? <table className="w-full min-w-[32rem] text-left text-[14px]">
            <thead><tr><th>Подразделение</th><th>Открыто</th><th>Срок подходит</th><th>Просрочено</th></tr></thead>
            <tbody>{funnel.open_waits.by_department.map((item) => <tr key={item.department} className="border-t border-[#E1E5EB]">
              <td className="py-3">{item.department}</td><td>{item.total}</td><td><Badge tone="amber">{item.due_soon_total}</Badge></td><td><Badge tone="red">{item.overdue_total}</Badge></td>
            </tr>)}</tbody>
          </table> : <p>Открытых передач нет.</p>}
        </Card>
      </>}
    </>}
  </div>;
}

