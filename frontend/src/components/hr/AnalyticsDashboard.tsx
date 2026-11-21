import { useEffect, useState } from 'react';
import { archiveApi, contour, request, type Vacancy } from '../../api/archive';
import { annualReportsPath, downloadWorkbook } from '../../api/reports';
import ReportPage from '../report/ReportPage';
import { Btn, Card } from '../shared/ui';

export type AnalyticsView = 'dashboard' | 'config' | 'ready';
type DashboardVacancy = Vacancy & { channel?: string; applications_count?: number };
type Funnel = {
  as_of: string;
  total_applications: number;
  stages: { code: string; title: string; reached_count: number }[];
  closures: { stage_code: string; reason_title: string; count: number }[];
  open_waits: { total: number; due_soon_total: number; overdue_total: number };
};

const field = 'px-3 py-1.5 border border-[#E1E5EB] rounded-lg bg-white text-[#141A24] text-[13px]';
const periodOptions = ['Неделя', 'Месяц', 'Квартал', 'Год', 'Свой период'];
const channelNames: Record<string, string> = { hh_ru: 'HH.ru', rabota_rossii: 'Работа России', city_site: 'Сайт администрации', email: 'Электронная почта', citizen_appeal: 'Обращения граждан', internship: 'Практика' };
const statusNames: Record<string, string> = { open: 'Открыта', closed: 'Закрыта', draft: 'Черновик', paused: 'Приостановлена' };
const weeklyData = [
  { label: '21–27 окт', screenedHeight: '52%', interviewHeight: '40%' },
  { label: '28 окт–3 ноя', screenedHeight: '70%', interviewHeight: '48%' },
  { label: '4–10 ноя', screenedHeight: '92%', interviewHeight: '68%' },
  { label: '11–17 ноя', screenedHeight: '88%', interviewHeight: '68%' },
  { label: '18–20 ноя', screenedHeight: '60%', interviewHeight: '42%' },
];

