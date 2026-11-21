import React, { useState } from 'react';

interface VacancyPageProps {
  onGoHome?: () => void;
  onGoCabinet?: () => void;
  initialSubmitted?: boolean;
}

export const VacancyPage: React.FC<VacancyPageProps> = ({
  onGoHome,
  onGoCabinet,
  initialSubmitted = false,
}) => {
  const [isSubmitted, setIsSubmitted] = useState<boolean>(initialSubmitted);
  const [fio, setFio] = useState('');
  const [email, setEmail] = useState('');
  const [agreed, setAgreed] = useState(false);

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
          onClick={onGoHome}
          className="hover:text-[#1F4FD1] transition-colors"
        >
          Вакансии
        </button>
        <span>›</span>
        <span className="text-[#141A24] font-medium">Python-разработчик</span>
      </nav>

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Vacancy Details (8 cols) */}
        <div className="lg:col-span-8 bg-white border border-[#E1E5EB] rounded-2xl p-6 sm:p-8 shadow-sm">
          {/* Badges */}
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <span className="px-3 py-1 rounded-md text-[12px] font-medium bg-[#EEF3FE] text-[#1F4FD1]">
              Департамент цифрового развития
            </span>
            <span className="px-3 py-1 rounded-md text-[12px] font-medium bg-[#F1F3F5] text-[#4A5363]">
              Нижегородский район
            </span>
            <span className="px-3 py-1 rounded-md text-[12px] font-medium bg-[#F1F3F5] text-[#4A5363]">
              Муниципальная служба
            </span>
          </div>

          {/* Job Title */}
          <h1 className="text-[28px] sm:text-[34px] font-bold text-[#141A24] tracking-tight mb-2">
            Python-разработчик
          </h1>

          {/* Salary */}
          <div className="text-[16px] text-[#616977] mb-8">
            <span className="text-[18px] sm:text-[20px] font-bold text-[#141A24]">
              60 000 – 90 000 ₽
            </span>{' '}
            до вычета налогов · оклад и надбавки за выслугу и классный чин
          </div>

          {/* Section: Чем предстоит заниматься */}
          <div className="mb-8">
            <h2 className="text-[16px] font-bold text-[#141A24] mb-3">
              Чем предстоит заниматься
            </h2>
            <ul className="space-y-2 text-[14px] text-[#334155] leading-relaxed">
              <li className="flex items-start gap-2">
                <span className="text-[#141A24]">•</span>
                <span>Разработка и поддержка городских цифровых сервисов</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-[#141A24]">•</span>
                <span>Автоматизированное тестирование API</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-[#141A24]">•</span>
                <span>Интеграция с ведомственными системами</span>
              </li>
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
                <li className="flex items-start gap-2">
                  <span>•</span>
                  <span>Высшее образование</span>
                </li>
                <li className="flex items-start gap-2">
                  <span>•</span>
                  <span>Подтверждённый коммерческий опыт не менее 2 лет</span>
                </li>
              </ul>
            </div>

            {/* Будет плюсом */}
            <div className="bg-[#F7F8FA] border border-[#E1E5EB] rounded-xl p-5">
              <h3 className="text-[15px] font-bold text-[#141A24] mb-3">
                Будет плюсом
              </h3>
              <ul className="space-y-2 text-[13px] text-[#334155] leading-relaxed">
                <li className="flex items-start gap-2">
                  <span>•</span>
                  <span>pytest и PostgreSQL</span>
                </li>
                <li className="flex items-start gap-2">
                  <span>•</span>
                  <span>Работа с госсистемами</span>
                </li>
              </ul>
            </div>
          </div>

          {/* Section: Условия */}
          <div>
            <h2 className="text-[16px] font-bold text-[#141A24] mb-3">
              Условия
            </h2>
            <ul className="space-y-2 text-[14px] text-[#334155] leading-relaxed">
              <li className="flex items-start gap-2">
                <span className="text-[#141A24]">•</span>
                <span>Пятидневная рабочая неделя</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-[#141A24]">•</span>
                <span>Социальные гарантии муниципальной службы</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-[#141A24]">•</span>
                <span>Наставник и курс адаптации в первый месяц</span>
              </li>
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
                Уже есть аккаунт? Войдите, данные подставятся сами.
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
                <div className="bg-[#F5F8FF] border-2 border-dashed border-[#94B4FB] rounded-xl p-5 text-center cursor-pointer hover:bg-[#EEF3FE] transition-colors">
                  <div className="text-[14px] font-bold text-[#141A24] mb-1">
                    Перетащите резюме сюда
                  </div>
                  <div className="text-[12px] text-[#616977]">
                    или выберите файл: PDF, DOCX до 10 МБ
                  </div>
                </div>
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
