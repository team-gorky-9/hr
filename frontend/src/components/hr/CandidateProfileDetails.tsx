import { ApiError, api, type Guide } from '../../api/recruitment';
import { useEffect, useState } from 'react';

export const profilePanel = 'bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm';
export const profileTitle = 'text-[16px] font-bold text-[#141A24]';

const exampleQuestions = [
  'Расскажите, где и сколько лет вы работали разработчиком.',
  'Какие API-тесты вы писали для сервиса заявок? Какой инструмент использовали?',
  'Был ли опыт с PostgreSQL? Приведите пример задачи.',
  'Почему вас интересует работа в муниципальной службе?',
];

export function ProfileQuestions({ applicationId, canReadGuide, onInterview }: {
  applicationId: string; canReadGuide: boolean; onInterview?: () => void;
}) {
  const [guide, setGuide] = useState<Guide | null>(null);
  const [loading, setLoading] = useState(canReadGuide);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    if (!canReadGuide) return;
    let live = true;
    setGuide(null); setLoading(true); setUnavailable(false);
    api.guide(applicationId)
      .then(value => { if (live) setGuide(value); })
      .catch(error => { if (live && !(error instanceof ApiError && error.code === 'GUIDE_NOT_FOUND')) setUnavailable(true); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [applicationId, canReadGuide]);

  const questions = guide ? [...guide.core, ...guide.clarifications].map(question => question.question) : exampleQuestions;
  return <section className={profilePanel}>
    <h2 className={profileTitle + ' mb-4'}>Черновик вопросов к телефонному интервью</h2>
    {loading && canReadGuide ? <p className="text-[13px] text-[#616977]">Загрузка вопросов…</p> : <>
      {!guide && <p className="mb-2 text-[12px] text-[#616977]">
        {unavailable ? 'Не удалось загрузить вопросы кандидата. ' : 'Вопросы для этого отклика ещё не сформированы. '}
        Ниже учебный пример.
      </p>}
      {guide?.is_stale && <p className="mb-2 text-[12px] text-[#8A4B0A]">Гайд устарел. Сверьте вопросы с текущей оценкой.</p>}
      <ol className="space-y-2 text-[13px] text-[#334155] leading-relaxed mb-4 list-decimal list-inside">
        {questions.map((question, index) => <li key={index}>{question}</li>)}
      </ol>
    </>}
    {onInterview && <button type="button" onClick={onInterview} className="text-[13px] font-medium text-[#1F4FD1] hover:underline">
      Телефонное интервью
    </button>}
  </section>;
}

const tests = [
  { title: 'Тест Равена', score: '48 из 60', label: 'Выше среднего', tone: 'bg-[#E6F4EA] text-[#15803D]' },
  { title: 'Системное мышление', score: '7 из 10', label: 'Средний', tone: 'bg-[#FEF3E6] text-[#B45309]' },
  { title: 'Стратегическое планирование', score: '6 из 10', label: 'Средний', tone: 'bg-[#FEF3E6] text-[#B45309]' },
];

export function ProfilePsychology() {
  return <section className={profilePanel}>
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
      <h2 className={profileTitle}>Психологическое тестирование</h2>
      <span className="text-[12px] text-[#616977]">Набор для уровня «ведущая должность» · учебный пример</span>
    </div>
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
      {tests.map(test => <div key={test.title} className="bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl p-4">
        <div className="text-[12px] text-[#616977] mb-1">{test.title}</div>
        <div className="text-[22px] font-bold text-[#141A24] mb-2 leading-none">{test.score}</div>
        <span className={`inline-block px-2.5 py-0.5 rounded-full text-[11px] font-medium whitespace-nowrap ${test.tone}`}>{test.label}</span>
      </div>)}
    </div>
    <p className="text-[12px] text-[#616977]">Тип личности в примере: аналитик · вывод носит вспомогательный характер</p>
  </section>;
}

export function ProfileOtherVacancies() {
  return <section className={profilePanel}>
    <h2 className={profileTitle + ' mb-1'}>Подходит и на другие вакансии</h2>
    <p className="text-[12px] text-[#616977] mb-4">Учебный пример</p>
    <div className="space-y-3">
      {[{ title: 'Тестировщик ПО', score: '82%' }, { title: 'Аналитик данных', score: '74%' }].map(item =>
        <div key={item.title} className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <span className="bg-[#EEF3FE] text-[#1F4FD1] text-[12px] font-medium px-2 py-0.5 rounded">{item.score}</span>
            <span className="text-[14px] font-medium text-[#141A24]">{item.title}</span>
          </div>
          <button type="button" disabled title="Предложить вакансию" className="text-[13px] font-medium text-[#1F4FD1]">
            Будет добавлено позже
          </button>
        </div>)}
    </div>
  </section>;
}
