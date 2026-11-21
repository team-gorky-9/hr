import React, { useState } from 'react';

export interface ResponseItem {
  id: string;
  name: string;
  source: string;
  requirementExp: 'Выполнено' | 'Нужно уточнить' | 'Не выполнено' | 'Не оценено';
  skillApi: string;
  category: 'call' | 'clarify' | 'reject' | 'action';
}

const mockResponses: ResponseItem[] = [
  {
    id: 'r1',
    name: 'Фролов Денис',
    source: 'HH.ru',
    requirementExp: 'Нужно уточнить',
    skillApi: '85 · цитата найдена',
    category: 'clarify',
  },
  {
    id: 'r2',
    name: 'Ковалёва Анна',
    source: '«Работа России»',
    requirementExp: 'Выполнено',
    skillApi: '85 · цитата найдена',
    category: 'call',
  },
  {
    id: 'r3',
    name: 'Морозов Илья',
    source: 'Сайт администрации',
    requirementExp: 'Не выполнено',
    skillApi: '85 · цитата найдена',
    category: 'reject',
  },
  {
    id: 'r4',
    name: 'Белова Ольга',
    source: 'HH.ru',
    requirementExp: 'Нужно уточнить',
    skillApi: 'Цитата не найдена',
    category: 'clarify',
  },
  {
    id: 'r5',
    name: 'Соколов Артём',
    source: 'Почта',
    requirementExp: 'Не оценено',
    skillApi: '—',
    category: 'action',
  },
  {
    id: 'r6',
    name: 'Кузнецова Мария',
    source: 'HH.ru',
    requirementExp: 'Не оценено',
    skillApi: '—',
    category: 'action',
  },
];

interface VacancyResponsesProps {
  initialVacancyId?: string;
  onOpenCard?: (responseId: string) => void;
  onManualUpload?: () => void;
}

type FilterTab = 'all' | 'call' | 'clarify' | 'reject' | 'action';

const requirementExpStyles: Record<string, string> = {
  'Выполнено': 'bg-[#E6F4EA] text-[#137333]',
  'Нужно уточнить': 'bg-[#FFF4E5] text-[#A16207]',
  'Не выполнено': 'bg-[#FDE8E8] text-[#C5221F]',
  'Не оценено': 'bg-[#F1F3F5] text-[#616977]',
};