export default function AnalyticsDashboard() {
  const [view, setView] = useState<AnalyticsView>('dashboard');
  const [activePeriod, setActivePeriod] = useState('Свой период');
  const [vacancies, setVacancies] = useState<DashboardVacancy[]>([]);
  const [vacancy, setVacancy] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [reload, setReload] = useState(0);
  const invalidDates = Boolean(from && to && from > to);

  useEffect(() => {
    const controller = new AbortController();
    archiveApi.vacancies(controller.signal).then(({ items }) => setVacancies(items)).catch((failure) => {
      if (!controller.signal.aborted) setError(failure.message);
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

  function selectPeriod(period: string) {
    setActivePeriod(period);
    if (period === 'Свой период') return;
    const end = new Date();
    const start = new Date(end);
    const days = { Неделя: 6, Месяц: 29, Квартал: 89, Год: 364 }[period] ?? 29;
    start.setUTCDate(start.getUTCDate() - days);
    setFrom(start.toISOString().slice(0,10));
    setTo(end.toISOString().slice(0,10));
  }

  async function downloadAnnual() {
    setError('');
    setDownloading(true);
    try {
      const versions = await request<{ snapshot_id: string }[]>(annualReportsPath);
      if (!versions[0]) throw new Error('Доступных снимков пока нет.');
      await downloadWorkbook(versions[0].snapshot_id, '/xlsx');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Не удалось скачать отчёт.');
    } finally {
      setDownloading(false);
    }
  }

  const stageCount = (code: string) => funnel?.stages.find((stage) => stage.code === code)?.reached_count;
  const barWidth = (value: number, max: number) => (100 * value / Math.max(max, 1)) + '%';
  const funnelData = funnel?.stages.map((stage) => ({ stage: stage.title, count: stage.reached_count, width: barWidth(stage.reached_count, funnel.total_applications) })) ?? [];
  const channels = new Map<string, number>();
  const rejectionCounts = new Map<string, number>();
  for (const item of vacancies) {
    if (!item.channel || (vacancy && item.vacancy_id !== vacancy)) continue;
    channels.set(item.channel, (channels.get(item.channel) || 0) + (item.applications_count ?? 0));
  }
  for (const item of funnel?.closures ?? []) {
    if (item.stage_code !== 'rejected') continue;
    rejectionCounts.set(item.reason_title, (rejectionCounts.get(item.reason_title) || 0) + item.count);
  }
  const maxChannel = Math.max(1, ...channels.values());
  const sourcesData = Array.from(channels, ([source, count]) => ({ source: channelNames[source] || source, count, width: barWidth(count, maxChannel) }));
  const maxRejection = Math.max(1, ...rejectionCounts.values());
  const rejectionData = Array.from(rejectionCounts, ([reason, count]) => ({ reason, count, width: barWidth(count, maxRejection) })).sort((a,b) => b.count-a.count);
  const vacanciesSLA = vacancies.filter((item) => !vacancy || item.vacancy_id === vacancy).map((item) => {
    const selected = item.vacancy_id === vacancy && funnel;
    return {
      title: item.title, responses: item.applications_count ?? '—',
      interview: selected ? stageCount('phone_interview') ?? '—' : '—',
      forwarded: selected ? stageCount('sent_to_department') ?? '—' : '—',
      status: statusNames[item.status] || 'Иной статус',
      slaStatus: selected ? selected.open_waits.overdue_total ? 'Просрочено: ' + selected.open_waits.overdue_total
        : selected.open_waits.total ? 'Ожидается: ' + selected.open_waits.total : 'Нет открытых передач' : 'Выберите вакансию',
      slaColor: selected && selected.open_waits.overdue_total ? 'bg-[#FEE2E2] text-[#B91C1C]' : 'bg-[#EEF1F5] text-[#4A5363]',
    };
  });

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div className="flex items-center justify-end">
        <div className="flex items-center gap-1 bg-white border border-[#E1E5EB] rounded-lg p-1 text-xs">
          <button
            type="button"
            onClick={() => setView('dashboard')}
            className={`px-2.5 py-1 rounded font-medium transition-colors whitespace-nowrap ${
              view === 'dashboard'
                ? 'bg-[#1F4FD1] text-white shadow-sm'
                : 'text-[#4A5363] hover:text-[#141A24]'
            }`}
          >
            Дашборд
          </button>
          <button
            type="button"
            onClick={() => setView('config')}
            className={`px-2.5 py-1 rounded font-medium transition-colors whitespace-nowrap ${
              view === 'config'
                ? 'bg-[#1F4FD1] text-white shadow-sm'
                : 'text-[#4A5363] hover:text-[#141A24]'
            }`}
          >
            Настройка отчёта
          </button>
          <button
            type="button"
            onClick={() => setView('ready')}
            className={`px-2.5 py-1 rounded font-medium transition-colors whitespace-nowrap ${
              view === 'ready'
                ? 'bg-[#1F4FD1] text-white shadow-sm'
                : 'text-[#4A5363] hover:text-[#141A24]'
            }`}
          >
            Готовый отчёт
          </button>
        </div>
      </div>

      {view === 'dashboard' && (
        <>
          {/* Header & Filters Card */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
              <div>
                <h1 className="text-[22px] font-bold text-[#141A24] tracking-tight mb-1">
                  Аналитика и отчёты
                </h1>
                <p className="text-[13px] text-[#616977]">
                  {funnel ? 'Состояние подбора · ' + new Date(funnel.as_of).toLocaleString('ru-RU') : 'Состояние подбора'}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => void downloadAnnual()} disabled={downloading}
                  className="px-4 py-2 text-[13px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors whitespace-nowrap"
                >
                  Скачать годовой XLSX
                </button>
                <button
                  type="button"
                  onClick={() => setView('config')}
                  className="px-4 py-2 text-[13px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm whitespace-nowrap"
                >
                  Сформировать отчёт
                </button>
              </div>
            </div>

            {/* Filter controls row */}
            <div className="flex flex-wrap items-center gap-4 pt-2 border-t border-[#F0F2F5]">
              <div className="inline-flex flex-wrap rounded-lg bg-[#F3F5F8] p-1">
                {periodOptions.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => selectPeriod(p)} aria-pressed={activePeriod === p}
                    className={`px-3 py-1 text-[13px] font-medium rounded-md transition-all whitespace-nowrap ${
                      activePeriod === p
                        ? 'bg-white text-[#141A24] shadow-sm font-semibold'
                        : 'text-[#616977] hover:text-[#141A24]'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-3 text-[13px]">
                <div className="flex items-center gap-2">
                  <label>Закрытие с <input type="date" value={from} onChange={(event) => { setFrom(event.target.value); setActivePeriod('Свой период'); }} className={field} /></label>
                  <label>по <input type="date" value={to} onChange={(event) => { setTo(event.target.value); setActivePeriod('Свой период'); }} className={field} /></label>
                </div>

                <div className="flex items-center gap-2">
                  <button type="button" className={field} onClick={() => setNotice('Будет добавлено позже')}>Сравнить с прошлым периодом</button>
                </div>

                <div className="flex items-center gap-2">
                  <label>Вакансия <select className={field} value={vacancy} onChange={(event) => setVacancy(event.target.value)}>
                    <option value="">Все вакансии</option>
                    {vacancies.map((item) => <option key={item.vacancy_id} value={item.vacancy_id}>{item.title}</option>)}
                  </select></label>
                </div>
              </div>
            </div>
          </div>

          {error && <Card><p role="alert" className="text-[#A3171B]">{error}</p><Btn variant="link" onClick={() => setReload((value) => value + 1)}>Повторить</Btn></Card>}
          {invalidDates && <Card><p role="alert">Проверьте даты периода закрытия откликов.</p></Card>}
          {!funnel && !error && !invalidDates && <p role="status" className="text-[14px] text-[#616977]">Загружаем данные подбора…</p>}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: 'Получено откликов', value: funnel?.total_applications, caption: 'По выбранным вакансиям' },
              { label: 'Открытые передачи', value: funnel?.open_waits.total, caption: 'Ожидают ответа подразделения' },
              { label: 'Дошли до телефонного интервью', value: stageCount('phone_interview'), caption: 'По истории этапов' },
              { label: 'Приняты на работу', value: stageCount('hired'), caption: 'По истории этапов' },
            ].map(({ label, value, caption }) => <div key={label} className="bg-white border border-[#E1E5EB] rounded-2xl p-5 shadow-sm">
              <div className="text-[12px] text-[#616977] mb-1">{label}</div>
              <div className="text-[28px] font-bold text-[#141A24] mb-1">{value ?? '—'}</div>
              <div className="text-[12px] text-[#616977]">{caption}</div>
            </div>)}
          </div>

          {/* AI Insight Highlight Card */}
          <div className="bg-[#FAF7FF] border border-[#E5DBFF] rounded-2xl p-5 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-[#6B21A8] font-bold text-[14px]">↗</span>
                <h2 className="text-[15px] font-bold text-[#141A24]">
                  Главное по подбору
                </h2>
              </div>
              <span className="text-[12px] text-[#6B21A8]">
                По данным подбора
              </span>
            </div>
            {funnel ? <ul className="space-y-1.5 text-[13px] text-[#334155] leading-relaxed">
              <li>• Откликов в выбранном контуре: {funnel.total_applications}.</li>
              <li>• Открыто передач: {funnel.open_waits.total}. Срок подходит: {funnel.open_waits.due_soon_total}. Просрочено: {funnel.open_waits.overdue_total}.</li>
              {rejectionData[0] && <li>• Самая частая причина отказа за период: {rejectionData[0].reason} ({rejectionData[0].count}).</li>}
            </ul> : <p className="text-[13px] text-[#616977]">Сводка появится после загрузки данных.</p>}
          </div>

          {/* 2x2 Charts Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Chart 1: Воронка по вакансиям */}
            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
              <h2 className="text-[16px] font-bold text-[#141A24] mb-1">
                Воронка по моим вакансиям
              </h2>
              <p className="text-[12px] text-[#616977] mb-6">
                Сколько откликов достигло каждого этапа
              </p>
              <div className="space-y-3">
                {funnelData.map((f) => (
                  <div key={f.stage} className="flex items-center text-[13px]">
                    <span className="w-48 text-[#4A5363] shrink-0 truncate mr-2">
                      {f.stage}
                    </span>
                    <div className="flex-1 bg-[#F0F2F5] rounded-full h-5 overflow-hidden relative">
                      <div
                        className="bg-[#1F4FD1] h-full rounded-full transition-all duration-500"
                        style={{ width: f.width }}
                      ></div>
                    </div>
                    <span className="w-10 text-right font-medium text-[#141A24] ml-2">
                      {f.count}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Chart 2: Источники */}
            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
              <h2 className="text-[16px] font-bold text-[#141A24] mb-1">
                Источники
              </h2>
              <p className="text-[12px] text-[#616977] mb-6">
                Отклики в разрезе каналов вакансий
              </p>
              <div className="space-y-3">
                {!sourcesData.length && <p className="text-[13px] text-[#616977]">Данных пока нет.</p>}
                {sourcesData.map((s) => (
                  <div key={s.source} className="flex items-center text-[13px]">
                    <span className="w-36 text-[#4A5363] shrink-0 truncate mr-2">
                      {s.source}
                    </span>
                    <div className="flex-1 bg-[#F0F2F5] rounded-full h-5 overflow-hidden relative">
                      <div
                        className="bg-[#5C83F6] h-full rounded-full transition-all duration-500"
                        style={{ width: s.width }}
                      ></div>
                    </div>
                    <span className="w-10 text-right font-medium text-[#141A24] ml-2">
                      {s.count}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Chart 3: Динамика по неделям */}
            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
              <h2 className="text-[16px] font-bold text-[#141A24] mb-1">
                Динамика по неделям
              </h2>
              <p className="text-[12px] text-[#616977] mb-6">
                Пример расположения графика · Будет добавлено позже
              </p>
              <div className="h-44 flex items-end justify-between gap-3 pt-6 border-b border-[#E1E5EB] px-2 overflow-x-auto">
                {weeklyData.map((w) => (
                  <div key={w.label} className="flex-1 flex flex-col items-center gap-2 h-full justify-end">
                    <div className="w-full flex items-end justify-center gap-1.5 h-full">
                      <div
                        className="w-4 bg-[#1F4FD1] rounded-t-sm transition-all duration-500"
                        style={{ height: w.screenedHeight }}
                        title="Разобрано"
                      ></div>
                      <div
                        className="w-4 bg-[#7FA4FD] rounded-t-sm transition-all duration-500"
                        style={{ height: w.interviewHeight }}
                        title="Интервью"
                      ></div>
                    </div>
                    <span className="text-[11px] text-[#616977] whitespace-nowrap">
                      {w.label}
                    </span>
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-4 mt-3 text-[12px] text-[#616977]">
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded-sm bg-[#1F4FD1]"></span>
                  <span>Разобрано</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded-sm bg-[#7FA4FD]"></span>
                  <span>Интервью</span>
                </div>
              </div>
            </div>

            {/* Chart 4: Причины отказов */}
            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
              <h2 className="text-[16px] font-bold text-[#141A24] mb-1">
                Причины отказов
              </h2>
              <p className="text-[12px] text-[#616977] mb-6">
                {funnel ? 'Отказов за период: ' + rejectionData.reduce((sum, item) => sum + item.count, 0) : 'Загружаются данные'}
              </p>
              <div className="space-y-3">
                {funnel && !rejectionData.length && <p className="text-[13px] text-[#616977]">Отказов за период нет.</p>}
                {rejectionData.map((r) => (
                  <div key={r.reason} className="flex items-center text-[13px]">
                    <span className="w-44 text-[#4A5363] shrink-0 truncate mr-2">
                      {r.reason}
                    </span>
                    <div className="flex-1 bg-[#F0F2F5] rounded-full h-5 overflow-hidden relative">
                      <div
                        className="bg-[#C84A2A] h-full rounded-full transition-all duration-500"
                        style={{ width: r.width }}
                      ></div>
                    </div>
                    <span className="w-10 text-right font-medium text-[#141A24] ml-2">
                      {r.count}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Table: Мои вакансии */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl shadow-sm overflow-hidden">
            <div className="p-6 border-b border-[#E1E5EB]">
              <h2 className="text-[16px] font-bold text-[#141A24]">
                Вакансии
              </h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[14px]">
                <thead className="bg-[#FAFBFD] border-b border-[#E1E5EB] text-[13px] text-[#616977]">
                  <tr>
                    <th className="py-3 px-6 font-medium whitespace-nowrap">Вакансия</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Откликов</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Интервью</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Направлено</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Статус вакансии</th>
                    <th className="py-3 px-6 font-medium whitespace-nowrap">Ответ департамента</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E1E5EB]">
                  {vacanciesSLA.map((v) => (
                    <tr key={v.title} className="hover:bg-[#F8FAFC]">
                      <td className="py-3.5 px-6 font-medium text-[#141A24] whitespace-nowrap">
                        {v.title}
                      </td>
                      <td className="py-3.5 px-4 text-[#4A5363] whitespace-nowrap">{v.responses}</td>
                      <td className="py-3.5 px-4 text-[#4A5363] whitespace-nowrap">{v.interview}</td>
                      <td className="py-3.5 px-4 text-[#4A5363] whitespace-nowrap">{v.forwarded}</td>
                      <td className="py-3.5 px-4 text-[#4A5363] whitespace-nowrap">{v.status}</td>
                      <td className="py-3.5 px-6 whitespace-nowrap">
                        <span className={`inline-block px-2.5 py-0.5 rounded-full text-[12px] font-medium whitespace-nowrap ${v.slaColor}`}>
                          {v.slaStatus}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {view !== 'dashboard' && <>
        <Btn variant="link" onClick={() => setView('dashboard')}>← Аналитика и отчёты</Btn>
        <ReportPage embeddedView={view} onPrepared={() => setView('ready')} />
      </>}
      {notice && <div role="status" className="fixed bottom-6 right-6 z-50 rounded-xl bg-[#141A24] px-4 py-3 text-white">
        {notice}<button type="button" className="ml-3" aria-label="Закрыть уведомление" onClick={() => setNotice('')}>×</button>
      </div>}
    </div>
  );
}

