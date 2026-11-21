import React, { useEffect, useState } from 'react';
import { api, deadlineLabel, errorMessage, type CandidateRow, type Handoff, type Vacancy } from '../../api/recruitment';
import { Badge, Btn } from '../shared/ui';

export interface CandidateRecord extends CandidateRow {
  id: string;
  candidateId: string;
  applicationId: string | null;
  vacancyId: string | null;
}

interface CandidatesDatabaseProps {
  vacancyId?: string;
  onVacancyChange?: (vacancyId: string) => void;
  onSelectCandidate?: (candidate: CandidateRecord) => void;
  onUploadResume?: () => void;
}

const channelLabels: Record<string, string> = {
  hh_ru: 'HH.ru', rabota_rossii: '«Работа России»', city_site: 'Сайт администрации',
  email: 'Электронная почта', citizen_appeal: 'Обращение гражданина',
  internship: 'Практика', internal: 'Внутренний', other: 'Другой источник',
};

function candidateType(candidate: CandidateRecord) {
  const application = candidate.applications.find(item => item.application_id === candidate.applicationId);
  if (application?.source === 'response') return 'Внешний отклик';
  if (application?.source === 'history') return 'История откликов';
  if (application?.source === 'manual') return 'Рассмотрение HR';
  return 'Резюме';
}

function ResponseDeadline({ attempt }: { attempt?: Handoff }) {
  if (!attempt) return <span className="text-[#616977]">Передачи нет</span>;
  const tone = { overdue: 'red', due_soon: 'amber', responded: 'green', on_track: 'blue' } as const;
  const daysLeft = attempt.business_days_left;
  const showProgress = attempt.status === 'awaiting_response' && daysLeft !== null && !attempt.extensions_count;
  const progress = daysLeft === null ? 0 : Math.max(0, Math.min(attempt.deadline_business_days, attempt.deadline_business_days - daysLeft));
  return <div className="space-y-1">
    <Badge tone={tone[attempt.deadline_status as keyof typeof tone]}>{deadlineLabel(attempt.deadline_status)}</Badge>
    {attempt.status === 'awaiting_response' && <div className="text-xs text-[#4A5363]">
      {attempt.overdue_notice || (daysLeft !== null && daysLeft > 0 ? `Осталось ${daysLeft} раб. дн.` : 'Срок сегодня')} · до {attempt.due_date}
      {attempt.extensions_count > 0 && ' · срок перенесён'}
    </div>}
    {showProgress && <progress aria-label="Прошло рабочих дней" className="h-1.5 w-28 accent-[#1F4FD1]" max={attempt.deadline_business_days} value={progress} />}
  </div>;
}

