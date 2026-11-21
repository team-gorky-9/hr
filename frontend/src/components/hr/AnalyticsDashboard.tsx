import { useEffect, useState } from 'react';
import { analyticsApi, type Dashboard, type Period, type ReportQuery, type ReportSlice, type ReportVersion } from '../../api/analytics';

export type AnalyticsView = 'dashboard' | 'config' | 'ready';
type Prepared = { version: ReportVersion; from: string; to: string; query: ReportQuery; slice: ReportSlice };
const periodOptions = ['Неделя', 'Месяц', 'Квартал', 'Год', 'Свой период'];
const periodDays: Record<string, number> = { Неделя: 7, Месяц: 30, Квартал: 90, Год: 365 };
const channelNames: Record<string, string> = {
  hh_ru: 'HH.ru', rabota_rossii: '«Работа России»', city_site: 'Сайт администрации', email: 'Почта',
  citizen_appeal: 'Обращения граждан', internship: 'Студенты', internal: 'Внутренние', other: 'Другие',
};
const stages = [
  ['new', 'Получено'], ['screening', 'Разобрано'], ['phone_interview', 'Телефонное собеседование'],
  ['sent_to_department', 'Направлено в департамент'], ['department_interview', 'Очное собеседование'], ['hired', 'Принято'],
];
const metrics = ['applications_received', 'phone_interviews_held', 'applications_with_phone_interview'];
const dayMs = 86_400_000;
const firstDate = '0001-01-02';
const lastDate = '9999-12-30';
const dayLabel = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', timeZone: 'UTC' });
const monthLabel = new Intl.DateTimeFormat('ru-RU', { month: 'short', timeZone: 'UTC' });
const dateText = (time: number) => new Date(time).toISOString().slice(0, 10);
const monthName = (month: string) => monthLabel.format(new Date(month + '-01T12:00:00Z'));
const message = (failure: unknown) => failure instanceof Error ? failure.message : 'Не удалось выполнить действие.';
const percent = (value: number, max: number) => 100 * value / Math.max(max, 1) + '%';
const isMonth = (value: string, year: number) => /^\d{4}-(0[1-9]|1[0-2])$/.test(value) && value.startsWith(String(year) + '-');

function latestPeriod(days: number): Period {
  const to = dateText(Date.now() + 3 * 3_600_000);
  return { from: dateText(Date.parse(to) - (days - 1) * dayMs), to };
}

function validPeriod({ from, to }: Period) {
  const days = (Date.parse(to) - Date.parse(from)) / dayMs;
  return from >= firstDate && to <= lastDate && Number.isFinite(days) && days >= 0 && days < 366;
}

function previousPeriod(period: Period, mode: string): Period {
  if (mode === 'year') {
    function shift(value: string) {
      const [year, month, day] = value.split('-').map(Number);
      const lastDay = new Date(0);
      lastDay.setUTCFullYear(year - 1, month, 0);
      const shifted = new Date(0);
      shifted.setUTCFullYear(year - 1, month - 1, Math.min(day, lastDay.getUTCDate()));
      return dateText(shifted.getTime());
    }
    return { from: shift(period.from), to: shift(period.to) };
  }
  const first = Date.parse(period.from);
  return { from: dateText(2 * first - Date.parse(period.to) - dayMs), to: dateText(first - dayMs) };
}

