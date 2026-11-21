import { useEffect, useState } from 'react';
import { ApiError, api, errorMessage, type CrossAssessmentItem, type Guide } from '../../api/recruitment';

export const profilePanel = 'bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm';
export const profileTitle = 'text-[16px] font-bold text-[#141A24]';

export function ProfileQuestions({ applicationId, canReadGuide, onInterview }: {
  applicationId: string; canReadGuide: boolean; onInterview?: () => void;
}) {
  const [guide, setGuide] = useState<Guide | null>(null);
  const [loading, setLoading] = useState(canReadGuide);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!canReadGuide) return;
    let live = true;
    setGuide(null); setLoading(true); setError('');
    api.guide(applicationId)
      .then(value => { if (live) setGuide(value); })
      .catch(error => {
        if (live && !(error instanceof ApiError && error.code === 'GUIDE_NOT_FOUND')) setError(errorMessage(error));
      })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [applicationId, canReadGuide]);

  const questions = guide ? [...guide.core, ...guide.clarifications] : [];
  return <div className={profilePanel}>
    <h2 className={profileTitle + ' mb-4'}>Черновик вопросов к телефонному интервью</h2>
    <div className="space-y-2 text-[13px] text-[#334155] leading-relaxed mb-4">
      {loading && canReadGuide ? <div>Загрузка вопросов…</div> : error ? <div role="alert">{error}</div>
        : questions.length ? questions.map((question, index) =>
          <div key={question.question_id}>{index + 1}. {question.question}</div>)
          : <div>{canReadGuide ? 'Вопросы ещё не сформированы.' : 'Будет добавлено позже'}</div>}
    </div>
    <p className="text-[12px] text-[#616977]">
      {guide?.is_stale && 'Вопросы по прежней оценке. '}
      {onInterview && <button type="button" onClick={onInterview} className="hover:text-[#1F4FD1] hover:underline transition-colors">
        {guide ? 'Открыть телефонное интервью' : 'Открыть интервью и сформировать вопросы'}
      </button>}
    </p>
  </div>;
}

const tests = [
  { title: 'Тест Равена', tone: 'bg-[#E6F4EA] text-[#15803D]' },
  { title: 'Системное мышление', tone: 'bg-[#FEF3E6] text-[#B45309]' },
  { title: 'Стратегическое планирование', tone: 'bg-[#FEF3E6] text-[#B45309]' },
];

export function ProfilePsychology() {
  return <div className={profilePanel}>
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
      <h2 className={profileTitle}>Психологическое тестирование</h2>
      <span className="text-[12px] text-[#616977]">Будет добавлено позже</span>
    </div>
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
      {tests.map(test => <div key={test.title} className="bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl p-4">
        <div className="text-[12px] text-[#616977] mb-1">{test.title}</div>
        <div className="text-[22px] font-bold text-[#141A24] mb-2 leading-none">—</div>
        <span className={`inline-block px-2.5 py-0.5 rounded-full text-[11px] font-medium whitespace-nowrap ${test.tone}`}>Нет данных</span>
      </div>)}
    </div>
    <p className="text-[12px] text-[#616977]">Тип личности · нет данных</p>
  </div>;
}

export function ProfileOtherVacancies({ candidateId, currentPosition, currentVacancy }: {
  candidateId: string; currentPosition: string | undefined; currentVacancy: string | undefined;
}) {
  const [items, setItems] = useState<CrossAssessmentItem[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setItems(null); setError('');
    api.crossAssessments(candidateId, controller.signal)
      .then(result => { if (!controller.signal.aborted) setItems(result.items); })
      .catch(error => { if (!controller.signal.aborted) setError(errorMessage(error)); });
    return () => controller.abort();
  }, [candidateId]);

  const recommendations = items?.flatMap(item => {
    if (item.position_code === currentPosition || item.assessment_status !== 'ready' || item.assessment?.formal_result !== 'met') return [];
    return item.vacancies.filter(vacancy => vacancy.status === 'open' && vacancy.vacancy_id !== currentVacancy).map(vacancy => ({
      ...vacancy,
      label: item.assessment?.formal_preliminary ? 'Предварительно' : 'Требования выполнены',
    }));
  });

  return <div className={profilePanel}>
    <h2 className={profileTitle + ' mb-4'}>Подходит и на другие вакансии</h2>
    <div className="space-y-3">
      {error ? <div role="alert" className="text-[13px] text-[#616977]">{error}</div>
        : recommendations === undefined ? <div className="text-[13px] text-[#616977]">Загрузка оценок…</div>
        : !recommendations.length ? <div className="text-[13px] text-[#616977]">Подтверждённых совпадений с другими открытыми вакансиями пока нет.</div>
        : recommendations.map(item => <div key={item.vacancy_id} className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <span className="bg-[#EEF3FE] text-[#1F4FD1] text-[12px] font-medium px-2 py-0.5 rounded">{item.label}</span>
            <span className="text-[14px] font-medium text-[#141A24]">{item.title}</span>
          </div>
          <button type="button" disabled title="Предложить вакансию · будет добавлено позже"
            className="text-[13px] font-medium text-[#1F4FD1] hover:underline">
            Будет добавлено позже
          </button>
        </div>)}
    </div>
  </div>;
}