export const CandidatesDatabase: React.FC<CandidatesDatabaseProps> = ({
  vacancyId: controlledVacancy, onVacancyChange, onSelectCandidate, onUploadResume,
}) => {
  const [localVacancy, setLocalVacancy] = useState('');
  const vacancyId = controlledVacancy ?? localVacancy;
  const [vacancies, setVacancies] = useState<Vacancy[]>([]);
  const [rows, setRows] = useState<CandidateRow[]>([]);
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [sourceFilter, setSourceFilter] = useState<string[] | null>(null);
  const [activeType, setActiveType] = useState('Все');
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [deadlineLoading, setDeadlineLoading] = useState(true);
  const [error, setError] = useState('');
  const [deadlineError, setDeadlineError] = useState('');
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    api.vacancies(controller.signal)
      .then(({ items }) => { if (!controller.signal.aborted) setVacancies(items); })
      .catch(error => { if (!controller.signal.aborted) setError(errorMessage(error)); });
    return () => controller.abort();
  }, [reload]);

  useEffect(() => {
    const controller = new AbortController();
    let loadingDeadlines = false;
    const load = () => {
      if (controller.signal.aborted || loadingDeadlines) return;
      loadingDeadlines = true;
      api.staffHandoffs(vacancyId, controller.signal).then(({ items }) => {
        if (!controller.signal.aborted) { setHandoffs(items); setDeadlineError(''); }
      }).catch(error => { if (!controller.signal.aborted) { setHandoffs([]); setDeadlineError(errorMessage(error)); } })
        .finally(() => {
          loadingDeadlines = false;
          if (!controller.signal.aborted) setDeadlineLoading(false);
        });
    };
    setLoading(true); setDeadlineLoading(true); setError(''); setDeadlineError(''); setRows([]); setHandoffs([]);
    api.candidates(vacancyId, controller.signal)
      .then(({ items }) => { if (!controller.signal.aborted) setRows(items); })
      .catch(error => { if (!controller.signal.aborted) setError(errorMessage(error)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    load();
    window.addEventListener('focus', load);
    const deadlineTimer = window.setInterval(() => { if (!document.hidden) load(); }, 60_000);
    return () => {
      controller.abort();
      window.removeEventListener('focus', load);
      window.clearInterval(deadlineTimer);
    };
  }, [vacancyId, reload]);

  const records = rows.map((row): CandidateRecord => {
    const application = vacancyId ? row.applications.find(item => item.vacancy_id === vacancyId) : row.applications[0];
    return { ...row, id: row.candidate_id, candidateId: row.candidate_id, applicationId: application?.application_id ?? null, vacancyId: application?.vacancy_id ?? null };
  });
  const sourceCounts = new Map<string, number>();
  const typeCounts = new Map<string, number>([['Все', records.length]]);
  for (const candidate of records) {
    sourceCounts.set(candidate.channel, (sourceCounts.get(candidate.channel) ?? 0) + 1);
    const type = candidateType(candidate);
    typeCounts.set(type, (typeCounts.get(type) ?? 0) + 1);
    if (candidate.in_archive) typeCounts.set('Архив кадров', (typeCounts.get('Архив кадров') ?? 0) + 1);
  }
  const allSources = [...sourceCounts.keys()];
  const selectedSources = sourceFilter ?? allSources;
  const type = typeCounts.has(activeType) ? activeType : 'Все';
  const visible = records.filter(record => selectedSources.includes(record.channel) && (
    type === 'Все' || (type === 'Архив кадров' ? record.in_archive : candidateType(record) === type)
  ));
  const byApplication = new Map<string, Handoff>();
  for (const handoff of handoffs) {
    if (!byApplication.has(handoff.application_id)) byApplication.set(handoff.application_id, handoff);
  }

  function selectVacancy(id: string) {
    setLocalVacancy(id);
    setSourceFilter(null);
    setActiveType('Все');
    onVacancyChange?.(id);
  }

  return <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8">
    <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
      <div>
        <h1 className="text-[26px] font-bold text-[#141A24]">Единая база кандидатов</h1>
        <p className="text-[14px] text-[#616977] mt-1">Резюме, отклики и повторное рассмотрение</p>
      </div>
      {onUploadResume && <Btn variant="primary" onClick={onUploadResume}>Загрузить резюме</Btn>}
      <Btn onClick={() => setReload(n => n + 1)}>Обновить</Btn>
    </div>
    <div className="flex flex-wrap items-end gap-3 mb-4">
      <label className="block text-sm font-medium min-w-0 max-w-full">
        Вакансия
        <select aria-label="Фильтр по вакансии" value={vacancyId} onChange={e => selectVacancy(e.target.value)} className="mt-1 block w-full max-w-lg rounded-xl border border-[#C9D0DB] bg-white px-4 py-2.5">
          <option value="">Все вакансии и резюме без вакансии</option>
          {vacancies.map(vacancy => <option key={vacancy.vacancy_id} value={vacancy.vacancy_id}>{vacancy.title} · {vacancy.employer}</option>)}
        </select>
      </label>
      {vacancyId && <Btn onClick={() => selectVacancy('')}>Сбросить вакансию</Btn>}
    </div>
    <div className="flex flex-wrap gap-2 mb-4">
      {[...typeCounts].map(([label, count]) => <button key={label} type="button" aria-pressed={type === label}
        onClick={() => setActiveType(label)} className={`px-4 py-1.5 rounded-full text-[13px] font-medium border ${type === label ? 'bg-[#1F4FD1] border-[#1F4FD1] text-white' : 'bg-white border-[#E1E5EB] text-[#141A24]'}`}>{label} · {count}</button>)}
    </div>
    {allSources.length > 0 && <div className="mb-6">
      <Btn aria-expanded={sourcesOpen} onClick={() => setSourcesOpen(!sourcesOpen)}>Источники: {selectedSources.length} из {allSources.length}</Btn>
      {sourcesOpen && <div className="mt-3 bg-white border border-[#1F4FD1] rounded-2xl p-5 space-y-3">
        <div className="flex flex-wrap gap-3">
          {allSources.map(source => <label key={source} className="inline-flex gap-2 rounded-xl border border-[#E1E5EB] px-3 py-2 text-sm">
            <input type="checkbox" checked={selectedSources.includes(source)} onChange={e => setSourceFilter(e.target.checked ? [...selectedSources, source] : selectedSources.filter(item => item !== source))} />
            {channelLabels[source] || 'Другой источник'} · {sourceCounts.get(source)}
          </label>)}
        </div>
        <Btn variant="link" onClick={() => setSourceFilter(null)}>Выбрать все</Btn>
      </div>}
    </div>}
    {error && <p role="alert" className="mb-4 rounded-xl bg-red-50 p-4 text-red-800">{error}</p>}
    {deadlineError && <p role="alert" className="mb-4 rounded-xl bg-amber-50 p-4 text-amber-900">Сроки временно недоступны. {deadlineError}</p>}
    <div className="bg-white border border-[#E1E5EB] rounded-2xl shadow-sm overflow-x-auto">
      {loading ? <p className="p-5">Загрузка кандидатов…</p> : visible.length ? <table className="w-full text-left text-[14px]">
        <thead className="bg-[#FAFBFD] text-[13px] text-[#616977]">
          <tr>{['Кандидат', 'Тип', 'Источник', 'Вакансия', 'Этап', 'Срок ответа'].map(label => <th key={label} className="px-4 py-3.5 whitespace-nowrap">{label}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-[#E1E5EB]">
          {visible.map(candidate => {
            const application = candidate.applications.find(item => item.application_id === candidate.applicationId);
            return <tr key={candidate.id} className="hover:bg-[#F8FAFC]">
              <td className="px-4 py-3.5 min-w-48">
                <button type="button" disabled={!onSelectCandidate} onClick={() => onSelectCandidate?.(candidate)} className="text-[#1F4FD1] hover:underline text-left font-medium">{candidate.candidate_code}</button>
                {candidate.headline && <p className="text-sm text-[#4A5363]">{candidate.headline}</p>}
              </td>
              <td className="px-4 py-3.5 whitespace-nowrap"><Badge tone="blue">{candidateType(candidate)}</Badge>{candidate.in_archive && <span className="block text-xs mt-1">В архиве</span>}</td>
              <td className="px-4 py-3.5 whitespace-nowrap">{channelLabels[candidate.channel] || 'Другой источник'}</td>
              <td className="px-4 py-3.5 min-w-36">{application?.vacancy_title || 'Без вакансии'}{candidate.applications.length > 1 && <span className="block text-xs text-[#616977]">Всего рассмотрений: {candidate.applications.length}</span>}</td>
              <td className="px-4 py-3.5">{application?.stage_title || 'Без отклика'}</td>
              <td className="px-4 py-3.5 min-w-40">{deadlineLoading ? 'Загрузка срока…' : deadlineError ? 'Недоступно' : <ResponseDeadline attempt={application ? byApplication.get(application.application_id) : undefined} />}</td>
            </tr>;
          })}
        </tbody>
      </table> : !error && <p className="p-5">Кандидатов по выбранным условиям нет.</p>}
    </div>
  </div>;
};

export default CandidatesDatabase;
