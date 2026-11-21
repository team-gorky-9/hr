import { CandidateCard } from "./CandidateCard";

export type ActionState =
  | "idle"
  | "forward_form"
  | "forward_done"
  | "forward_expired"
  | "extend_form"
  | "reserve_form"
  | "reserve_done"
  | "reject_form"
  | "reject_done";
interface CandidateProfileProps {
  applicationId?: string;
  initialActionState?: ActionState;
  onBackToDatabase?: () => void;
  onOpenInterview?: () => void;
  onOpenReserve?: () => void;
}
// Both entry points use the same persisted application and actions.
// A profile must never manufacture a candidate or an application identifier.
export function CandidateProfile({
  applicationId,
  onBackToDatabase,
  onOpenInterview,
}: CandidateProfileProps) {
  if (!applicationId)
    return (
      <div className="max-w-[1240px] mx-auto px-6 py-8">
        <p>Выберите кандидата в единой базе.</p>
        <button className="text-[#1F4FD1] mt-3" onClick={onBackToDatabase}>
          Вернуться в базу
        </button>
      </div>
    );
  return (
    <CandidateCard
      key={applicationId}
      candidateId={applicationId}
      onBack={onBackToDatabase}
      onRequestClarification={onOpenInterview}
    />
  );
}
export default CandidateProfile;