export const VacancyResponses: React.FC<VacancyResponsesProps> = ({
  initialVacancyId = 'v1',
  onOpenCard,
  onManualUpload: _onManualUpload,
}) => {
  const [selectedVacancyId, setSelectedVacancyId] = useState<string>(initialVacancyId);
  const [activeFilter, setActiveFilter] = useState<FilterTab>('all');

  const vacancies = [
    {
      id: 'v1',
      title: 'Python-разработчик',
      department: 'Департамент цифрового развития',
      count: '6 откликов',
      requirement: 'требование: коммерческий опыт от 2 лет',
      hasResponses: true,
    },
    {
      id: 'v2',
      title: 'Главный специалист по обращениям граждан',
      department: 'Общий отдел',
      count: 'нет откликов',
      requirement: 'требование: коммерческий опыт от 2 лет',
      hasResponses: false,
    },
  ];

  const currentVacancy = vacancies.find((v) => v.id === selectedVacancyId) || vacancies[0];

  const filteredResponses = mockResponses.filter((r) => {
    if (activeFilter === 'all') return true;
    if (activeFilter === 'call') return r.category === 'call';
    if (activeFilter === 'clarify') return r.requirementExp === 'Нужно уточнить';
    if (activeFilter === 'reject') return r.requirementExp === 'Не выполнено';
    if (activeFilter === 'action') return r.requirementExp === 'Не оценено' || r.category === 'clarify';
    return true;
  });

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8">
      {/* Page Title & Subtitle */}
      <div className="mb-6">
        <h1 className="text-[28px] sm:text-[32px] font-bold text-[#141A24] tracking-tight mb-1.5">
          Отклики
        </h1>
        <p className="text-[14px] text-[#616977]">
          Выберите вакансию и откройте отклик. Просмотр персональных данных фиксируется в журнале.
        </p>
      </div>

      {/* Two Column Layout */}
      <div className="flex flex-col md:flex-row gap-6 items-start">
        {/* Left Column: Vacancies List Card */}
        <div className="w-full md:w-[260px] shrink-0 bg-white border border-[#E1E5EB] rounded-2xl p-4 sm:p-5 shadow-sm">
          <h2 className="text-[18px] font-bold text-[#141A24] mb-3.5">
            Вакансии
          </h2>

          <div className="space-y-3">
            {vacancies.map((v) => {
              const isSelected = selectedVacancyId === v.id;
              return (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => setSelectedVacancyId(v.id)}
                  className={`w-full text-left p-4 rounded-xl transition-all ${
                    isSelected
                      ? 'border-[1.5px] border-[#1F4FD1] bg-[#EEF3FE]'
                      : 'border border-[#E1E5EB] bg-white hover:bg-[#F8FAFC]'
                  }`}
                >
                  <div className="text-[16px] font-bold text-[#141A24] mb-1 leading-snug">
                    {v.title}
                  </div>
                  <div className="text-[13px] text-[#4A5363] mb-1">
                    {v.department}
                  </div>
                  <div className="text-[13px] text-[#4A5363] font-medium">
                    {v.count}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right Column: Detail Container */}
        <div className="flex-1 min-w-0 bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
          {/* Vacancy Header */}
          <div className="mb-6">
            <h2 className="text-[24px] font-bold text-[#141A24] mb-1">
              {currentVacancy.title}
            </h2>
            <p className="text-[14px] text-[#616977]">
              {currentVacancy.department} · {currentVacancy.requirement}
            </p>
          </div>

          {currentVacancy.hasResponses ? (
            <>
              {/* Horizontal Filter Tabs / Chips */}
              <div className="flex items-center gap-3.5 lg:gap-4 border-b border-[#E1E5EB] mb-6 overflow-x-auto">
                {/* 1. Все */}
                <button
                  type="button"
                  onClick={() => setActiveFilter('all')}
                  className={`flex items-center gap-2 pb-3 text-[14px] font-medium transition-colors relative whitespace-nowrap ${
                    activeFilter === 'all'
                      ? 'text-[#1F4FD1] font-semibold'
                      : 'text-[#4A5363] hover:text-[#141A24]'
                  }`}
                >
                  <span>Все</span>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[12px] font-semibold ${
                      activeFilter === 'all'
                        ? 'bg-[#EEF3FE] text-[#1F4FD1]'
                        : 'bg-[#F1F3F5] text-[#616977]'
                    }`}
                  >
                    6
                  </span>
                  {activeFilter === 'all' && (
                    <div className="absolute bottom-0 left-0 right-0 h-[2.5px] bg-[#1F4FD1] rounded-full" />
                  )}
                </button>

                {/* 2. Готов к звонку */}
                <button
                  type="button"
                  onClick={() => setActiveFilter('call')}
                  className={`flex items-center gap-2 pb-3 text-[14px] font-medium transition-colors relative whitespace-nowrap ${
                    activeFilter === 'call'
                      ? 'text-[#1F4FD1] font-semibold'
                      : 'text-[#141A24] hover:text-[#1F4FD1]'
                  }`}
                >
                  <span className="w-4 h-4 rounded-full bg-[#137333] flex items-center justify-center text-white text-[10px] font-bold">
                    ✓
                  </span>
                  <span>Готов к звонку</span>
                  <span className="px-2 py-0.5 rounded-full text-[12px] font-semibold bg-[#F1F3F5] text-[#616977]">
                    1
                  </span>
                  {activeFilter === 'call' && (
                    <div className="absolute bottom-0 left-0 right-0 h-[2.5px] bg-[#1F4FD1] rounded-full" />
                  )}
                </button>

                {/* 3. Нужно уточнить */}
                <button
                  type="button"
                  onClick={() => setActiveFilter('clarify')}
                  className={`flex items-center gap-2 pb-3 text-[14px] font-medium transition-colors relative whitespace-nowrap ${
                    activeFilter === 'clarify'
                      ? 'text-[#1F4FD1] font-semibold'
                      : 'text-[#141A24] hover:text-[#1F4FD1]'
                  }`}
                >
                  <span className="w-4 h-4 rounded-full bg-[#B45309] flex items-center justify-center text-white text-[11px] font-bold">
                    ?
                  </span>
                  <span>Нужно уточнить</span>
                  <span className="px-2 py-0.5 rounded-full text-[12px] font-semibold bg-[#F1F3F5] text-[#616977]">
                    1
                  </span>
                  {activeFilter === 'clarify' && (
                    <div className="absolute bottom-0 left-0 right-0 h-[2.5px] bg-[#1F4FD1] rounded-full" />
                  )}
                </button>

                {/* 4. Формально не проходит */}
                <button
                  type="button"
                  onClick={() => setActiveFilter('reject')}
                  className={`flex items-center gap-2 pb-3 text-[14px] font-medium transition-colors relative whitespace-nowrap ${
                    activeFilter === 'reject'
                      ? 'text-[#1F4FD1] font-semibold'
                      : 'text-[#141A24] hover:text-[#1F4FD1]'
                  }`}
                >
                  <span className="w-4 h-4 rounded-full bg-[#DC2626] flex items-center justify-center text-white text-[10px] font-bold">
                    ✕
                  </span>
                  <span>Формально не проходит</span>
                  <span className="px-2 py-0.5 rounded-full text-[12px] font-semibold bg-[#F1F3F5] text-[#616977]">
                    1
                  </span>
                  {activeFilter === 'reject' && (
                    <div className="absolute bottom-0 left-0 right-0 h-[2.5px] bg-[#1F4FD1] rounded-full" />
                  )}
                </button>

                {/* 5. Требуют действия */}
                <button
                  type="button"
                  onClick={() => setActiveFilter('action')}
                  className={`flex items-center gap-2 pb-3 text-[14px] font-medium transition-colors relative whitespace-nowrap ${
                    activeFilter === 'action'
                      ? 'text-[#1F4FD1] font-semibold'
                      : 'text-[#141A24] hover:text-[#1F4FD1]'
                  }`}
                >
                  <span className="w-4 h-4 rounded-full border-2 border-[#616977] flex items-center justify-center">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#616977]"></span>
                  </span>
                  <span>Требуют действия</span>
                  <span className="px-2 py-0.5 rounded-full text-[12px] font-semibold bg-[#F1F3F5] text-[#616977]">
                    3
                  </span>
                  {activeFilter === 'action' && (
                    <div className="absolute bottom-0 left-0 right-0 h-[2.5px] bg-[#1F4FD1] rounded-full" />
                  )}
                </button>
              </div>

              {/* Responses Table Container */}
              <div className="border border-[#E1E5EB] rounded-2xl overflow-hidden bg-white">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-[14px] min-w-[700px]">
                    <thead className="border-b border-[#E1E5EB] text-[13px] text-[#4A5363] font-semibold bg-white">
                      <tr>
                        <th className="py-4 pl-6 pr-4 font-semibold whitespace-nowrap">
                          Отклик
                        </th>
                        <th className="py-4 px-4 font-semibold whitespace-nowrap">
                          Опыт от 2 лет
                        </th>
                        <th className="py-4 px-4 font-semibold whitespace-nowrap">
                          Тестирование API
                        </th>
                        <th className="py-4 pl-4 pr-6 text-right whitespace-nowrap"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E1E5EB]">
                      {filteredResponses.map((r) => (
                        <tr key={r.id} className="hover:bg-[#F8FAFC] transition-colors">
                          {/* Col 1: Кандидат и источник */}
                          <td className="py-4 pl-6 pr-4 whitespace-nowrap">
                            <div className="text-[15px] font-bold text-[#1F4FD1] leading-snug">
                              {r.name}
                            </div>
                            <div className="text-[13px] text-[#616977] mt-0.5">
                              {r.source}
                            </div>
                          </td>

                          {/* Col 2: Опыт от 2 лет (бейдж) */}
                          <td className="py-4 px-4 whitespace-nowrap">
                            <span
                              className={`inline-block px-3 py-1 rounded-md text-[13px] font-medium whitespace-nowrap ${
                                requirementExpStyles[r.requirementExp] || 'bg-[#F1F3F5] text-[#616977]'
                              }`}
                            >
                              {r.requirementExp}
                            </span>
                          </td>

                          {/* Col 3: Тестирование API */}
                          <td className="py-4 px-4 text-[#141A24] text-[14px] whitespace-nowrap">
                            {r.skillApi}
                          </td>

                          {/* Col 4: Кнопка «Открыть» */}
                          <td className="py-4 pl-4 pr-6 text-right whitespace-nowrap">
                            <button
                              type="button"
                              onClick={() => onOpenCard?.(r.id)}
                              className="px-6 py-2 text-[14px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-xl hover:bg-[#F8FAFC] transition-colors shadow-sm whitespace-nowrap"
                            >
                              Открыть
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            /* Пустой список для вакансии без откликов */
            <div className="border-2 border-dashed border-[#D2D4D8] rounded-2xl p-8 lg:p-10 flex flex-col items-start">
              <h3 className="text-[18px] font-bold text-[#141A24] mb-2">
                Откликов пока нет
              </h3>
              <p className="text-[14px] text-[#616977] max-w-xl leading-relaxed mb-6">
                Они появятся здесь автоматически из HH.ru, «Работы России», с сайта администрации и из обращений граждан.
              </p>
              <button
                type="button"
                onClick={() => _onManualUpload?.()}
                className="px-5 py-2.5 text-[14px] font-medium text-[#141A24] bg-white border border-[#D2D4D8] rounded-xl hover:bg-[#F8FAFC] transition-colors shadow-sm"
              >
                Загрузить отклик вручную
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default VacancyResponses;
