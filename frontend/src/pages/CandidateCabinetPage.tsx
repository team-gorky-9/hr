import React, { useState } from 'react';

interface CandidateCabinetPageProps {
  onGoHome?: () => void;
  onGoVacancy?: () => void;
  initialAnswered?: boolean;
}

export const CandidateCabinetPage: React.FC<CandidateCabinetPageProps> = ({
  onGoHome: _onGoHome,
  onGoVacancy,
  initialAnswered = false,
}) => {
  const [isAnswered, setIsAnswered] = useState<boolean>(initialAnswered);
  const [answerText, setAnswerText] = useState<string>('');

  const handleAnswerSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsAnswered(true);
  };

  return (
    <div className="space-y-6">
      {/* Title & Subtitle */}
      <div>
        <h1 className="text-[26px] sm:text-[30px] font-bold text-[#141A24] mb-1">
          Личный кабинет
        </h1>
        <p className="text-[14px] text-[#616977]">
          Здесь видно, что происходит с каждым вашим откликом
        </p>
      </div>

      {/* State 4: Баннер вопроса «Нужно ответить» */}
      {!isAnswered && (
        <div className="bg-[#FFF8E8] border border-[#F3E2B5] rounded-2xl p-5 sm:p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <span className="bg-[#FFEFD9] text-[#9A3412] text-[12px] font-medium px-2.5 py-1 rounded-md">
              Нужно ответить
            </span>
            <span className="text-[13px] text-[#4A5363] font-medium">
              Python-разработчик
            </span>
          </div>

          <h2 className="text-[17px] sm:text-[18px] font-bold text-[#141A24] mb-3">
            Сколько лет у вас коммерческого опыта разработки?
          </h2>

          <form
            onSubmit={handleAnswerSubmit}
            className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 mb-2.5"
          >
            <input
              type="text"
              required
              value={answerText}
              onChange={(e) => setAnswerText(e.target.value)}
              placeholder="Например: 3 года"
              className="flex-1 h-11 px-4 bg-white border border-[#E1E5EB] rounded-lg text-[14px] text-[#141A24] placeholder-[#8E939D] focus:outline-none focus:border-[#1F4FD1]"
            />
            <button
              type="submit"
              className="h-11 px-6 bg-[#1F4FD1] hover:bg-[#1841B2] text-white text-[14px] font-medium rounded-lg transition-colors whitespace-nowrap shadow-sm"
            >
              Отправить ответ
            </button>
          </form>

          <p className="text-[13px] text-[#616977]">
            Ответ ускорит рассмотрение. Вопрос задан автоматически: этих данных нет в резюме.
          </p>
        </div>
      )}

      {/* State 5: Баннер подтверждения «Ответ отправлен сотруднику по подбору персонала» */}
      {isAnswered && (
        <div className="bg-[#E6F4EA] border border-[#A8DAB5] rounded-2xl p-5 shadow-sm">
          <h2 className="text-[16px] font-bold text-[#137333] mb-1">
            Ответ отправлен сотруднику по подбору персонала
          </h2>
          <p className="text-[14px] text-[#137333]">
            Отклик перешёл к следующему шагу: телефонное собеседование.
          </p>
        </div>
      )}

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Мои отклики (8 cols) */}
        <div className="lg:col-span-8 space-y-5">
          <h2 className="text-[20px] font-bold text-[#141A24]">
            Мои отклики
          </h2>

          {/* Card 1: Python-разработчик */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            {/* Top row */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6">
              <div>
                <h3 className="text-[18px] font-bold text-[#141A24] mb-1">
                  Python-разработчик
                </h3>
                <p className="text-[13px] text-[#616977]">
                  Департамент цифрового развития · отклик от 18.11.2026
                </p>
              </div>

              {!isAnswered ? (
                <span className="self-start sm:self-auto px-3 py-1 rounded-md text-[12px] font-medium bg-[#FFF8E8] text-[#B06000] border border-[#F3E2B5]">
                  Нужно уточнить данные
                </span>
              ) : (
                <span className="self-start sm:self-auto px-3 py-1 rounded-md text-[12px] font-medium bg-[#EEF3FE] text-[#1F4FD1]">
                  Телефонное собеседование
                </span>
              )}
            </div>

            {/* Stepper / Progress Bar (6 steps) */}
            <div className="pt-2">
              <div className="grid grid-cols-6 gap-2 mb-2">
                <div className={`h-1.5 rounded-full ${isAnswered ? 'bg-[#137333]' : 'bg-[#1F4FD1]'}`} />
                <div className={`h-1.5 rounded-full ${isAnswered ? 'bg-[#137333]' : 'bg-[#1F4FD1]'}`} />
                <div className={`h-1.5 rounded-full ${isAnswered ? 'bg-[#137333]' : 'bg-[#D97706]'}`} />
                <div className={`h-1.5 rounded-full ${isAnswered ? 'bg-[#D97706]' : 'bg-[#E1E5EB]'}`} />
                <div className="h-1.5 rounded-full bg-[#E1E5EB]" />
                <div className="h-1.5 rounded-full bg-[#E1E5EB]" />
              </div>
              <div className="grid grid-cols-6 gap-2 text-[11px] leading-tight text-[#616977]">
                <span>Отклик получен</span>
                <span>Разбор резюме</span>
                <span className={!isAnswered ? 'font-bold text-[#141A24]' : ''}>
                  Уточнение данных
                </span>
                <span className={isAnswered ? 'font-bold text-[#141A24]' : ''}>
                  Телефонное собеседование
                </span>
                <span>Решение департамента</span>
                <span>Итог</span>
              </div>
            </div>
          </div>

          {/* Card 2: Аналитик данных */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            {/* Top row */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6">
              <div>
                <h3 className="text-[18px] font-bold text-[#141A24] mb-1">
                  Аналитик данных
                </h3>
                <p className="text-[13px] text-[#616977]">
                  Департамент цифрового развития · отклик от 02.11.2026
                </p>
              </div>
              <span className="self-start sm:self-auto px-3 py-1 rounded-md text-[12px] font-medium bg-[#FCE8E6] text-[#C5221F]">
                Не подходит
              </span>
            </div>

            {/* Stepper / Progress Bar (6 steps) */}
            <div className="pt-2 mb-5">
              <div className="grid grid-cols-6 gap-2 mb-2">
                <div className="h-1.5 rounded-full bg-[#137333]" />
                <div className="h-1.5 rounded-full bg-[#137333]" />
                <div className="h-1.5 rounded-full bg-[#137333]" />
                <div className="h-1.5 rounded-full bg-[#137333]" />
                <div className="h-1.5 rounded-full bg-[#C5221F]" />
                <div className="h-1.5 rounded-full bg-[#E1E5EB]" />
              </div>
              <div className="grid grid-cols-6 gap-2 text-[11px] leading-tight text-[#616977]">
                <span>Отклик получен</span>
                <span>Разбор резюме</span>
                <span>Уточнение данных</span>
                <span>Телефонное собеседование</span>
                <span className="font-bold text-[#141A24]">Решение департамента</span>
                <span>Итог</span>
              </div>
            </div>

            {/* Reason callout */}
            <div className="bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl p-4 text-[13px] text-[#334155] mb-4">
              Причина от департамента: нужна другая специализация (BI-аналитика). Спасибо за отклик!
            </div>

            {/* Match recommendation banner */}
            <div className="bg-[#F1EDFF] border border-[#DDD6FE] rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <span className="text-[14px] font-medium text-[#4C1D95]">
                Вам подойдёт вакансия «Тестировщик ПО»: совпадение 82%
              </span>
              <button
                type="button"
                onClick={onGoVacancy}
                className="px-5 py-2 bg-white border border-[#E1E5EB] rounded-lg text-[13px] font-medium text-[#141A24] hover:bg-[#F3F5F8] transition-colors whitespace-nowrap shadow-sm self-start sm:self-auto"
              >
                Посмотреть
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Мои документы, Согласия, Тесты для отбора (4 cols) */}
        <div className="lg:col-span-4 space-y-6">
          {/* Block 1: Мои документы */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            <h2 className="text-[16px] font-bold text-[#141A24] mb-4">
              Мои документы
            </h2>
            <div className="space-y-3.5 text-[13px]">
              {/* Item 1 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <span className="bg-[#F1F3F5] text-[#4A5363] text-[11px] font-bold px-1.5 py-0.5 rounded">
                    PDF
                  </span>
                  <span className="text-[#141A24] font-medium">Резюме</span>
                </div>
                <span className="text-[12px] font-medium text-[#137333]">
                  Загружено
                </span>
              </div>

              {/* Item 2 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <span className="bg-[#F1F3F5] text-[#4A5363] text-[11px] font-bold px-1.5 py-0.5 rounded">
                    PDF
                  </span>
                  <span className="text-[#141A24] font-medium">
                    Диплом о высшем образовании
                  </span>
                </div>
                <span className="text-[12px] font-medium text-[#137333]">
                  Загружено
                </span>
              </div>

              {/* Item 3 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <span className="text-[#8E939D] font-bold px-1">—</span>
                  <span className="text-[#141A24] font-medium">
                    Анкета (форма 667-р)
                  </span>
                </div>
                <span className="text-[12px] font-medium text-[#B06000]">
                  Нужно заполнить
                </span>
              </div>
            </div>

            <button
              type="button"
              className="w-full mt-5 py-2.5 text-[13px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors"
            >
              Загрузить документ
            </button>
          </div>

          {/* Block 2: Согласия */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            <h2 className="text-[16px] font-bold text-[#141A24] mb-2">
              Согласия
            </h2>
            <p className="text-[13px] text-[#616977] leading-relaxed">
              Согласие на обработку персональных данных дано 18.11.2026. Отозвать можно в любой момент.
            </p>
          </div>

          {/* Block 3: Тесты для отбора */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-[16px] font-bold text-[#141A24]">
                Тесты для отбора
              </h2>
              <span className="text-[13px] text-[#616977]">
                0 из 3
              </span>
            </div>

            <p className="text-[13px] text-[#4A5363] leading-relaxed mb-4">
              Для вакансии «Python-разработчик» нужно пройти 3 коротких теста. Результаты увидит Сотрудник по подбору персонала, они дополняют резюме, но не решают за вас.
            </p>

            <div className="space-y-3 mb-4">
              <div className="flex items-center justify-between p-3 rounded-xl border border-[#E1E5EB] hover:border-[#1F4FD1] transition-colors">
                <div>
                  <h3 className="text-[14px] font-bold text-[#141A24]">
                    Тест Равена
                  </h3>
                  <p className="text-[12px] text-[#616977]">
                    логика · 25 минут
                  </p>
                </div>
                <button
                  type="button"
                  className="px-4 py-1.5 text-[13px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors"
                >
                  Начать
                </button>
              </div>

              <div className="flex items-center justify-between p-3 rounded-xl border border-[#E1E5EB] hover:border-[#1F4FD1] transition-colors">
                <div>
                  <h3 className="text-[14px] font-bold text-[#141A24]">
                    Системное мышление
                  </h3>
                  <p className="text-[12px] text-[#616977]">
                    10 вопросов · 15 минут
                  </p>
                </div>
                <button
                  type="button"
                  className="px-4 py-1.5 text-[13px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors"
                >
                  Начать
                </button>
              </div>

              <div className="flex items-center justify-between p-3 rounded-xl border border-[#E1E5EB] hover:border-[#1F4FD1] transition-colors">
                <div>
                  <h3 className="text-[14px] font-bold text-[#141A24]">
                    Стратегическое планирование
                  </h3>
                  <p className="text-[12px] text-[#616977]">
                    10 вопросов · 15 минут
                  </p>
                </div>
                <button
                  type="button"
                  className="px-4 py-1.5 text-[13px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors"
                >
                  Начать
                </button>
              </div>
            </div>

            <p className="text-[12px] text-[#616977] leading-tight">
              Пройти до 27.11.2026 · можно делать перерывы между тестами
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CandidateCabinetPage;
