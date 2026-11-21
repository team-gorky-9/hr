import React, { useState } from 'react';

export type AnalyticsView = 'dashboard' | 'config' | 'ready';

export const AnalyticsDashboard: React.FC = () => {
  const [view, setView] = useState<AnalyticsView>('dashboard');
  const [activePeriod, setActivePeriod] = useState<string>('Месяц');
  const [configPeriod, setConfigPeriod] = useState<string>('Свой период');
  const [reportFormat, setReportFormat] = useState<'PDF' | 'Excel' | 'Презентация'>('PDF');
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const periodOptions = ['Неделя', 'Месяц', 'Квартал', 'Год', 'Свой период'];

  // Funnel Data (Horizontal blue bars)
  const funnelData = [
    { stage: 'Получено', count: 64, width: '92%' },
    { stage: 'Разобрано', count: 58, width: '83%' },
    { stage: 'Телефонное интервью', count: 34, width: '49%' },
    { stage: 'Направлено в департамент', count: 14, width: '20%' },
    { stage: 'Очное собеседование', count: 8, width: '12%' },
    { stage: 'Принято', count: 3, width: '5%' },
  ];

  // Sources Data (Horizontal lighter blue bars)
  const sourcesData = [
    { source: 'HH.ru', count: 29, width: '85%' },
    { source: '«Работа России»', count: 14, width: '42%' },
    { source: 'Сайт администрац', count: 11, width: '33%' },
    { source: 'Почта', count: 6, width: '18%' },
    { source: 'Студенты', count: 4, width: '12%' },
  ];

  // Weekly Dynamics Data (Vertical grouped bars)
  const weeklyData = [
    { label: '21–27 окт', screenedHeight: '52%', interviewHeight: '40%' },
    { label: '28 окт–3 ноя', screenedHeight: '70%', interviewHeight: '48%' },
    { label: '4–10 ноя', screenedHeight: '92%', interviewHeight: '68%' },
    { label: '11–17 ноя', screenedHeight: '88%', interviewHeight: '68%' },
    { label: '18–20 ноя', screenedHeight: '60%', interviewHeight: '42%' },
  ];

  // Reasons for Rejection Data (Horizontal rust-red bars)
  const rejectionData = [
    { reason: 'Не хватает опыта', count: 9, width: '75%' },
    { reason: 'Другая специализаци', count: 5, width: '42%' },
    { reason: 'Не прошёл интервью', count: 4, width: '33%' },
    { reason: 'Отказался сам', count: 3, width: '25%' },
  ];

  // Vacancy SLA Data
  const vacanciesSLA = [
    {
      title: 'Python-разработчик',
      responses: 24,
      interview: 14,
      forwarded: 6,
      daysOpen: 18,
      slaStatus: 'В срок · 2 дн.',
      slaColor: 'bg-[#D7F0DD] text-[#15803D]',
    },
    {
      title: 'Аналитик данных',
      responses: 19,
      interview: 10,
      forwarded: 4,
      daysOpen: 25,
      slaStatus: 'Срок подходит · 4 дн.',
      slaColor: 'bg-[#FFF3D6] text-[#B45309]',
    },
    {
      title: 'Инженер ПТО',
      responses: 15,
      interview: 7,
      forwarded: 3,
      daysOpen: 32,
      slaStatus: 'Просрочено · 6 дн.',
      slaColor: 'bg-[#FEE2E2] text-[#B91C1C]',
    },
    {
      title: 'Главный специалист по обращениям',
      responses: 6,
      interview: 3,
      forwarded: 1,
      daysOpen: 9,
      slaStatus: 'В срок · 1 дн.',
      slaColor: 'bg-[#D7F0DD] text-[#15803D]',
    },
  ];

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

      {/* ======================================================== */}
      {/* МАКЕТ 21: ДАШБОРД ЗА ПЕРИОД (Аналитика_ дашборд.png)      */}
      {/* ======================================================== */}
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
                  Мои вакансии и кандидаты · Марина С.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => showToast('Формирование файла Excel...')}
                  className="px-4 py-2 text-[13px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors whitespace-nowrap"
                >
                  Скачать Excel
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
                    onClick={() => setActivePeriod(p)}
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
                  <input
                    type="text"
                    defaultValue="21.10.2026 – 20.11.2026"
                    className="px-3 py-1.5 border border-[#E1E5EB] rounded-lg bg-white text-[#141A24] text-[13px] focus:outline-none"
                  />
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[#616977]">Сравнить с</span>
                  <select className="px-3 py-1.5 border border-[#E1E5EB] rounded-lg bg-white text-[#141A24] text-[13px] focus:outline-none">
                    <option>Предыдущий месяц</option>
                    <option>Тот же период прошлого года</option>
                  </select>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[#616977]">Вакансия</span>
                  <select className="px-3 py-1.5 border border-[#E1E5EB] rounded-lg bg-white text-[#141A24] text-[13px] focus:outline-none">
                    <option>Все вакансии (4)</option>
                    <option>Python-разработчик</option>
                    <option>Аналитик данных</option>
                    <option>Инженер ПТО</option>
                  </select>
                </div>
              </div>
            </div>
          </div>

          {/* 4 Summary Metric Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-5 shadow-sm">
              <div className="text-[12px] text-[#616977] mb-1">Разобрано откликов</div>
              <div className="text-[28px] font-bold text-[#141A24] mb-1">58</div>
              <div className="text-[12px] font-medium text-[#15803D]">
                +12% к прошлому месяцу
              </div>
            </div>

            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-5 shadow-sm">
              <div className="text-[12px] text-[#616977] mb-1">Первый ответ кандидату</div>
              <div className="text-[28px] font-bold text-[#141A24] mb-1">1,6 дн.</div>
              <div className="text-[12px] font-medium text-[#15803D]">
                быстрее на 0,8 дн.
              </div>
            </div>

            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-5 shadow-sm">
              <div className="text-[12px] text-[#616977] mb-1">Проведено интервью</div>
              <div className="text-[28px] font-bold text-[#141A24] mb-1">34</div>
              <div className="text-[12px] text-[#616977]">
                в среднем 24 мин
              </div>
            </div>

            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-5 shadow-sm">
              <div className="text-[12px] text-[#616977] mb-1">Принято на работу</div>
              <div className="text-[28px] font-bold text-[#141A24] mb-1">3</div>
              <div className="text-[12px] text-[#616977]">
                ещё 2 — на очном этапе
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
                Сводка ИИ, проверьте цифры
              </span>
            </div>
            <ul className="space-y-1.5 text-[13px] text-[#334155] leading-relaxed">
              <li>• Откликов стало больше на 12%, в основном с HH.ru. Доля дошедших до интервью держится около 59%.</li>
              <li>• Узкое место — ответы департамента строительства: 3 из 5 кандидатов ждут дольше 3 дней.</li>
              <li>• Самая частая причина отказа — нехватка опыта (9 из 21). Стоит смягчить требования к стажёрам или звать их в студенческий резерв.</li>
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
                Сколько кандидатов прошло каждый этап
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
                Откуда пришли отклики
              </p>
              <div className="space-y-3">
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
                Разобрано откликов и проведено интервью
              </p>
              <div className="h-44 flex items-end justify-between gap-3 pt-6 border-b border-[#E1E5EB] px-2">
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
                21 отказ за период
              </p>
              <div className="space-y-3">
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
                Мои вакансии
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
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Открыта, дней</th>
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
                      <td className="py-3.5 px-4 text-[#4A5363] whitespace-nowrap">{v.daysOpen}</td>
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

      {/* ======================================================== */}
      {/* МАКЕТ 22: НАСТРОЙКА ОТЧЁТА (Отчёт_ настройка.png)        */}
      {/* ======================================================== */}
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
              Выберите период и разделы. Отчёт соберётся автоматически из данных системы.
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
                      onClick={() => setConfigPeriod(p)}
                      className={`px-3 py-1 text-[13px] font-medium rounded-md transition-all whitespace-nowrap ${
                        configPeriod === p
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
                    <input
                      type="text"
                      defaultValue="01.10.2026"
                      className="w-full px-3 py-2 border border-[#E1E5EB] rounded-lg bg-white text-[#141A24] focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-[12px] text-[#616977] mb-1">По</label>
                    <input
                      type="text"
                      defaultValue="20.11.2026"
                      className="w-full px-3 py-2 border border-[#E1E5EB] rounded-lg bg-white text-[#141A24] focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-[12px] text-[#616977] mb-1">Сравнить с</label>
                    <input
                      type="text"
                      defaultValue="Тот же период прошлого года"
                      className="w-full px-3 py-2 border border-[#E1E5EB] rounded-lg bg-white text-[#141A24] focus:outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Block 2: Разделы отчёта */}
              <div className="pt-2 border-t border-[#F0F2F5]">
                <h2 className="text-[15px] font-bold text-[#141A24] mb-3">Разделы отчёта</h2>
                <div className="space-y-2.5 text-[13px] text-[#334155]">
                  {[
                    { label: 'Ключевые показатели', defaultChecked: true },
                    { label: 'Сводка ИИ: главное за период', defaultChecked: true },
                    { label: 'Воронка подбора', defaultChecked: true },
                    { label: 'Динамика по неделям', defaultChecked: true },
                    { label: 'Источники откликов', defaultChecked: true },
                    { label: 'Причины отказов', defaultChecked: true },
                    { label: 'Сроки ответов департаментов', defaultChecked: false },
                    { label: 'Список кандидатов с ФИО (только для внутреннего пользования)', defaultChecked: false },
                  ].map((item) => (
                    <label key={item.label} className="flex items-center gap-2.5 cursor-pointer">
                      <input
                        type="checkbox"
                        defaultChecked={item.defaultChecked}
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
                      onClick={() => setReportFormat(fmt)}
                      className={`px-4 py-2 rounded-lg text-[13px] font-medium transition-all ${
                        reportFormat === fmt
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
                  onClick={() => {
                    setView('ready');
                    showToast('Отчёт успешно сформирован и отправлен');
                  }}
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
                    defaultValue="Ирина Б., начальник отдела кадров"
                    className="w-full px-3.5 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24] focus:outline-none focus:border-[#1F4FD1]"
                  />
                </div>
                <label className="flex items-center gap-2 cursor-pointer text-[13px] text-[#4A5363]">
                  <input
                    type="checkbox"
                    defaultChecked
                    className="w-4 h-4 rounded text-[#1F4FD1] focus:ring-[#1F4FD1]"
                  />
                  <span>Отправить копию мне</span>
                </label>
              </div>

              <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm space-y-3">
                <h2 className="text-[16px] font-bold text-[#141A24]">Автоотчёт</h2>
                <p className="text-[13px] text-[#616977]">
                  Система сама соберёт отчёт и пришлёт его на почту
                </p>
                <div className="space-y-2 pt-1 text-[13px] text-[#4A5363]">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      defaultChecked
                      className="w-4 h-4 rounded text-[#1F4FD1] focus:ring-[#1F4FD1]"
                    />
                    <span>Присылать каждый понедельник в 9:00</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      className="w-4 h-4 rounded text-[#1F4FD1] focus:ring-[#1F4FD1]"
                    />
                    <span>Присылать в конце месяца</span>
                  </label>
                </div>
              </div>

              <div className="bg-[#EFF6FF] border border-[#BFDBFE] rounded-2xl p-5 text-[13px] space-y-1">
                <div className="font-bold text-[#1E40AF]">Без лишних персональных данных</div>
                <div className="text-[#1E3A8A] leading-relaxed">
                  По умолчанию в отчёте только цифры. ФИО кандидатов добавляются, только если вы отметите это явно.
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
          <div className="bg-[#EBF7EE] border border-[#C6E7D2] rounded-2xl p-5 text-[#14532D]">
            <h2 className="text-[15px] font-bold text-[#166534] mb-0.5">
              Отчёт готов и отправлен
            </h2>
            <p className="text-[13px]">
              Ирина Б. получила его на почту 20.11 в 14:02. Копия — у вас в разделе «Отчёты».
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
                    01.10.2026 – 20.11.2026 · сравнение с тем же периодом 2025 года
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <img src="/images/Header/Mark.svg" alt="GorkyCode" className="w-6 h-6" />
                  <span className="text-[13px] font-bold text-[#141A24]">GorkyCode - team 9</span>
                </div>
              </div>

              {/* 4 Mini KPI Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl p-3.5">
                  <div className="text-[11px] text-[#616977]">Разобрано</div>
                  <div className="text-[22px] font-bold text-[#141A24]">92</div>
                  <div className="text-[11px] font-medium text-[#15803D]">+18%</div>
                </div>
                <div className="bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl p-3.5">
                  <div className="text-[11px] text-[#616977]">Интервью</div>
                  <div className="text-[22px] font-bold text-[#141A24]">53</div>
                  <div className="text-[11px] font-medium text-[#15803D]">+11%</div>
                </div>
                <div className="bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl p-3.5">
                  <div className="text-[11px] text-[#616977]">Направлено</div>
                  <div className="text-[22px] font-bold text-[#141A24]">21</div>
                  <div className="text-[11px] font-medium text-[#15803D]">+5%</div>
                </div>
                <div className="bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl p-3.5">
                  <div className="text-[11px] text-[#616977]">Принято</div>
                  <div className="text-[22px] font-bold text-[#141A24]">5</div>
                  <div className="text-[11px] font-medium text-[#15803D]">+2 чел.</div>
                </div>
              </div>

              {/* Главное */}
              <div className="space-y-1.5 text-[13px] text-[#334155] leading-relaxed">
                <h3 className="font-bold text-[#141A24]">Главное</h3>
                <p>
                  Подбор ускорился: первый ответ кандидату — 1,6 дня вместо 2,4. Узкое место — департамент строительства: средний ответ 5,2 дня при норме 3.
                </p>
                <p>
                  Рекомендация: договориться с департаментом о сроке ответа и подключить напоминания руководителю.
                </p>
              </div>

              {/* Динамика по неделям */}
              <div>
                <h3 className="text-[13px] font-bold text-[#141A24] mb-3">Динамика по неделям</h3>
                <div className="h-28 flex items-end justify-between gap-3 pt-2 border-b border-[#E1E5EB] px-2">
                  {weeklyData.map((w) => (
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
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[#616977]">Не хватает опыта</span>
                      <span className="font-bold">14</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-[#616977]">Другая специализация</span>
                      <span className="font-bold">8</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-[#616977]">Не прошёл интервью</span>
                      <span className="font-bold">6</span>
                    </div>
                  </div>
                </div>

                <div>
                  <h4 className="font-bold text-[#141A24] mb-2">Источники</h4>
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[#616977]">HH.ru</span>
                      <span className="font-bold">41</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-[#616977]">«Работа России»</span>
                      <span className="font-bold">22</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-[#616977]">Сайт</span>
                      <span className="font-bold">17</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="text-[11px] text-[#8E939D] pt-2 border-t border-[#E1E5EB]">
                стр. 1 из 3
              </div>
            </div>

            {/* Right Column (4 cols): Actions & Past Reports */}
            <div className="lg:col-span-4 space-y-6">
              <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm space-y-3">
                <h2 className="text-[16px] font-bold text-[#141A24]">Скачать</h2>
                <button
                  type="button"
                  onClick={() => showToast('Загрузка PDF...')}
                  className="w-full py-2.5 px-4 text-[14px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm text-center"
                >
                  Скачать PDF
                </button>
                <button
                  type="button"
                  onClick={() => showToast('Загрузка Excel...')}
                  className="w-full py-2.5 px-4 text-[14px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors text-center"
                >
                  Скачать Excel
                </button>
                <button
                  type="button"
                  onClick={() => showToast('Загрузка презентации...')}
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
                    defaultValue="Директор департамента кадров"
                    className="w-full px-3.5 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24] focus:outline-none focus:border-[#1F4FD1]"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => showToast('Отчёт отправлен директору департамента кадров')}
                  className="w-full py-2 text-[13px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors text-center"
                >
                  Отправить
                </button>
              </div>

              <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm space-y-3">
                <h2 className="text-[16px] font-bold text-[#141A24]">Мои отчёты</h2>
                <div className="space-y-3 text-[13px]">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium text-[#141A24]">Октябрь 2026</div>
                      <div className="text-[11px] text-[#616977]">PDF · 05.11</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => showToast('Открытие отчёта за Октябрь 2026')}
                      className="text-[#1F4FD1] hover:underline font-medium text-[12px]"
                    >
                      Открыть
                    </button>
                  </div>

                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium text-[#141A24]">Сентябрь 2026</div>
                      <div className="text-[11px] text-[#616977]">PDF · 03.10</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => showToast('Открытие отчёта за Сентябрь 2026')}
                      className="text-[#1F4FD1] hover:underline font-medium text-[12px]"
                    >
                      Открыть
                    </button>
                  </div>

                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium text-[#141A24]">III квартал 2026</div>
                      <div className="text-[11px] text-[#616977]">Презентация · 02.10</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => showToast('Открытие отчёта за III квартал 2026')}
                      className="text-[#1F4FD1] hover:underline font-medium text-[12px]"
                    >
                      Открыть
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 bg-[#141A24] text-white text-[13px] px-4 py-2.5 rounded-lg shadow-lg z-50 animate-fade-in flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[#15803D]"></span>
          {toastMessage}
        </div>
      )}
    </div>
  );
};

export default AnalyticsDashboard;
