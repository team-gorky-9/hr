import { Card } from '../shared/ui';

export type ReportPoint = {
  label: string;
  value: number | null;
  partial?: boolean;
};

export default function ReportBars({ title, points, color = '#1F4FD1' }: {
  title: string;
  points: ReportPoint[];
  color?: string;
}) {
  const max = points.reduce((highest, { value }) => Math.max(highest, value ?? 0), 1);

  return <Card>
    <figure>
      <figcaption className="mb-4 text-[20px] font-bold">{title}</figcaption>
      {points.length ? <ul className="space-y-3">
        {points.map(({ label, value, partial }, index) => <li key={`${label}-${index}`} className="grid grid-cols-[minmax(6rem,2fr)_minmax(3rem,3fr)_auto] items-center gap-3 text-[14px]">
          <span className="min-w-0 break-words">{label}</span>
          <span aria-hidden="true" className="h-3 overflow-hidden rounded-md bg-[#EEF1F5]">
            {value !== null && <span className="block h-full rounded-md" style={{ width: `${100 * Math.max(value, 0) / max}%`, backgroundColor: color, opacity: partial ? 0.45 : 1 }} />}
          </span>
          <span className="min-w-[4rem] text-right tabular-nums text-[#4A5363]">
            {value === null ? 'Нет данных' : `${partial ? 'Не менее ' : ''}${value.toLocaleString('ru-RU')}`}
          </span>
        </li>)}
      </ul> : <p className="text-[#4A5363]">Данных для диаграммы пока нет.</p>}
    </figure>
  </Card>;
}
