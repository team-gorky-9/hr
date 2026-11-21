import React, { useEffect, useState } from 'react';
import { api, recruitmentContour, resultLabel, errorMessage, type Vacancy } from '../../api/recruitment';

export interface ResponseItem {
  id: string;
  name: string;
  code: string;
  headline: string | null;
  source: string;
  requirementExp: 'Выполнено' | 'Нужно уточнить' | 'Не выполнено' | 'Не оценено';
  skillApi: string;
  category: 'call' | 'clarify' | 'reject' | 'action';
}

interface VacancyResponsesProps {
  initialVacancyId?: string;
  onOpenCard?: (applicationId: string, vacancyId: string) => void;
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
  initialVacancyId = '',
  onOpenCard,
  onManualUpload: _onManualUpload,
}) => {
  const [selectedVacancyId, setSelectedVacancyId] = useState<string>(initialVacancyId);
  const [activeFilter, setActiveFilter] = useState<FilterTab>('all');

  const [vacancyRows, setVacancyRows] = useState<Vacancy[]>([]);
  const [responses, setResponses] = useState<ResponseItem[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError(''); setLoading(true);
    api.vacancies(controller.signal).then(({ items }) => {
      setVacancyRows(items);
      setSelectedVacancyId(current => items.some(v => v.vacancy_id === current) ? current : (items.find(v => v.applications_count > 0) || items[0])?.vacancy_id || '');
      if (!items.length) setLoading(false);
    }).catch(e => { if (!controller.signal.aborted) { setError(errorMessage(e)); setLoading(false); } });
    return () => controller.abort();
  }, [reload]);
  useEffect(() => {
    if (!selectedVacancyId) return;
    const controller = new AbortController();
    setResponses([]); setError(''); setLoading(true);
    api.applications(selectedVacancyId, controller.signal).then(({ items }) => {
      setResponses(items.map(a => ({ id: a.application_id, name: a.full_name?.trim() || a.candidate_code, code: a.candidate_code, headline: a.headline, source: [a.current_stage_title, a.applied_at].filter(Boolean).join(' · '), requirementExp: resultLabel(a.formal_result) as ResponseItem['requirementExp'], skillApi: a.rank_reason, category: ({ ready: 'call', clarify: 'clarify', not_met: 'reject' }[a.rank_group] || 'action') as ResponseItem['category'] })));
      setLoading(false);
    }).catch(e => { if (!controller.signal.aborted) { setError(errorMessage(e)); setLoading(false); } });
    return () => controller.abort();
  }, [selectedVacancyId, reload]);
  const vacancies = vacancyRows.map(v => ({ id: v.vacancy_id, title: v.title, department: v.employer, count: `${v.applications_count} откликов`, requirement: v.approved_profile_version ? `профиль v${v.approved_profile_version}` : 'нет утверждённого профиля', hasResponses: responses.length > 0 }));
  const currentVacancy = vacancies.find(v => v.id === selectedVacancyId);
  const filteredResponses = responses.filter(r => activeFilter === 'all' || r.category === activeFilter);
  if (!currentVacancy) return <div className="max-w-[1240px] mx-auto p-8"><h1 className="text-3xl font-bold mb-4">Отклики</h1><p>{error || (loading ? 'Загрузка вакансий…' : 'Вакансий пока нет')}</p><button className="mt-4 text-[#1F4FD1]" onClick={() => setReload(n => n + 1)}>Обновить</button></div>;

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-6">
      {/* Page Title & Subtitle */}
      <div className="mb-6">
        <h1 className="text-[28px] sm:text-[32px] font-bold text-[#141A24] tracking-tight mb-1.5">
          Отклики
        </h1>
        <p className="text-[14px] text-[#616977]">
          {recruitmentContour === 'training' ? 'Учебные данные · ' : ''}Выберите вакансию и откройте отклик. Имена доступны кадровику.
        </p>
      </div>

      {/* Two Column Layout */}
      <div data-tour="hr-responses-board" className="flex flex-col lg:flex-row gap-6 items-start">
        {/* Left Column: Vacancies List Card */}
        <div className="w-full lg:w-[260px] lg:max-h-[calc(100dvh-320px)] overflow-y-auto shrink-0 bg-white border border-[#E1E5EB] rounded-2xl p-4 sm:p-5 shadow-sm">
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
                  <div title={v.title} className="text-[16px] font-bold text-[#141A24] mb-1 leading-snug line-clamp-3 break-words">
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
        <div className="flex-1 min-w-0 bg-white border border-[#E1E5EB] rounded-2xl p-4 sm:p-6 shadow-sm">
          {/* Vacancy Header */}
          <div className="mb-6">
            <h2 title={currentVacancy.title} className="text-[24px] font-bold text-[#141A24] mb-1 break-words line-clamp-2">
              {currentVacancy.title}
            </h2>
            <p className="text-[14px] text-[#616977]">
              {currentVacancy.department} · {currentVacancy.requirement}
            </p>
          </div>

          {error && <div role="alert" className="mb-4 p-4 bg-red-50 text-red-800 rounded-xl">{error} <button onClick={() => setReload(n => n + 1)}>Повторить</button></div>}
          {loading && <p className="mb-4">Загрузка откликов…</p>}
          {!loading && !error && currentVacancy.hasResponses ? (
            <>
              {/* Horizontal Filter Tabs / Chips */}
              <div data-tour="hr-responses-traffic-light" className="flex items-center gap-3.5 lg:gap-4 border-b border-[#E1E5EB] mb-6 overflow-x-auto">
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
                    {responses.length}
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
                    {responses.filter(r => r.category === 'call').length}
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
                    {responses.filter(r => r.category === 'clarify').length}
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
                    {responses.filter(r => r.category === 'reject').length}
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
                    {responses.filter(r => r.category === 'action').length}
                  </span>
                  {activeFilter === 'action' && (
                    <div className="absolute bottom-0 left-0 right-0 h-[2.5px] bg-[#1F4FD1] rounded-full" />
                  )}
                </button>
              </div>

              {/* Responses Table Container */}
              <div className="border border-[#E1E5EB] rounded-2xl overflow-hidden bg-white">
                <div className="max-h-[calc(100dvh-530px)] min-h-[180px] overflow-y-auto">
                  <table className="w-full table-fixed text-left text-[14px]"><colgroup><col className="w-[30%]"/><col className="w-[20%]"/><col className="w-[34%]"/><col className="w-[16%]"/></colgroup>
                    <thead className="border-b border-[#E1E5EB] text-[13px] text-[#4A5363] font-semibold bg-white">
                      <tr>
                        <th className="sticky top-0 bg-[#F8FAFC] py-3 pl-3 pr-2 font-semibold w-[30%] break-words">
                          Отклик
                        </th>
                        <th className="sticky top-0 bg-[#F8FAFC] py-3 px-2 font-semibold break-words">
                          Формальные требования
                        </th>
                        <th className="sticky top-0 bg-[#F8FAFC] py-3 px-2 font-semibold break-words">
                          Основание группы
                        </th>
                        <th className="py-3 pl-2 pr-3 text-right"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E1E5EB]">
                      {filteredResponses.map((r) => (
                        <tr key={r.id} className="hover:bg-[#F8FAFC] transition-colors">
                          {/* Col 1: Кандидат и источник */}
                          <td className="py-3 pl-3 pr-2 break-words">
                            <div className="text-[15px] font-bold text-[#1F4FD1] leading-snug">
                              {r.name}
                            </div>
                            <div className="text-[13px] text-[#616977] mt-0.5">
                              {r.code !== r.name && <span className="block">{r.code}</span>}{r.headline && <span className="block break-words">{r.headline}</span>}{r.source}
                            </div>
                          </td>

                          {/* Col 2: Формальные требования (бейдж) */}
                          <td className="py-3 px-2 break-words">
                            <span
                              className={`inline-block px-2 py-1 rounded-md text-[13px] font-medium ${
                                requirementExpStyles[r.requirementExp] || 'bg-[#F1F3F5] text-[#616977]'
                              }`}
                            >
                              {r.requirementExp}
                            </span>
                          </td>

                          {/* Col 3: Основание группы */}
                          <td className="py-3 px-2 text-[#141A24] text-[14px] break-words [overflow-wrap:anywhere]">
                            {r.skillApi}
                          </td>

                          {/* Col 4: Кнопка «Открыть» */}
                          <td className="py-3 pl-2 pr-3 text-right">
                            <button
                              type="button"
                              onClick={() => onOpenCard?.(r.id, selectedVacancyId)}
                              className="px-2 py-2 text-[13px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-xl hover:bg-[#F8FAFC] transition-colors shadow-sm whitespace-nowrap"
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
          ) : !loading && !error ? (
            /* Пустой список для вакансии без откликов */
            <div className="border-2 border-dashed border-[#D2D4D8] rounded-2xl p-8 lg:p-10 flex flex-col items-start">
              <h3 className="text-[18px] font-bold text-[#141A24] mb-2">
                Откликов пока нет
              </h3>
              <p className="text-[14px] text-[#616977] max-w-xl leading-relaxed mb-6">
                Для выбранной вакансии в этом контуре нет откликов.
              </p>
              {_onManualUpload && <button
                type="button"
                onClick={_onManualUpload}
                className="px-5 py-2.5 text-[14px] font-medium text-[#141A24] bg-white border border-[#D2D4D8] rounded-xl hover:bg-[#F8FAFC] transition-colors shadow-sm"
              >
                Загрузить отклик вручную
              </button>}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};

export default VacancyResponses;
