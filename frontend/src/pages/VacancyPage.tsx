import React, { useEffect, useState } from 'react';

interface VacancyDetail {
  id: string;
  title: string;
  department: string;
  district: string;
  salary: string;
  tasks: string[];
  required: string[];
  plus: string[];
  conditions: string[];
}

const VACANCIES: Record<string, VacancyDetail> = {
  'python-dev': {
    id: 'python-dev',
    title: 'Python-разработчик',
    department: 'Департамент цифрового развития',
    district: 'Нижегородский район',
    salary: '60 000 – 90 000 ₽',
    tasks: [
      'Разработка и поддержка городских цифровых сервисов',
      'Автоматизированное тестирование API',
      'Интеграция с ведомственными системами',
    ],
    required: [
      'Высшее образование',
      'Подтверждённый коммерческий опыт не менее 2 лет',
    ],
    plus: ['pytest и PostgreSQL', 'Работа с госсистемами'],
    conditions: [
      'Пятидневная рабочая неделя',
      'Социальные гарантии муниципальной службы',
      'Наставник и курс адаптации в первый месяц',
    ],
  },
  'data-analyst': {
    id: 'data-analyst',
    title: 'Аналитик данных',
    department: 'Департамент цифрового развития',
    district: 'Нижегородский район',
    salary: '55 000 – 80 000 ₽',
    tasks: [
      'Сбор и анализ данных по городским сервисам и обращениям жителей',
      'Построение дашбордов и регулярной отчётности в Power BI',
      'Подготовка аналитических записок для руководителей департаментов',
    ],
    required: [
      'Высшее образование',
      'Уверенный SQL и опыт работы с BI-инструментами (Power BI)',
    ],
    plus: ['Python (pandas) для обработки данных', 'Опыт работы с госотчётностью'],
    conditions: [
      'Пятидневная рабочая неделя',
      'Социальные гарантии муниципальной службы',
      'Наставник и курс адаптации в первый месяц',
    ],
  },
  'pto-engineer': {
    id: 'pto-engineer',
    title: 'Инженер ПТО',
    department: 'Департамент строительства',
    district: 'Нижегородский район',
    salary: '55 000 – 85 000 ₽',
    tasks: [
      'Проверка проектно-сметной и исполнительной документации',
      'Сопровождение объектов капитального строительства и благоустройства',
      'Взаимодействие с подрядными организациями и технический контроль',
    ],
    required: [
      'Высшее техническое образование',
      'Подтверждённый опыт работы от 3 лет',
    ],
    plus: ['AutoCAD и сметные комплексы', 'Опыт работы по 44-ФЗ'],
    conditions: [
      'Пятидневная рабочая неделя',
      'Социальные гарантии муниципальной службы',
      'Наставник и курс адаптации в первый месяц',
    ],
  },
};

interface VacancyPageProps {
  vacancyId?: string;
  onGoHome?: () => void;
  onGoVacancies?: () => void;
  onGoCabinet?: () => void;
  initialSubmitted?: boolean;
}

