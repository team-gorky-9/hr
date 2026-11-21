import React from 'react';
import type { PortalSearchFilters } from './HeroSection';

interface NewVacanciesSectionProps {
  filters?: PortalSearchFilters;
  onResetFilters?: () => void;
  onSelectVacancy?: (vacancyId: string) => void;
}

export const NewVacanciesSection: React.FC<NewVacanciesSectionProps> = ({
  filters,
  onResetFilters,
  onSelectVacancy,
}) => {
  const vacancies = [
    {
      id: 'python-dev',
      department: 'Цифрового развития',
      district: 'Нижегородский район',
      tags: [
        { label: 'Цифрового развития', bg: 'bg-[#EEF3FE] text-[#1F4FD1]' },
        { label: 'Нижегородский район', bg: 'bg-[#F1F3F5] text-[#4A5363]' },
      ],
      title: 'Python-разработчик',
      experience: 'Опыт от 2 лет, тестирование API',
      salary: '60 000 – 90 000 ₽',
    },
    {
      id: 'data-analyst',
      department: 'Цифрового развития',
      district: 'Нижегородский район',
      tags: [
        { label: 'Цифрового развития', bg: 'bg-[#EEF3FE] text-[#1F4FD1]' },
        { label: 'Нижегородский район', bg: 'bg-[#F1F3F5] text-[#4A5363]' },
      ],
      title: 'Аналитик данных',
      experience: 'Высшее образование, SQL, Power BI',
      salary: '55 000 – 80 000 ₽',
    },
    {
      id: 'pto-engineer',
      department: 'Строительства',
      district: 'Нижегородский район',
      tags: [
        { label: 'Строительства', bg: 'bg-[#EEF3FE] text-[#1F4FD1]' },
        { label: 'Нижегородский район', bg: 'bg-[#F1F3F5] text-[#4A5363]' },
      ],
      title: 'Инженер ПТО',
      experience: 'Высшее техническое, опыт от 3 лет',
      salary: '55 000 – 85 000 ₽',
    },
  ];

  const q = (filters?.query || '').trim().toLowerCase();
  const filteredVacancies = vacancies.filter((v) => {
    if (filters?.department && v.department !== filters.department) return false;
    if (filters?.district && v.district !== filters.district) return false;
    if (q) {
      const hay = `${v.title} ${v.experience} ${v.department} ${v.district}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const hasActiveFilters = Boolean(q || filters?.department || filters?.district);

  return (
    <section id="new-vacancies" className="scroll-mt-24">
      <div className="flex items-center justify-between gap-4 mb-4">
        <h2 className="text-[20px] font-bold text-[#141A24]">
          Новые вакансии
        </h2>
        {hasActiveFilters && onResetFilters && (
          <button
            type="button"
            onClick={onResetFilters}
            className="text-[13px] font-medium text-[#1F4FD1] hover:underline"
          >
            Сбросить фильтры
          </button>
        )}
      </div>

      {filteredVacancies.length === 0 ? (
        <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 text-center space-y-3">
          <p className="text-[14px] text-[#616977]">
            По выбранным параметрам вакансий не найдено.
          </p>
          {onResetFilters && (
            <button
              type="button"
              onClick={onResetFilters}
              className="px-4 py-2 text-[13px] font-medium text-[#1F4FD1] bg-[#EEF3FE] rounded-lg hover:bg-[#DCE7FD] transition-colors"
            >
              Показать все вакансии
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {filteredVacancies.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => onSelectVacancy?.(v.id)}
              className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm flex flex-col justify-between text-left hover:shadow-md transition-shadow cursor-pointer"
            >
              <div>
                {/* Badges */}
                <div className="flex flex-wrap items-center gap-2 mb-3">
                  {v.tags.map((t) => (
                    <span
                      key={t.label}
                      className={`px-2.5 py-1 rounded-md text-[12px] font-medium ${t.bg}`}
                    >
                      {t.label}
                    </span>
                  ))}
                </div>

                {/* Title */}
                <h3 className="text-[18px] font-bold text-[#141A24] mb-1.5">
                  {v.title}
                </h3>

                {/* Experience / Description */}
                <p className="text-[13px] text-[#616977] mb-6">
                  {v.experience}
                </p>
              </div>

              {/* Salary */}
              <div className="text-[16px] font-bold text-[#141A24]">
                {v.salary}{' '}
                <span className="text-[12px] text-[#616977] font-normal">
                  до вычета налогов
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </section>
  );
};

export default NewVacanciesSection;
