import React from 'react';

interface NewVacanciesSectionProps {
  onSelectVacancy?: (vacancyId: string) => void;
}

export const NewVacanciesSection: React.FC<NewVacanciesSectionProps> = ({ onSelectVacancy }) => {
  const vacancies = [
    {
      id: 'python-dev',
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
      tags: [
        { label: 'Строительства', bg: 'bg-[#EEF3FE] text-[#1F4FD1]' },
        { label: 'Нижегородский район', bg: 'bg-[#F1F3F5] text-[#4A5363]' },
      ],
      title: 'Инженер ПТО',
      experience: 'Высшее техническое, опыт от 3 лет',
      salary: '55 000 – 85 000 ₽',
    },
  ];

  return (
    <section>
      <h2 className="text-[20px] font-bold text-[#141A24] mb-4">
        Новые вакансии
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {vacancies.map((v) => (
          <div
            key={v.id}
            onClick={() => onSelectVacancy?.(v.id)}
            className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm flex flex-col justify-between hover:shadow-md transition-shadow cursor-pointer"
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
          </div>
        ))}
      </div>
    </section>
  );
};

export default NewVacanciesSection;