export const VacancyPage: React.FC<VacancyPageProps> = ({
  vacancyId = 'python-dev',
  onGoHome,
  onGoVacancies,
  onGoCabinet,
  initialSubmitted = false,
}) => {
  const vacancy = VACANCIES[vacancyId] || VACANCIES['python-dev'];
  const [isSubmitted, setIsSubmitted] = useState<boolean>(initialSubmitted);
  const [fio, setFio] = useState('');
  const [email, setEmail] = useState('');
  const [resumeFileName, setResumeFileName] = useState('');
  const [agreed, setAgreed] = useState(false);

  useEffect(() => {
    setIsSubmitted(initialSubmitted);
  }, [vacancyId, initialSubmitted]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitted(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="space-y-6">
      {/* Breadcrumbs */}
      <nav className="text-[13px] text-[#616977] flex items-center gap-1.5">
        <button
          type="button"
          onClick={onGoHome}
          className="hover:text-[#1F4FD1] transition-colors"
        >
          Главная
        </button>
        <span>›</span>
        <button
          type="button"
          onClick={onGoVacancies || onGoHome}
          className="hover:text-[#1F4FD1] transition-colors"
        >
          Вакансии
        </button>
        <span>›</span>
        <span className="text-[#141A24] font-medium">{vacancy.title}</span>
      </nav>

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Vacancy Details (8 cols) */}
        <div className="lg:col-span-8 bg-white border border-[#E1E5EB] rounded-2xl p-6 sm:p-8 shadow-sm">
          {/* Badges */}
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <span className="px-3 py-1 rounded-md text-[12px] font-medium bg-[#EEF3FE] text-[#1F4FD1]">
              {vacancy.department}
            </span>
            <span className="px-3 py-1 rounded-md text-[12px] font-medium bg-[#F1F3F5] text-[#4A5363]">
              {vacancy.district}
            </span>
            <span className="px-3 py-1 rounded-md text-[12px] font-medium bg-[#F1F3F5] text-[#4A5363]">
              Муниципальная служба
            </span>
          </div>

          {/* Job Title */}
          <h1 className="text-[28px] sm:text-[34px] font-bold text-[#141A24] tracking-tight mb-2">
            {vacancy.title}
          </h1>

          {/* Salary */}
          <div className="text-[16px] text-[#616977] mb-8">
            <span className="text-[18px] sm:text-[20px] font-bold text-[#141A24]">
              {vacancy.salary}
            </span>{' '}
            до вычета налогов · оклад и надбавки за выслугу и классный чин
          </div>

          {/* Section: Чем предстоит заниматься */}
          <div className="mb-8">
            <h2 className="text-[16px] font-bold text-[#141A24] mb-3">
              Чем предстоит заниматься
            </h2>
            <ul className="space-y-2 text-[14px] text-[#334155] leading-relaxed">
              {vacancy.tasks.map((task) => (
                <li key={task} className="flex items-start gap-2">
                  <span className="text-[#141A24]">•</span>
                  <span>{task}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Side-by-side Requirement Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
            {/* Обязательные требования */}
            <div className="bg-[#FFF6EC] border border-[#F3DDBF] rounded-xl p-5">
              <h3 className="text-[15px] font-bold text-[#141A24] mb-3">
                Обязательные требования
              </h3>
              <ul className="space-y-2 text-[13px] text-[#334155] leading-relaxed">
                {vacancy.required.map((req) => (
                  <li key={req} className="flex items-start gap-2">
                    <span>•</span>
                    <span>{req}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Будет плюсом */}
            <div className="bg-[#F7F8FA] border border-[#E1E5EB] rounded-xl p-5">
              <h3 className="text-[15px] font-bold text-[#141A24] mb-3">
                Будет плюсом
              </h3>
              <ul className="space-y-2 text-[13px] text-[#334155] leading-relaxed">
                {vacancy.plus.map((item) => (
                  <li key={item} className="flex items-start gap-2">
                    <span>•</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Section: Условия */}
          <div>
            <h2 className="text-[16px] font-bold text-[#141A24] mb-3">
              Условия
            </h2>
            <ul className="space-y-2 text-[14px] text-[#334155] leading-relaxed">
              {vacancy.conditions.map((cond) => (
                <li key={cond} className="flex items-start gap-2">
                  <span className="text-[#141A24]">•</span>
                  <span>{cond}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Right Column: Sticky Action Form / State (4 cols) */}
        <div className="lg:col-span-4 bg-white border border-[#E1E5EB] rounded-2xl p-6 sm:p-7 shadow-sm sticky top-24">
          {/* STATE A: Форма отклика */}
          {!isSubmitted && (
            <form onSubmit={handleSubmit}>
              <h2 className="text-[20px] font-bold text-[#141A24] mb-1">
                Откликнуться
              </h2>
              <p className="text-[13px] text-[#616977] leading-snug mb-5">
                Уже есть аккаунт?{' '}
                <button
                  type="button"
                  onClick={onGoCabinet}
                  className="text-[#1F4FD1] font-medium hover:underline"
                >
                  Войдите
                </button>
                , данные подставятся сами.
              </p>

              {/* Field: ФИО */}
              <div className="mb-4">
                <label className="block text-[13px] font-medium text-[#141A24] mb-1.5">
                  ФИО
                </label>
                <input
                  type="text"
                  required
                  value={fio}
                  onChange={(e) => setFio(e.target.value)}
                  placeholder="Иванов Иван"
                  className="w-full h-11 px-3.5 bg-white border border-[#E1E5EB] rounded-lg text-[14px] text-[#141A24] placeholder-[#8E939D] focus:outline-none focus:border-[#1F4FD1]"
                />
              </div>

              {/* Field: Электронная почта */}
              <div className="mb-4">
                <label className="block text-[13px] font-medium text-[#141A24] mb-1.5">
                  Электронная почта
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@mail.ru"
                  className="w-full h-11 px-3.5 bg-white border border-[#E1E5EB] rounded-lg text-[14px] text-[#141A24] placeholder-[#8E939D] focus:outline-none focus:border-[#1F4FD1]"
                />
              </div>

              {/* Field: Резюме Dropzone */}
              <div className="mb-4">
                <label className="block text-[13px] font-medium text-[#141A24] mb-1.5">
                  Резюме
                </label>
                <label className="block bg-[#F5F8FF] border-2 border-dashed border-[#94B4FB] rounded-xl p-5 text-center cursor-pointer hover:bg-[#EEF3FE] transition-colors">
                  <input
                    type="file"
                    accept=".pdf,.doc,.docx"
                    className="hidden"
                    onChange={(e) => setResumeFileName(e.target.files?.[0]?.name || '')}
                  />
                  <div className="text-[14px] font-bold text-[#141A24] mb-1">
                    {resumeFileName || 'Перетащите резюме сюда'}
                  </div>
                  <div className="text-[12px] text-[#616977]">
                    {resumeFileName ? 'Нажмите, чтобы заменить файл' : 'или выберите файл: PDF, DOCX до 10 МБ'}
                  </div>
                </label>
              </div>

              {/* Checkbox: 152-ФЗ */}
              <label className="flex items-start gap-2.5 mb-5 cursor-pointer select-none">
                <input
                  type="checkbox"
                  required
                  checked={agreed}
                  onChange={(e) => setAgreed(e.target.checked)}
                  className="mt-1 w-4 h-4 rounded border-[#E1E5EB] text-[#1F4FD1] focus:ring-0"
                />
                <span className="text-[13px] text-[#334155] leading-snug">
                  Согласен на обработку персональных данных (152-ФЗ)
                </span>
              </label>

              {/* Submit Button */}
              <button
                type="submit"
                className="w-full h-11 bg-[#1F4FD1] hover:bg-[#1841B2] text-white font-medium text-[14px] rounded-lg transition-colors shadow-sm"
              >
                Отправить отклик
              </button>

              {/* Automatic note */}
              <p className="text-[11px] text-[#616977] text-center mt-3.5">
                Отметка согласия и дата сохраняются автоматически.
              </p>
            </form>
          )}

          {/* STATE B: Отклик отправлен */}
          {isSubmitted && (
            <div className="py-2">
              {/* Green Check Icon Badge */}
              <div className="w-12 h-12 rounded-full bg-[#E6F4EA] flex items-center justify-center mb-4">
                <img src="/icons/check.svg" alt="" className="w-6 h-6" />
              </div>

              {/* Heading */}
              <h2 className="text-[20px] font-bold text-[#141A24] mb-2">
                Отклик отправлен
              </h2>

              {/* Body text */}
              <p className="text-[14px] text-[#4A5363] leading-relaxed mb-6">
                Мы разберём резюме в течение 3 рабочих дней. Если чего-то не хватит, вопрос придёт в личный кабинет.
              </p>

              {/* Cabinet Button */}
              <button
                type="button"
                onClick={onGoCabinet}
                className="w-full h-11 bg-[#1F4FD1] hover:bg-[#1841B2] text-white font-medium text-[14px] rounded-lg transition-colors shadow-sm"
              >
                Перейти в личный кабинет
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default VacancyPage;
