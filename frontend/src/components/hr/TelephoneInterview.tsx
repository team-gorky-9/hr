import React, { useState } from 'react';

interface TelephoneInterviewProps {
  onBackToCard?: () => void;
  onSaveResult?: (result: string) => void;
}

export const TelephoneInterview: React.FC<TelephoneInterviewProps> = ({
  onBackToCard,
  onSaveResult,
}) => {
  const [selectedOutcome, setSelectedOutcome] = useState<'fit' | 'clarify' | 'unfit'>('fit');
  const [questions, setQuestions] = useState([
    {
      id: 1,
      text: 'Расскажите, где и сколько лет вы работали разработчиком.',
      hint: 'В резюме нет длительности опыта',
      checked: true,
      note: '',
      notePlaceholder: 'Заметка HR-менеджера',
    },
    {
      id: 2,
      text: 'Какие API-тесты вы писали для сервиса заявок? Какой инструмент использовали?',
      hint: 'Проверка компетенции «Тестирование API»',
      checked: true,
      note: '',
      notePlaceholder: 'Заметка HR-менеджера',
    },
    {
      id: 3,
      text: 'Был ли опыт с PostgreSQL? Приведите пример задачи.',
      hint: 'Желательное требование, в резюме не упоминается',
      checked: false,
      note: '',
      notePlaceholder: 'Заметка',
    },
    {
      id: 4,
      text: 'Почему вас интересует муниципальная служба?',
      hint: 'Мотивация кандидата',
      checked: false,
      note: '',
      notePlaceholder: 'Заметка',
    },
  ]);

  const toggleCheck = (id: number) => {
    setQuestions((prev) =>
      prev.map((q) => (q.id === id ? { ...q, checked: !q.checked } : q))
    );
  };

  const handleNoteChange = (id: number, note: string) => {
    setQuestions((prev) =>
      prev.map((q) => (q.id === id ? { ...q, note } : q))
    );
  };

  const handleAddQuestion = () => {
    setQuestions((prev) => [
      ...prev,
      {
        id: Date.now(),
        text: '',
        hint: '',
        checked: false,
        note: '',
        notePlaceholder: 'Заметка',
      },
    ]);
  };

  const checkedCount = questions.filter((q) => q.checked).length;

  const handleSave = () => {
    const outcomeText =
      selectedOutcome === 'fit'
        ? 'Подходит'
        : selectedOutcome === 'clarify'
        ? 'Нужно ещё уточнить'
        : 'Не подходит';
    onSaveResult?.(outcomeText);
  };

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-6">
      {/* Back Link */}
      <div className="mb-5">
        <button
          type="button"
          onClick={onBackToCard}
          className="text-[14px] font-medium text-[#1F4FD1] hover:underline flex items-center gap-1.5 transition-colors whitespace-nowrap"
        >
          ← Карточка Фролов Денис
        </button>
      </div>

      {/* Main Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Вопросы и заметки (8 cols) */}
        <div className="lg:col-span-8 bg-white border border-[#E1E5EB] rounded-2xl p-6 sm:p-8 shadow-sm space-y-6">
          <h2 className="text-[18px] font-bold text-[#141A24]">
            Вопросы и заметки
          </h2>

          <div className="space-y-5">
            {questions.map((q) => (
              <div key={q.id} className="space-y-2.5">
                <div className="flex items-start gap-3">
                  <button
                    type="button"
                    onClick={() => toggleCheck(q.id)}
                    className={`mt-0.5 w-5 h-5 rounded flex items-center justify-center shrink-0 transition-colors ${
                      q.checked
                        ? 'bg-[#1F4FD1] text-white'
                        : 'border border-[#C5CAD3] bg-white hover:border-[#1F4FD1]'
                    }`}
                  >
                    {q.checked && (
                      <svg
                        className="w-3.5 h-3.5 fill-current"
                        viewBox="0 0 20 20"
                      >
                        <path d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" />
                      </svg>
                    )}
                  </button>
                  <div className="flex-1">
                    <div className="text-[14px] sm:text-[15px] font-bold text-[#141A24] leading-snug">
                      {q.text}
                    </div>
                    {q.hint && (
                      <div className="text-[13px] text-[#616977] mt-1">
                        {q.hint}
                      </div>
                    )}
                  </div>
                </div>

                <div className="pl-8">
                  <input
                    type="text"
                    placeholder={q.notePlaceholder}
                    value={q.note}
                    onChange={(e) => handleNoteChange(q.id, e.target.value)}
                    className="w-full px-4 py-2.5 text-[14px] border border-[#D2D4D8] rounded-xl bg-white text-[#141A24] placeholder-[#8E939D] focus:outline-none focus:border-[#1F4FD1]"
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="pt-2">
            <button
              type="button"
              onClick={handleAddQuestion}
              className="px-5 py-2.5 text-[14px] font-medium text-[#141A24] bg-white border border-[#D2D4D8] rounded-xl hover:bg-[#F8FAFC] transition-colors shadow-sm whitespace-nowrap"
            >
              Добавить свой вопрос
            </button>
          </div>
        </div>

        {/* Right Column: Итог интервью (4 cols) */}
        <div className="lg:col-span-4 bg-white border border-[#E1E5EB] rounded-2xl p-6 sm:p-7 shadow-sm">
          <h2 className="text-[18px] font-bold text-[#141A24] mb-1">
            Итог интервью
          </h2>
          <p className="text-[14px] text-[#616977] mb-5">
            Задано вопросов: {checkedCount} из {questions.length}
          </p>

          <div className="space-y-3 mb-6">
            <button
              type="button"
              onClick={() => setSelectedOutcome('fit')}
              className={`w-full text-left p-4 rounded-xl transition-all ${
                selectedOutcome === 'fit'
                  ? 'border-2 border-[#137333] bg-[#E6F4EA] font-semibold text-[#141A24]'
                  : 'border border-[#E1E5EB] bg-white hover:bg-[#F8FAFC] text-[#141A24]'
              }`}
            >
              <div className="text-[14px] font-medium">Подходит</div>
            </button>

            <button
              type="button"
              onClick={() => setSelectedOutcome('clarify')}
              className={`w-full text-left p-4 rounded-xl transition-all ${
                selectedOutcome === 'clarify'
                  ? 'border-2 border-[#137333] bg-[#E6F4EA] font-semibold text-[#141A24]'
                  : 'border border-[#E1E5EB] bg-white hover:bg-[#F8FAFC] text-[#141A24]'
              }`}
            >
              <div className="text-[14px] font-medium">Нужно ещё уточнить</div>
            </button>

            <button
              type="button"
              onClick={() => setSelectedOutcome('unfit')}
              className={`w-full text-left p-4 rounded-xl transition-all ${
                selectedOutcome === 'unfit'
                  ? 'border-2 border-[#137333] bg-[#E6F4EA] font-semibold text-[#141A24]'
                  : 'border border-[#E1E5EB] bg-white hover:bg-[#F8FAFC] text-[#141A24]'
              }`}
            >
              <div className="text-[14px] font-medium">Не подходит</div>
            </button>
          </div>

          <button
            type="button"
            onClick={handleSave}
            className="w-full py-3 px-4 text-[15px] font-semibold text-white bg-[#1F4FD1] rounded-xl hover:bg-[#1841B2] transition-colors shadow-sm text-center"
          >
            Сохранить итог
          </button>
        </div>
      </div>
    </div>
  );
};

export default TelephoneInterview;
