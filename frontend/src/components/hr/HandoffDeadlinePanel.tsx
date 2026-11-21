import { deadlineProgress, displayDay } from './handoffDeadline';
import type { ProfileHandoff } from './useProfileHandoff';

const colors = {
  on_track: { card: 'bg-[#EBF7EE] border-[#C6E7D2] text-[#166534]', bar: 'bg-[#15803D]' },
  due_soon: { card: 'bg-[#FFF8E6] border-[#F5D58A] text-[#92400E]', bar: 'bg-[#D97706]' },
  overdue: { card: 'bg-[#FCE8E8] border-[#F3B8B8] text-[#A3171B]', bar: 'bg-[#9B1C1C]' },
};

export default function HandoffDeadlinePanel({ handoff, today, onExtend }: {
  handoff: ProfileHandoff; today: string; onExtend?: () => void;
}) {
  const progress = deadlineProgress(handoff.sentOn, handoff.dueOn, today);
  const color = colors[progress.status];
  return <div className={`border rounded-xl p-4 ${color.card}`}>
    <h3 className="text-[14px] font-bold mb-1">
      {progress.status === 'overdue' ? 'Срок ответа департамента истёк'
        : progress.status === 'due_soon' ? 'Срок ответа департамента скоро истечёт'
          : `Направлен в ${handoff.department}`}
    </h3>
    <p className="text-[12px] font-medium mb-2">
      Ответственный: {handoff.recipient} · срок {progress.status === 'overdue' ? 'был' : 'ответа'} до {displayDay(handoff.dueOn)}
    </p>
    <div role="progressbar" aria-label="Срок ответа департамента" aria-valuemin={0}
      aria-valuemax={progress.total} aria-valuenow={Math.min(progress.elapsed, progress.total)}
      aria-valuetext={`Прошло ${progress.elapsed} из ${progress.total} рабочих дней`}
      className="h-[6px] rounded-full bg-black/10 overflow-hidden mb-2">
      <div className={`h-full rounded-full transition-[width] duration-300 ${color.bar}`}
        style={{ width: `${progress.percent}%` }} />
    </div>
    <p className="text-[12px] leading-relaxed">
      Прошло {progress.elapsed} из {progress.total} рабочих дней.
      {progress.status === 'overdue' ? ' Ответа пока нет.'
        : progress.status === 'due_soon' ? ' Пора напомнить ответственному об ответе.'
          : ' Ожидаем ответ департамента.'}
    </p>
    {progress.status === 'overdue' && onExtend && <button type="button" onClick={onExtend}
      className="mt-3 px-4 py-2 text-[13px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2]">
      Продлить срок
    </button>}
  </div>;
}
