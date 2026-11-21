import React from 'react';

interface StudentsPageProps {
  onApplyPractice?: (title: string) => void;
  onRegisterEvent?: (eventTitle: string) => void;
}

export const StudentsPage: React.FC<StudentsPageProps> = ({
  onApplyPractice,
  onRegisterEvent,
}) => {
  const practices = [
    {
      id: 'p1',
      title: 'Практика в правовом управлении',
      department: 'Правовое управление · 2 месяца',
      description: 'Подготовка проектов ответов на обращения граждан.',
    },
    {
      id: 'p2',
      title: 'Стажировка: аналитика данных',
      department: 'Департамент цифрового развития · 3 месяца',
      description: 'Дашборды по обращениям жителей, Power BI и SQL.',
    },
    {
      id: 'p3',
      title: 'Практика в департаменте строительства',
      department: 'Департамент строительства · 1 месяц',
      description: 'Технический надзор, проектная документация.',
    },
  ];

  const events = [
    {
      id: 'e1',
      day: '04',
      month: 'ДЕК',
      title: 'День карьеры в администрации',
      subtitle: 'Для студентов всех вузов',
    },
    {
      id: 'e2',
      day: '12',
      month: 'ДЕК',
      title: 'Хакатон по городским сервисам',
      subtitle: 'Онлайн и в IT-парке',
    },
    {
      id: 'e3',
      day: '22',
      month: 'ЯНВ',
      title: 'Экскурсия «Как устроена администрация»',
      subtitle: 'Для групп от 10 человек',
    },
  ];

  return (
    <div className="space-y-10">
      {/* 1. Hero Banner */}
      <section className="bg-[#FF6A3D] rounded-2xl p-8 lg:p-12 text-white shadow-sm">
        <span className="inline-block bg-white/95 text-[#C2410C] text-[12px] font-bold px-3 py-1 rounded-full mb-4 shadow-sm">
          Для студентов и выпускников
        </span>
        <h1 className="text-[32px] sm:text-[38px] font-bold tracking-tight mb-3">
          Практика в администрации — не для галочки
        </h1>
        <p className="text-[15px] sm:text-[16px] text-white/95 leading-relaxed max-w-2xl">
          Реальные задачи города, наставник из департамента и шанс попасть в студенческий резерв.
        </p>
      </section>

      {/* 2. Практика и стажировки */}
      <section>
        <h2 className="text-[20px] font-bold text-[#141A24] mb-4">
          Практика и стажировки
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {practices.map((p) => (
            <div
              key={p.id}
              className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm flex flex-col justify-between hover:shadow-md transition-shadow"
            >
              <div>
                <span className="inline-block bg-[#FEF7E0] text-[#B06000] text-[12px] font-medium px-2.5 py-1 rounded-md mb-3">
                  Практика
                </span>
                <h3 className="text-[17px] font-bold text-[#141A24] mb-1.5">
                  {p.title}
                </h3>
                <p className="text-[13px] text-[#616977] mb-3">
                  {p.department}
                </p>
                <p className="text-[13px] text-[#4A5363] leading-relaxed mb-6">
                  {p.description}
                </p>
              </div>

              <div>
                <button
                  type="button"
                  onClick={() => onApplyPractice?.(p.title)}
                  className="px-6 py-2.5 bg-[#1F4FD1] hover:bg-[#1841B2] text-white text-[14px] font-medium rounded-lg transition-colors shadow-sm"
                >
                  Откликнуться
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 3. Мероприятия */}
      <section>
        <h2 className="text-[20px] font-bold text-[#141A24] mb-4">
          Мероприятия
        </h2>

        <div className="space-y-3.5">
          {events.map((ev) => (
            <div
              key={ev.id}
              className="bg-white border border-[#E1E5EB] rounded-2xl p-5 shadow-sm flex items-center justify-between hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-5">
                {/* Date Square */}
                <div className="w-14 h-14 bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl flex flex-col items-center justify-center text-center shrink-0">
                  <span className="text-[18px] font-bold text-[#141A24] leading-tight">
                    {ev.day}
                  </span>
                  <span className="text-[11px] font-bold text-[#616977] uppercase">
                    {ev.month}
                  </span>
                </div>

                {/* Event Info */}
                <div>
                  <h3 className="text-[16px] font-bold text-[#141A24] mb-0.5">
                    {ev.title}
                  </h3>
                  <p className="text-[13px] text-[#616977]">
                    {ev.subtitle}
                  </p>
                </div>
              </div>

              {/* Action Button */}
              <button
                type="button"
                onClick={() => onRegisterEvent?.(ev.title)}
                disabled={!onRegisterEvent}
                className="px-6 py-2.5 text-[14px] font-medium rounded-lg transition-colors whitespace-nowrap shadow-sm shrink-0 text-[#616977] bg-white border border-[#E1E5EB] disabled:cursor-default"
              >
                {onRegisterEvent ? 'Записаться' : 'Запись пока недоступна'}
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default StudentsPage;
