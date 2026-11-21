import { useEffect, useState } from 'react';
import { api, errorMessage, stageLabel } from '../../api/recruitment';
import { Badge, Btn, Card, PageTitle } from '../shared/ui';
import CandidateCard from './CandidateCard';
import type { CandidateRecord } from './CandidatesDatabase';

interface CandidateProfileProps {
  candidate: CandidateRecord;
  selectedApplicationId?: string;
  onBackToDatabase?: () => void;
  onOpenInterview?: (applicationId: string) => void;
  onOpenReserve?: () => void;
}

export default function CandidateProfile({ candidate, selectedApplicationId, onBackToDatabase, onOpenInterview, onOpenReserve }: CandidateProfileProps) {
  const [selected, setSelected] = useState(selectedApplicationId || candidate.applicationId);
  const [source, setSource] = useState<{ text: string; version: number } | null>(null);
  const [sourceError, setSourceError] = useState('');
  const applicationId = candidate.applications.some(row => row.application_id === selected) ? selected : candidate.applicationId;

  useEffect(() => {
    if (applicationId || !candidate.current_text_id) return;
    let active = true;
    setSource(null); setSourceError('');
    api.source(candidate.current_text_id).then(value => { if (active) setSource(value); })
      .catch(error => { if (active) setSourceError(errorMessage(error)); });
    return () => { active = false; };
  }, [applicationId, candidate.current_text_id]);

  if (applicationId) return <CandidateCard key={applicationId} candidateId={applicationId} backLabel="Единая база" databaseProfile
    profileApplication={candidate.applications.find(item => item.application_id === applicationId)} profileChannel={candidate.channel}
    onBack={onBackToDatabase} onOpenArchive={onOpenReserve} onRequestClarification={onOpenInterview ? () => onOpenInterview(applicationId) : undefined}
    context={candidate.applications.length > 1 && <label className="block max-w-lg font-medium text-sm">
      Рассмотрение
      <select className="mt-1 w-full rounded-xl border border-[#C9D0DB] bg-white px-4 py-2.5" value={applicationId} onChange={e => setSelected(e.target.value)}>
        {candidate.applications.map(item => <option key={item.application_id} value={item.application_id}>
          {item.vacancy_title} · {stageLabel(item.stage_title)}{item.applied_at && ' · ' + item.applied_at}
        </option>)}
      </select>
    </label>} />;

  return <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-6 space-y-5">
    <Btn variant="link" onClick={onBackToDatabase}>← Единая база</Btn>
    <Card><PageTitle title={candidate.candidate_code} subtitle={candidate.headline || 'Резюме без отклика'} right={candidate.is_training && <Badge>Учебная запись</Badge>} /></Card>
    <Card className="space-y-3">
      <h2 className="text-xl font-bold">Текст источника</h2>
      {sourceError ? <p role="alert">{sourceError}</p> : source
        ? <><p className="text-sm text-[#616977]">Версия {source.version}</p><p className="whitespace-pre-wrap break-words">{source.text}</p></>
        : <p>{candidate.current_text_id ? 'Загрузка источника…' : 'Доступного текста нет.'}</p>}
      {onOpenReserve && <Btn variant="link" onClick={onOpenReserve}>Открыть архив кадров</Btn>}
    </Card>
  </div>;
}