export default function AnalyticsDashboard() {
  const [view, setView] = useState<AnalyticsView>('dashboard');
  const [activePeriod, setActivePeriod] = useState('Месяц');
  const [period, setPeriod] = useState(() => latestPeriod(30));
  const [vacancy, setVacancy] = useState('');
  const [vacancies, setVacancies] = useState<{ vacancy_id: string; title: string }[]>([]);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [comparison, setComparison] = useState<Dashboard | null>(null);
  const [comparisonMode, setComparisonMode] = useState('previous');
  const [comparisonError, setComparisonError] = useState(false);
  const [dataError, setDataError] = useState('');
  const [vacancyError, setVacancyError] = useState('');
  const [reload, setReload] = useState(0);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [versions, setVersions] = useState<ReportVersion[]>([]);
  const [reportId, setReportId] = useState('');
  const [reportFrom, setReportFrom] = useState('');
  const [reportTo, setReportTo] = useState('');
  const [reportPreset, setReportPreset] = useState('Год');
  const [prepared, setPrepared] = useState<Prepared | null>(null);
  const invalidPeriod = !validPeriod(period);
  const reportVersion = versions.find((version) => version.snapshot_id === reportId);
  const reportMin = reportVersion ? reportVersion.year + '-01' : undefined;
  const reportMax = reportVersion ? reportVersion.year + '-12' : undefined;

  useEffect(() => {
    const controller = new AbortController();
    setVacancyError('');
    analyticsApi.vacancies(controller.signal)
      .then(({ items }) => { if (!controller.signal.aborted) setVacancies(items); })
      .catch((failure) => { if (!controller.signal.aborted) setVacancyError(message(failure)); });
    return () => controller.abort();
  }, [reload]);

  useEffect(() => {
    setDashboard(null);
    setDataError('');
    if (invalidPeriod) return;
    const controller = new AbortController();
    analyticsApi.dashboard(period, vacancy, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setDashboard(data); })
      .catch((failure) => { if (!controller.signal.aborted) setDataError(message(failure)); });
    return () => controller.abort();
  }, [period, vacancy, invalidPeriod, reload]);

  useEffect(() => {
    setComparison(null);
    setComparisonError(false);
    if (!comparisonMode || invalidPeriod) return;
    const range = previousPeriod(period, comparisonMode);
    if (!validPeriod(range)) {
      setComparisonError(true);
      return;
    }
    const controller = new AbortController();
    analyticsApi.dashboard(range, vacancy, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setComparison(data); })
      .catch(() => { if (!controller.signal.aborted) setComparisonError(true); });
    return () => controller.abort();
  }, [period, vacancy, invalidPeriod, reload, comparisonMode]);

  useEffect(() => {
    const controller = new AbortController();
    analyticsApi.versions(controller.signal).then((rows) => {
      if (controller.signal.aborted) return;
      setVersions(rows);
      setReportId((current) => current || rows[0]?.snapshot_id || '');
    }).catch((failure) => { if (!controller.signal.aborted) setNotice(message(failure)); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    setReportFrom(reportMin ?? '');
    setReportTo(reportMax ?? '');
    setReportPreset('Год');
  }, [reportMin, reportMax]);

  function selectPeriod(name: string) {
    setActivePeriod(name);
    if (periodDays[name]) setPeriod(latestPeriod(periodDays[name]));
  }

  function changePeriod(key: keyof Period, value: string) {
    setActivePeriod('Свой период');
    setPeriod((current) => ({ ...current, [key]: value }));
  }

  function comparisonLabel(key: 'screened' | 'interviews' | 'hired', fallback: string) {
    if (!dashboard || !comparison) return fallback;
    const before = comparison.totals[key];
    if (!before) return 'Период сравнения: 0';
    const change = Math.round(100 * (dashboard.totals[key] - before) / before);
    return (change > 0 ? '+' : '') + change + '% к выбранному сравнению';
  }

  const future = () => setNotice('Будет добавлено позже');

  function selectReportPeriod(preset: string) {
    if (preset === 'Неделя') return future();
    if (!reportVersion) return;
    setReportPreset(preset);
    if (preset === 'Свой период') return;
    setReportFrom(reportVersion.year + '-' + (preset === 'Месяц' ? '12' : preset === 'Квартал' ? '10' : '01'));
    setReportTo(reportVersion.year + '-12');
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setNotice('');
    try { await action(); }
    catch (failure) { setNotice(message(failure)); }
    finally { setBusy(false); }
  }

  async function prepareReport() {
    if (!reportVersion || !isMonth(reportFrom, reportVersion.year) || !isMonth(reportTo, reportVersion.year) || reportFrom > reportTo) {
      setNotice('Выберите месяцы в пределах года выбранного снимка.');
      return;
    }
    const query: ReportQuery = {
      start_month: Number(reportFrom.slice(-2)), end_month: Number(reportTo.slice(-2)),
      metrics, group_by: ['month'], compare_previous: false,
    };
    await run(async () => {
      const slice = await analyticsApi.report(reportVersion.snapshot_id, query);
      setPrepared({ version: reportVersion, from: reportFrom, to: reportTo, query, slice });
      setView('ready');
    });
  }

  function downloadLatestAnnual() {
    return run(async () => {
      const snapshot = versions[0];
      if (!snapshot) throw new Error('Доступных снимков годового доклада пока нет.');
      await analyticsApi.downloadAnnual(snapshot.snapshot_id);
    });
  }

  function downloadReady() {
    if (prepared) return run(() => analyticsApi.downloadReport(prepared.version.snapshot_id, prepared.query));
  }

  const counts = dashboard ? stages.map(([code, stage]) => ({
    stage, count: code === 'new' ? dashboard.totals.received : code === 'sent_to_department' ? dashboard.totals.forwarded
      : dashboard.stages.find((item) => item.code === code)?.count ?? 0,
  })) : [];
  const maxStage = Math.max(1, ...counts.map((item) => item.count));
  const funnelData = counts.map((item) => ({ ...item, width: percent(item.count, maxStage) }));
  const sources = dashboard?.sources ?? [];
  const maxSource = Math.max(1, ...sources.map((item) => item.count));
  const sourcesData = sources.map(({ channel, count }) => ({ source: channelNames[channel] || 'Другие источники', count, width: percent(count, maxSource) }));
  const rejections = dashboard?.rejections ?? [];
  const maxRejection = Math.max(1, ...rejections.map((item) => item.count));
  const rejectionData = rejections.map(({ code, title, count }) => ({ code, reason: title, count, width: percent(count, maxRejection) }));
  const weeks = dashboard?.weeks ?? [];
  const maxWeek = Math.max(1, ...weeks.flatMap(({ screened, interviews }) => [screened, interviews]));
  const weeklyData = weeks.map((week) => ({
    ...week, label: dayLabel.format(new Date(week.start)) + (week.start === week.end ? '' : '–' + dayLabel.format(new Date(week.end))),
    screenedHeight: percent(week.screened, maxWeek), interviewHeight: percent(week.interviews, maxWeek),
  }));
  const vacanciesSLA = (dashboard?.vacancies ?? []).map((row) => ({
    ...row, responses: row.received, interview: row.interviews,
    slaStatus: row.overdue ? 'Просрочено · ' + row.overdue : row.due_soon ? 'Срок подходит · ' + row.due_soon
      : row.waiting ? 'В срок · ' + row.waiting : 'Нет открытых передач',
    slaColor: row.overdue ? 'bg-[#FEE2E2] text-[#B91C1C]' : row.due_soon ? 'bg-[#FFF3D6] text-[#B45309]'
      : row.waiting ? 'bg-[#D7F0DD] text-[#15803D]' : 'bg-[#EEF1F5] text-[#4A5363]',
  }));
  const waiting = vacanciesSLA.reduce((sum, row) => sum + row.waiting, 0);
  const overdue = vacanciesSLA.reduce((sum, row) => sum + row.overdue, 0);
  const reportCards = [
    ['Отклики', 'applications_received'], ['Собеседования', 'phone_interviews_held'],
    ['Отклики с разговором', 'applications_with_phone_interview'], ['Принято', 'hired'],
  ].map(([label, key]) => {
    const metric = prepared?.slice.totals[key];
    return { label, value: metric?.value ?? '—', note: key === 'hired' ? 'Будет добавлено позже' : metric?.status === 'partial' ? 'Неполный охват' : 'По выбранному срезу' };
  });
  const months = prepared?.slice.rows ?? [];
  const maxMonth = Math.max(1, ...months.flatMap(({ metrics: row }) => [row.applications_received?.value ?? 0, row.phone_interviews_held?.value ?? 0]));
  const reportMonths = months.map(({ dimensions, metrics: row }) => {
    const rawMonth = String(dimensions.month ?? '');
    const month = /^\d{4}-\d{2}$/.test(rawMonth) ? rawMonth : prepared?.version.year + '-' + rawMonth.padStart(2, '0');
    return {
      label: /^\d{4}-(0[1-9]|1[0-2])$/.test(month) ? monthName(month) : rawMonth,
      screenedHeight: percent(row.applications_received?.value ?? 0, maxMonth), interviewHeight: percent(row.phone_interviews_held?.value ?? 0, maxMonth),
    };
  });


  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-6 space-y-6">
      {/* Quick Mockup Switcher for convenience (Экраны 21, 22, 23) */}
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
            Обзор
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

      {/* ======================================================== */}
      {/* МАКЕТ 21: ДАШБОРД ЗА ПЕРИОД (Аналитика_ дашборд.png)      */}
      {/* ======================================================== */}
      {view === 'dashboard' && (
        <>
          {/* Header & Filters Card */}
          <div data-tour="analytics-header" className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
              <div>
                <h1 className="text-[22px] font-bold text-[#141A24] tracking-tight mb-1">
                  Аналитика и отчёты
                </h1>
                <p className="text-[13px] text-[#616977]">
                  {dashboard ? 'Срез на ' + new Date(dashboard.as_of).toLocaleString('ru-RU') : 'Подбор по вакансиям'}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  title="Годовой доклад: фильтры сводки не применяются" onClick={() => void downloadLatestAnnual()} disabled={busy}
                  className="px-4 py-2 text-[13px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors whitespace-nowrap"
                >
                  Годовой XLSX
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
              <div className="inline-flex rounded-lg bg-[#F3F5F8] p-1">
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
                  <span className="text-[#616977]">Период</span>
                  <input type="date" aria-label="Начало периода" value={period.from} onChange={(event) => changePeriod('from', event.target.value)} className="px-3 py-1.5 border border-[#E1E5EB] rounded-lg bg-white text-[#141A24] text-[13px] focus:outline-none" />
                  <input type="date" aria-label="Конец периода" value={period.to} onChange={(event) => changePeriod('to', event.target.value)} className="px-3 py-1.5 border border-[#E1E5EB] rounded-lg bg-white text-[#141A24] text-[13px] focus:outline-none" />
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[#616977]">Сравнить с</span>
                  <select aria-label="Сравнить с" value={comparisonMode} onChange={(event) => setComparisonMode(event.target.value)} className="px-3 py-1.5 border border-[#E1E5EB] rounded-lg bg-white text-[#141A24] text-[13px] focus:outline-none">
                    <option value="previous">Предыдущий период</option><option value="year">Тот же период прошлого года</option><option value="">Без сравнения</option>
                  </select>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[#616977]">Вакансия</span>
                  <select aria-label="Вакансия" value={vacancy} onChange={(event) => setVacancy(event.target.value)} className="px-3 py-1.5 border border-[#E1E5EB] rounded-lg bg-white text-[#141A24] text-[13px] focus:outline-none">
                    <option value="">Все вакансии{vacancies.length > 0 ? ' (' + vacancies.length + ')' : ''}</option>
                    {vacancies.map((item) => <option key={item.vacancy_id} value={item.vacancy_id}>{item.title}</option>)}
                  </select>
                </div>
              </div>
            </div>
          </div>

          {invalidPeriod && <p role="alert" className="text-[13px] text-[#A3171B]">Выберите период от 1 до 366 календарных дней.</p>}
          {vacancyError && <p role="alert" className="text-[13px] text-[#A3171B]">{vacancyError} <button type="button" className="underline" onClick={() => setReload((value) => value + 1)}>Повторить загрузку вакансий</button></p>}
          {dataError && <p role="alert" className="text-[13px] text-[#A3171B]">{dataError} <button type="button" className="underline" onClick={() => setReload((value) => value + 1)}>Повторить</button></p>}
          {!dashboard && !invalidPeriod && !dataError && <p role="status" className="text-[13px] text-[#616977]">Загружаем данные…</p>}
          {comparisonError && <p role="status" className="text-[13px] text-[#616977]">Данные для сравнения недоступны.</p>}
          {/* 4 Summary Metric Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-5 shadow-sm">
              <div className="text-[12px] text-[#616977] mb-1">Разобрано откликов</div>
              <div className="text-[28px] font-bold text-[#141A24] mb-1">{dashboard?.totals.screened ?? '—'}</div>
              <div className="text-[12px] font-medium text-[#15803D]">
                {comparisonLabel('screened', 'Достигли первичного отбора')}
              </div>
            </div>

            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-5 shadow-sm">
              <div className="text-[12px] text-[#616977] mb-1">Первый ответ кандидату</div>
              <div className="text-[28px] font-bold text-[#141A24] mb-1">—</div>
              <div className="text-[12px] font-medium text-[#15803D]">
                Будет добавлено позже
              </div>
            </div>

            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-5 shadow-sm">
              <div className="text-[12px] text-[#616977] mb-1">Проведено собеседований</div>
              <div className="text-[28px] font-bold text-[#141A24] mb-1">{dashboard?.totals.interviews ?? '—'}</div>
              <div className="text-[12px] text-[#616977]">
                {comparisonLabel('interviews', 'По дате проведённого собеседования')}
              </div>
            </div>

            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-5 shadow-sm">
              <div className="text-[12px] text-[#616977] mb-1">Принято на работу</div>
              <div className="text-[28px] font-bold text-[#141A24] mb-1">{dashboard?.totals.hired ?? '—'}</div>
              <div className="text-[12px] text-[#616977]">
                {comparisonLabel('hired', 'По дате перехода на этап «Принят»')}
              </div>
            </div>
          </div>

          {/* AI Insight Highlight Card */}
          <div className="bg-[#FAF7FF] border border-[#E5DBFF] rounded-2xl p-5 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-[#6B21A8] font-bold text-[14px]">↗</span>
                <h2 className="text-[15px] font-bold text-[#141A24]">
                  Главное за период
                </h2>
              </div>
              <span className="text-[12px] text-[#6B21A8]">
                По данным за выбранный период
              </span>
            </div>
            <ul className="space-y-1.5 text-[13px] text-[#334155] leading-relaxed">
              {dashboard ? <>
                <li>• Поступило откликов: {dashboard.totals.received}. Проведено собеседований: {dashboard.totals.interviews}.</li>
                <li>• Направлено откликов: {dashboard.totals.forwarded}. Из передач за период сейчас ожидают ответа: {waiting}. Просрочено: {overdue}.</li>
                {rejectionData[0] && <li>• Наиболее частая причина отказа: {rejectionData[0].reason} ({rejectionData[0].count}).</li>}
              </> : <li>Сводка появится после загрузки данных.</li>}
            </ul>
          </div>

          {/* 2x2 Charts Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Chart 1: Воронка по моим вакансиям */}
            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
              <h2 className="text-[16px] font-bold text-[#141A24] mb-1">
                Воронка по моим вакансиям
              </h2>
              <p className="text-[12px] text-[#616977] mb-6">
                Сколько откликов достигло каждого этапа за период
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
                По каналу публикации вакансии и дате отклика
              </p>
              <div className="space-y-3">
                {dashboard && sourcesData.length === 0 && <p className="text-[13px] text-[#616977]">Откликов за период нет.</p>}
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
                Разобрано откликов и проведено собеседований
              </p>
              <div className="h-44 flex items-end justify-between gap-3 pt-6 border-b border-[#E1E5EB] px-2 overflow-x-auto">
                {weeklyData.map((w) => (
                  <div key={w.label} className="flex-1 min-w-[42px] flex flex-col items-center gap-2 h-full justify-end">
                    <div className="w-full flex items-end justify-center gap-1.5 h-full">
                      <div
                        className="w-4 bg-[#1F4FD1] rounded-t-sm transition-all duration-500"
                        style={{ height: w.screenedHeight }}
                        title={w.screened + ' откликов достигли первичного отбора'}
                      ></div>
                      <div
                        className="w-4 bg-[#7FA4FD] rounded-t-sm transition-all duration-500"
                        style={{ height: w.interviewHeight }}
                        title={w.interviews + ' проведённых собеседований'}
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
                  <span>Собеседования</span>
                </div>
              </div>
            </div>

            {/* Chart 4: Причины отказов */}
            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
              <h2 className="text-[16px] font-bold text-[#141A24] mb-1">
                Причины отказов
              </h2>
              <p className="text-[12px] text-[#616977] mb-6">
                {dashboard ? 'Отказов за период: ' + rejectionData.reduce((sum, item) => sum + item.count, 0) : 'За выбранный период'}
              </p>
              <div className="space-y-3">
                {dashboard && rejectionData.length === 0 && <p className="text-[13px] text-[#616977]">Отказов за период нет.</p>}
                {rejectionData.map((r) => (
                  <div key={r.code} className="flex items-center text-[13px]">
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
                Мои вакансии
              </h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[14px]">
                <thead className="bg-[#FAFBFD] border-b border-[#E1E5EB] text-[13px] text-[#616977]">
                  <tr>
                    <th className="py-3 px-6 font-medium whitespace-nowrap">Вакансия</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Откликов</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Собеседования</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Направлено</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Открыта, дней</th>
                    <th className="py-3 px-6 font-medium whitespace-nowrap" title="Текущее ожидание у передач, отправленных за выбранный период">Ответ департамента</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E1E5EB]">
                  {vacanciesSLA.map((v) => (
                    <tr key={v.id} className="hover:bg-[#F8FAFC]">
                      <td className="py-3.5 px-6 font-medium text-[#141A24] whitespace-nowrap">
                        {v.title}
                      </td>
                      <td className="py-3.5 px-4 text-[#4A5363] whitespace-nowrap">{v.responses}</td>
                      <td className="py-3.5 px-4 text-[#4A5363] whitespace-nowrap">{v.interview}</td>
                      <td className="py-3.5 px-4 text-[#4A5363] whitespace-nowrap">{v.forwarded}</td>
                      <td className="py-3.5 px-4 text-[#4A5363] whitespace-nowrap">{v.days_open ?? '—'}</td>
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


      {view === 'config' && (
        <div className="space-y-6">
          {/* Top back button */}
          <div>
            <button
              type="button"
              onClick={() => setView('dashboard')}
              className="text-[14px] font-medium text-[#1F4FD1] hover:underline flex items-center gap-1.5 transition-colors whitespace-nowrap"
            >
              ← Аналитика и отчёты
            </button>
          </div>

          <div>
            <h1 className="text-[24px] font-bold text-[#141A24] tracking-tight mb-1">
              Новый отчёт
            </h1>
            <p className="text-[14px] text-[#616977]">
              Выберите снимок годового доклада и месяцы для выгрузки XLSX.
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left Column (8 cols): Form Sections */}
            <div className="lg:col-span-8 bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm space-y-6">
              {/* Block 1: Период */}
              <div>
                <h2 className="text-[15px] font-bold text-[#141A24] mb-3">Период</h2>
                <div className="inline-flex rounded-lg bg-[#F3F5F8] p-1 mb-4">
                  {['Неделя', 'Месяц', 'Квартал', 'Год', 'Свой период'].map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => selectReportPeriod(p)} aria-pressed={reportPreset === p}
                      className={`px-3 py-1 text-[13px] font-medium rounded-md transition-all whitespace-nowrap ${
                        p === reportPreset
                          ? 'bg-white text-[#141A24] shadow-sm font-semibold'
                          : 'text-[#616977] hover:text-[#141A24]'
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-[13px]">
                  <div>
                    <label className="block text-[12px] text-[#616977] mb-1">С</label>
                    <input type="month" aria-label="Первый месяц отчёта" value={reportFrom} min={reportMin} max={reportMax}
                      onChange={(event) => { setReportFrom(event.target.value); setReportPreset('Свой период'); }} className="w-full px-3 py-2 border border-[#E1E5EB] rounded-lg bg-white text-[#141A24] focus:outline-none" />
                  </div>
                  <div>
                    <label className="block text-[12px] text-[#616977] mb-1">По</label>
                    <input type="month" aria-label="Последний месяц отчёта" value={reportTo} min={reportMin} max={reportMax}
                      onChange={(event) => { setReportTo(event.target.value); setReportPreset('Свой период'); }} className="w-full px-3 py-2 border border-[#E1E5EB] rounded-lg bg-white text-[#141A24] focus:outline-none" />
                  </div>
                  <div>
                    <label className="block text-[12px] text-[#616977] mb-1" htmlFor="dashboard-snapshot">Версия доклада</label>
                    <select id="dashboard-snapshot" value={reportId} onChange={(event) => setReportId(event.target.value)} className="w-full px-3 py-2 border border-[#E1E5EB] rounded-lg bg-white text-[#141A24] focus:outline-none">
                      <option value="">Выберите снимок</option>
                      {versions.map((version) => <option key={version.snapshot_id} value={version.snapshot_id}>{version.year} · {version.extracted_at.slice(0,10)}</option>)}
                    </select>
                  </div>
                </div>
              </div>

              {/* Block 2: Разделы отчёта */}
              <div className="pt-2 border-t border-[#F0F2F5]">
                <h2 className="text-[15px] font-bold text-[#141A24] mb-3">Разделы отчёта</h2>
                <div className="space-y-2.5 text-[13px] text-[#334155]">
                  {[
                    { label: 'Ключевые показатели', defaultChecked: true },
                    { label: 'Сводка ИИ: главное за период', defaultChecked: false },
                    { label: 'Воронка подбора', defaultChecked: false },
                    { label: 'Динамика по месяцам', defaultChecked: true },
                    { label: 'Источники откликов', defaultChecked: false },
                    { label: 'Причины отказов', defaultChecked: false },
                    { label: 'Сроки ответов департаментов', defaultChecked: false },
                    { label: 'Список кандидатов с ФИО (только для внутреннего пользования)', defaultChecked: false },
                  ].map((item) => (
                    <label key={item.label} className="flex items-center gap-2.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={item.defaultChecked} onChange={() => item.defaultChecked ? setNotice('Этот раздел входит в выгрузку XLSX') : future()}
                        className="w-4 h-4 rounded text-[#1F4FD1] focus:ring-[#1F4FD1] cursor-pointer"
                      />
                      <span>{item.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Block 3: Формат */}
              <div className="pt-2 border-t border-[#F0F2F5]">
                <h2 className="text-[15px] font-bold text-[#141A24] mb-3">Формат</h2>
                <div className="flex items-center gap-2">
                  {(['PDF', 'Excel', 'Презентация'] as const).map((fmt) => (
                    <button
                      key={fmt}
                      type="button"
                      onClick={() => { if (fmt !== 'Excel') future(); }}
                      className={`px-4 py-2 rounded-lg text-[13px] font-medium transition-all ${
                        fmt === 'Excel'
                          ? 'border-2 border-[#1F4FD1] text-[#1F4FD1] bg-[#F8FAFF]'
                          : 'border border-[#E1E5EB] text-[#4A5363] hover:bg-gray-50'
                      }`}
                    >
                      {fmt}
                    </button>
                  ))}
                </div>
              </div>

              {/* Actions */}
              <div className="pt-4 border-t border-[#F0F2F5] flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => void prepareReport()} disabled={busy || !reportVersion}
                  className="px-5 py-2.5 text-[14px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm whitespace-nowrap"
                >
                  Сформировать
                </button>
                <button
                  type="button"
                  onClick={() => setView('dashboard')}
                  className="px-5 py-2.5 text-[14px] font-medium text-[#4A5363] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors whitespace-nowrap"
                >
                  Отмена
                </button>
              </div>
            </div>

            {/* Right Column (4 cols): Кому отправить & Автоотчёт */}
            <div className="lg:col-span-4 space-y-6">
              <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm space-y-4">
                <h2 className="text-[16px] font-bold text-[#141A24]">
                  Кому отправить
                </h2>
                <div>
                  <label className="block text-[12px] font-medium text-[#4A5363] mb-1">
                    Получатели
                  </label>
                  <input
                    type="text"
                    readOnly placeholder="Будет добавлено позже" onClick={future}
                    className="w-full px-3.5 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24] focus:outline-none focus:border-[#1F4FD1]"
                  />
                </div>
                <label className="flex items-center gap-2 cursor-pointer text-[13px] text-[#4A5363]">
                  <input
                    type="checkbox"
                    checked={false} onChange={future} className="w-4 h-4 rounded text-[#1F4FD1] focus:ring-[#1F4FD1]"
                  />
                  <span>Отправить копию мне</span>
                </label>
              </div>

              <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm space-y-3">
                <h2 className="text-[16px] font-bold text-[#141A24]">Автоотчёт</h2>
                <p className="text-[13px] text-[#616977]">
                  Расписание отправки отчётов будет добавлено позже.
                </p>
                <div className="space-y-2 pt-1 text-[13px] text-[#4A5363]">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={false} onChange={future} className="w-4 h-4 rounded text-[#1F4FD1] focus:ring-[#1F4FD1]"
                    />
                    <span>Присылать каждый понедельник в 9:00</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox" checked={false} onChange={future} className="w-4 h-4 rounded text-[#1F4FD1] focus:ring-[#1F4FD1]"
                    />
                    <span>Присылать в конце месяца</span>
                  </label>
                </div>
              </div>

              <div className="bg-[#EFF6FF] border border-[#BFDBFE] rounded-2xl p-5 text-[13px] space-y-1">
                <div className="font-bold text-[#1E40AF]">Без лишних персональных данных</div>
                <div className="text-[#1E3A8A] leading-relaxed">
                  В текущей выгрузке только агрегированные показатели.
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* МАКЕТ 23: ОТЧЁТ ГОТОВ (Отчёт_ готов.png)                  */}
      {/* ======================================================== */}
      {view === 'ready' && (
        <div className="space-y-6">
          {/* Top Green Notification Banner */}
          <div className={prepared ? "bg-[#EBF7EE] border border-[#C6E7D2] rounded-2xl p-5 text-[#14532D]" : "bg-white border border-[#E1E5EB] rounded-2xl p-5 text-[#4A5363]"}>
            <h2 className="text-[15px] font-bold text-[#166534] mb-0.5">
              {prepared ? 'Отчёт готов' : 'Отчёт ещё не сформирован'}
            </h2>
            <p className="text-[13px]">
              {prepared ? 'Проверьте показатели и скачайте XLSX.' : 'Выберите параметры на вкладке «Настройка отчёта».'}
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left Column (8 cols): Report Sheet Preview */}
            <div className="lg:col-span-8 bg-white border border-[#E1E5EB] rounded-2xl p-6 lg:p-8 shadow-sm space-y-6">
              {/* Report Header */}
              <div className="flex items-start justify-between border-b border-[#E1E5EB] pb-5">
                <div>
                  <h1 className="text-[22px] font-bold text-[#141A24] tracking-tight mb-1">
                    Отчёт по подбору персонала
                  </h1>
                  <p className="text-[13px] text-[#616977]">
                    {prepared ? monthName(prepared.from) + ' – ' + monthName(prepared.to) + ' · ' + prepared.version.year : 'По выбранному снимку годового доклада'}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <img src="/images/Header/Mark.svg" alt="GorkyCode" className="w-6 h-6" />
                  <span className="text-[13px] font-bold text-[#141A24]">GorkyCode · команда 9</span>
                </div>
              </div>

              {/* 4 Mini KPI Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {reportCards.map((item) => <div key={item.label} className="bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl p-3.5">
                  <div className="text-[11px] text-[#616977]">{item.label}</div>
                  <div className="text-[22px] font-bold text-[#141A24]">{item.value}</div>
                  <div className="text-[11px] text-[#616977]">{item.note}</div>
                </div>)}
              </div>

              {/* Главное */}
              <div className="space-y-1.5 text-[13px] text-[#334155] leading-relaxed">
                <h3 className="font-bold text-[#141A24]">Главное</h3>
                <p>
                  {prepared ? 'На экране и в файле один срез годового доклада: отклики и телефонные разговоры.' : 'Данные появятся после формирования отчёта.'}
                </p>
              </div>

              {/* Динамика по неделям */}
              <div>
                <h3 className="text-[13px] font-bold text-[#141A24] mb-3">Динамика по месяцам</h3>
                <div className="h-28 flex items-end justify-between gap-3 pt-2 border-b border-[#E1E5EB] px-2">
                  {reportMonths.map((w) => (
                    <div key={w.label} className="flex-1 flex flex-col items-center gap-1.5 h-full justify-end">
                      <div className="w-full flex items-end justify-center gap-1.5 h-full">
                        <div className="w-3.5 bg-[#1F4FD1] rounded-t-sm" style={{ height: w.screenedHeight }}></div>
                        <div className="w-3.5 bg-[#7FA4FD] rounded-t-sm" style={{ height: w.interviewHeight }}></div>
                      </div>
                      <span className="text-[10px] text-[#616977] whitespace-nowrap">{w.label}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Причины отказов + Источники */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-[12px]">
                <div>
                  <h4 className="font-bold text-[#141A24] mb-2">Причины отказов</h4>
                  <p className="text-[#616977]">Будет добавлено позже</p>
                </div>

                <div>
                  <h4 className="font-bold text-[#141A24] mb-2">Источники</h4>
                  <p className="text-[#616977]">Будет добавлено позже</p>
                </div>
              </div>

              <div className="text-[11px] text-[#8E939D] pt-2 border-t border-[#E1E5EB]">
                {prepared ? 'Срез годового доклада' : 'Предварительный просмотр'}
              </div>
            </div>

            {/* Right Column (4 cols): Actions & Past Reports */}
            <div className="lg:col-span-4 space-y-6">
              <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm space-y-3">
                <h2 className="text-[16px] font-bold text-[#141A24]">Скачать</h2>
                <button
                  type="button"
                  onClick={future}
                  className="w-full py-2.5 px-4 text-[14px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm text-center"
                >
                  Скачать PDF
                </button>
                <button
                  type="button"
                  onClick={() => void downloadReady()} disabled={!prepared || busy}
                  className="w-full py-2.5 px-4 text-[14px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors text-center"
                >
                  Скачать Excel
                </button>
                <button
                  type="button"
                  onClick={future}
                  className="w-full py-2.5 px-4 text-[14px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors text-center"
                >
                  Скачать презентацию
                </button>
              </div>

              <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm space-y-3">
                <h2 className="text-[16px] font-bold text-[#141A24]">Отправить ещё</h2>
                <div>
                  <label className="block text-[12px] font-medium text-[#4A5363] mb-1">
                    Кому
                  </label>
                  <input
                    type="text"
                    readOnly placeholder="Будет добавлено позже" onClick={future}
                    className="w-full px-3.5 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24] focus:outline-none focus:border-[#1F4FD1]"
                  />
                </div>
                <button
                  type="button"
                  onClick={future}
                  className="w-full py-2 text-[13px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors text-center"
                >
                  Отправить
                </button>
              </div>

              <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm space-y-3">
                <h2 className="text-[16px] font-bold text-[#141A24]">Мои отчёты</h2>
                <div className="space-y-3 text-[13px]">
                  {versions.map((version) => <div key={version.snapshot_id} className="flex items-center justify-between">
                    <div><div className="font-medium text-[#141A24]">Годовой доклад · {version.year}</div><div className="text-[11px] text-[#616977]">XLSX · {version.extracted_at.slice(0,10)}</div></div>
                    <button type="button" onClick={() => void run(() => analyticsApi.downloadAnnual(version.snapshot_id))}
                      className="text-[#1F4FD1] hover:underline font-medium text-[12px]">Скачать</button>
                  </div>)}
                  {versions.length === 0 && <p className="text-[#616977]">Доступных снимков пока нет.</p>}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {notice && (
        <div className="fixed bottom-6 right-6 bg-[#141A24] text-white text-[13px] px-4 py-2.5 rounded-lg shadow-lg z-50 animate-fade-in flex items-center gap-2">
          <span role="status">{notice}</span><button type="button" aria-label="Закрыть уведомление" onClick={() => setNotice('')}>×</button>
        </div>
      )}
    </div>
  );
}

