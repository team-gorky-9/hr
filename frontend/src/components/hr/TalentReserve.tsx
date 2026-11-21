import React, { useState } from 'react';

export type ReserveSubTab = 'municipal' | 'students';

interface TalentReserveProps {
  initialSubTab?: ReserveSubTab;
  onOfferVacancy?: (candidateName: string) => void;
}

export const TalentReserve: React.FC<TalentReserveProps> = ({
  initialSubTab = 'municipal',
  onOfferVacancy,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<ReserveSubTab>(initialSubTab);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const participants = [
    {
      name: 'Тихонов Роман',
      targetRole: 'Начальник отдела цифровизации',
      problemScore: 9,
      projectScore: 8,
      presScore: 9,
      verdict: 'Рекомендован',
      verdictColor: 'bg-[#E6F4EA] text-[#15803D]',
    },
    {
      name: 'Фёдорова Елена',
      targetRole: 'Заместитель директора департамента экономики',
      problemScore: 7,
      projectScore: 7,
      presScore: 6,
      verdict: 'Ждёт решения',
      verdictColor: 'bg-[#FEF3E6] text-[#B45309]',
    },
    {
      name: 'Гусев Николай',
      targetRole: 'Начальник отдела благоустройства',
      problemScore: 5,
      projectScore: 4,
      presScore: 6,
      verdict: 'Не рекомендован',
      verdictColor: 'bg-[#FDE8E8] text-[#C5221F]',
    },
  ];

  const reservists = [
    {
      name: 'Павлова Ирина',
      targetRole: 'Заместитель начальника отдела кадров',
      readiness: 'Готов сейчас',
      since: '03.2025',
      status: 'Актуально',
      statusColor: 'bg-[#E6F4EA] text-[#15803D]',
    },
    {
      name: 'Семёнов Максим',
      targetRole: 'Начальник финансового отдела',
      readiness: 'Через 1 год',
      since: '09.2024',
      status: 'Подтвердить интерес',
      statusColor: 'bg-[#FEF3E6] text-[#B45309]',
    },
    {
      name: 'Волков Андрей',
      targetRole: 'Директор департамента строительства',
      readiness: 'Через 1 год',
      since: '11.2023',
      status: 'Устарело: больше 2 лет',
      statusColor: 'bg-[#FDE8E8] text-[#C5221F]',
    },
    {
      name: 'Тихонов Роман',
      targetRole: 'Начальник отдела цифровизации',
      readiness: 'Готов сейчас',
      since: '11.2026',
      status: 'Направлен в департамент',
      statusColor: 'text-[#4A5363]',
      isPlain: true,
    },
  ];

  const students = [
    {
      name: 'Никитина Полина',
      uniBadge: 'ННГУ, 4 курс',
      practiceDept: 'Практика: Правовое управление, 2 месяца',
      quote:
        '«Готовила проекты ответов на обращения быстро и без ошибок. Взял бы в штат.» — руководитель практики',
      skills: ['Работа с обращениями', 'Нормативные акты'],
    },
    {
      name: 'Воронов Кирилл',
      uniBadge: 'ВШЭ НН, 3 курс',
      practiceDept: 'Практика: Департамент цифрового развития',
      quote:
        '«Собрал дашборд по обращениям жителей, им пользуется весь отдел.» — руководитель практики',
      skills: ['Power BI', 'SQL'],
    },
    {
      name: 'Данилов Егор',
      uniBadge: 'ННГАСУ, 4 курс',
      practiceDept: 'Практика: Департамент строительства',
      quote:
        '«Аккуратно вёл проектную документацию, инициативен.» — руководитель практики',
      skills: ['Проектная документация', 'AutoCAD'],
    },
  ];

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-6 space-y-6">
      {/* Title & Subtitle */}
      <div>
        <h1 className="text-[26px] font-bold text-[#141A24] tracking-tight mb-1">
          Кадровый резерв
        </h1>
        <p className="text-[14px] text-[#616977]">
          Муниципальный резерв формируется по конкурсу с защитой проекта. Студенческий — по итогам практики.
        </p>
      </div>

      {/* Two Sub-tabs (Муниципальный резерв / Студенческий резерв) */}
      <div className="flex items-center gap-6 border-b border-[#E1E5EB]">
        <button
          type="button"
          onClick={() => setActiveSubTab('municipal')}
          className={`pb-3 text-[15px] font-medium transition-all relative ${
            activeSubTab === 'municipal'
              ? 'text-[#1F4FD1] font-semibold border-b-2 border-[#1F4FD1]'
              : 'text-[#616977] hover:text-[#141A24]'
          }`}
        >
          Муниципальный резерв
        </button>
        <button
          type="button"
          onClick={() => setActiveSubTab('students')}
          className={`pb-3 text-[15px] font-medium transition-all relative ${
            activeSubTab === 'students'
              ? 'text-[#1F4FD1] font-semibold border-b-2 border-[#1F4FD1]'
              : 'text-[#616977] hover:text-[#141A24]'
          }`}
        >
          Студенческий резерв
        </button>
      </div>

      {/* ======================================================== */}
      {/* МАКЕТ 24: МУНИЦИПАЛЬНЫЙ РЕЗЕРВ (Кадровый резерв_ конкурс)*/}
      {/* ======================================================== */}
      {activeSubTab === 'municipal' && (
        <div className="space-y-6">
          {/* Card 1: Конкурс в кадровый резерв 2026 */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <h2 className="text-[18px] font-bold text-[#141A24]">
                Конкурс в кадровый резерв 2026
              </h2>
              <span className="bg-[#FEF3E6] text-[#B45309] px-3 py-1 rounded-full text-[12px] font-medium whitespace-nowrap self-start sm:self-auto">
                Идёт этап: защита проектов
              </span>
            </div>

            {/* Stepper with progress bars */}
            <div className="space-y-2 pt-1">
              <div className="grid grid-cols-5 gap-2">
                <div className="h-1.5 rounded-full bg-[#15803D]"></div>
                <div className="h-1.5 rounded-full bg-[#15803D]"></div>
                <div className="h-1.5 rounded-full bg-[#15803D]"></div>
                <div className="h-1.5 rounded-full bg-[#D97706]"></div>
                <div className="h-1.5 rounded-full bg-[#E5E7EB]"></div>
              </div>
              <div className="grid grid-cols-5 gap-2 text-[12px] text-[#4A5363] leading-snug">
                <div>Приём заявок</div>
                <div>Проверка документов</div>
                <div>Подготовка проекта</div>
                <div className="font-semibold text-[#141A24]">Защита перед комиссией</div>
                <div className="text-[#8E939D]">Решение комиссии</div>
              </div>
            </div>

            {/* Details Box: 3 columns */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl p-5 text-[13px]">
              <div>
                <div className="text-[12px] text-[#616977] mb-1">Тема защиты</div>
                <div className="font-bold text-[14px] text-[#141A24] leading-snug">
                  Стратегия развития департамента до 2030 года
                </div>
              </div>

              <div>
                <div className="text-[12px] text-[#616977] mb-1">Требования к презентации</div>
                <ul className="text-[#334155] space-y-1">
                  <li>• 10–12 слайдов, 10 минут на защиту</li>
                  <li>• Проблематика, цели, план, бюджет</li>
                  <li>• Ответы на вопросы комиссии</li>
                </ul>
              </div>

              <div>
                <div className="text-[12px] text-[#616977] mb-1">Комиссия</div>
                <ul className="text-[#334155] space-y-1">
                  <li>• Заместитель главы города</li>
                  <li>• Директор департамента кадров</li>
                  <li>• Внешний эксперт</li>
                </ul>
              </div>
            </div>
          </div>

          {/* Card 2: Участники защиты: оценки комиссии */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl shadow-sm overflow-hidden">
            <div className="p-6 border-b border-[#E1E5EB]">
              <h2 className="text-[16px] font-bold text-[#141A24]">
                Участники защиты: оценки комиссии (1–10)
              </h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[14px]">
                <thead className="bg-[#FAFBFD] border-b border-[#E1E5EB] text-[13px] text-[#616977]">
                  <tr>
                    <th className="py-3 px-6 font-medium whitespace-nowrap">Участник</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Целевая должность</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Проблематика</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Проект</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Презентация</th>
                    <th className="py-3 px-6 font-medium whitespace-nowrap">Итог</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E1E5EB]">
                  {participants.map((p) => (
                    <tr key={p.name} className="hover:bg-[#F8FAFC]">
                      <td className="py-3.5 px-6 font-medium text-[#141A24] whitespace-nowrap">
                        {p.name}
                      </td>
                      <td className="py-3.5 px-4 text-[#4A5363] whitespace-nowrap">
                        {p.targetRole}
                      </td>
                      <td className="py-3.5 px-4 text-[#141A24] font-medium whitespace-nowrap">
                        {p.problemScore}
                      </td>
                      <td className="py-3.5 px-4 text-[#141A24] font-medium whitespace-nowrap">
                        {p.projectScore}
                      </td>
                      <td className="py-3.5 px-4 text-[#141A24] font-medium whitespace-nowrap">
                        {p.presScore}
                      </td>
                      <td className="py-3.5 px-6 whitespace-nowrap">
                        <span className={`inline-block px-2.5 py-0.5 rounded-full text-[12px] font-medium whitespace-nowrap ${p.verdictColor}`}>
                          {p.verdict}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Card 3: Резервисты */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl shadow-sm overflow-hidden">
            <div className="p-6 border-b border-[#E1E5EB]">
              <h2 className="text-[16px] font-bold text-[#141A24]">
                Резервисты
              </h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[14px]">
                <thead className="bg-[#FAFBFD] border-b border-[#E1E5EB] text-[13px] text-[#616977]">
                  <tr>
                    <th className="py-3 px-6 font-medium whitespace-nowrap">Резервист</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Целевая должность</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">Готовность</th>
                    <th className="py-3 px-4 font-medium whitespace-nowrap">В резерве с</th>
                    <th className="py-3 px-6 font-medium whitespace-nowrap">Актуальность</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E1E5EB]">
                  {reservists.map((r) => (
                    <tr key={r.name} className="hover:bg-[#F8FAFC]">
                      <td className="py-3.5 px-6 font-medium text-[#141A24] whitespace-nowrap">
                        {r.name}
                      </td>
                      <td className="py-3.5 px-4 text-[#4A5363] whitespace-nowrap">
                        {r.targetRole}
                      </td>
                      <td className="py-3.5 px-4 text-[#141A24] whitespace-nowrap">
                        {r.readiness}
                      </td>
                      <td className="py-3.5 px-4 text-[#4A5363] whitespace-nowrap">
                        {r.since}
                      </td>
                      <td className="py-3.5 px-6 whitespace-nowrap">
                        {r.isPlain ? (
                          <span className="text-[#4A5363] text-[13px] whitespace-nowrap">
                            {r.status}
                          </span>
                        ) : (
                          <span className={`inline-block px-2.5 py-0.5 rounded-full text-[12px] font-medium whitespace-nowrap ${r.statusColor}`}>
                            {r.status}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* МАКЕТ 25: СТУДЕНЧЕСКИЙ РЕЗЕРВ (Кадровый резерв_ студенты) */}
      {/* ======================================================== */}
      {activeSubTab === 'students' && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start">
          {students.map((st) => (
            <div
              key={st.name}
              className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm flex flex-col justify-between h-full space-y-4"
            >
              <div>
                <div className="flex items-start justify-between gap-2 mb-1">
                  <h3 className="text-[16px] font-bold text-[#141A24]">
                    {st.name}
                  </h3>
                  <span className="bg-[#FEF3E6] text-[#B45309] px-2.5 py-0.5 rounded text-[11px] font-medium whitespace-nowrap">
                    {st.uniBadge}
                  </span>
                </div>
                <div className="text-[12px] text-[#616977] mb-3">
                  {st.practiceDept}
                </div>

                <div className="bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl p-3.5 text-[13px] text-[#334155] leading-relaxed mb-4">
                  {st.quote}
                </div>

                <div className="flex flex-wrap items-center gap-1.5 mb-2">
                  {st.skills.map((skill) => (
                    <span
                      key={skill}
                      className="bg-[#EEF3FE] text-[#1F4FD1] text-[12px] font-medium px-2.5 py-0.5 rounded whitespace-nowrap"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              </div>

              <div>
                <button
                  type="button"
                  onClick={() => {
                    if (onOfferVacancy) onOfferVacancy(st.name);
                    else showToast(`Вакансия предложена кандидату ${st.name}`);
                  }}
                  className="w-full py-2 px-4 text-[13px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors shadow-sm text-center whitespace-nowrap"
                >
                  Предложить вакансию
                </button>
              </div>
            </div>
          ))}
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

export default TalentReserve;
