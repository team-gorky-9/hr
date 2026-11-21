import { useState } from 'react';
import { MONTHS, Y2025, Y2024 } from './reportData';

const W = 760, H = 300, PL = 40, PR = 20, PT = 16, PB = 40;
export type ChartMonth = { label: string; current: number | null; previous?: number | null; partial?: boolean };
const example = MONTHS.map((label, index) => ({ label, current: Y2025[index], previous: Y2024[index], partial: index === 11 }));

export default function LineChart({ interactive, points = example, year = 2025 }: {
  interactive?: boolean;
  points?: ChartMonth[];
  year?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const maxValue = Math.max(1, ...points.flatMap(({ current, previous }) => [current ?? 0, previous ?? 0]));
  const magnitude = 10 ** Math.floor(Math.log10(maxValue));
  const step = Math.max(1, Math.ceil(maxValue / magnitude / 4) * magnitude);
  const max = step * 4;
  const x = (index: number) => PL + index * (W - PL - PR) / Math.max(points.length - 1, 1);
  const y = (value: number) => PT + (1 - value / max) * (H - PT - PB);
  const selected = hover === null ? null : points[hover];
  const previousShown = points.some((point) => point.previous != null);

  const lines = (part: 'previous' | 'current') => points.slice(1).map((point, index) => {
    const start = points[index][part];
    const end = point[part];
    if (start == null || end == null) return null;
    const dashed = part === 'previous' || point.partial || points[index].partial;
    return <line key={index} x1={x(index)} x2={x(index + 1)} y1={y(start)} y2={y(end)}
      stroke={part === 'current' ? '#1F4FD1' : '#9AA3B2'} strokeWidth={part === 'current' ? 3 : 2} strokeDasharray={dashed ? '5 4' : undefined} />;
  });

  return <div className="relative">
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" aria-label={`Помесячные значения за ${year} год`}>
      {[0, 1, 2, 3, 4].map((index) => <g key={index}>
        <line x1={PL} x2={W - PR} y1={y(index * step)} y2={y(index * step)} stroke="#E1E5EB" />
        <text x={PL - 8} y={y(index * step) + 4} fontSize="12" fill="#616977" textAnchor="end">{index * step}</text>
      </g>)}
      {lines('previous')}{lines('current')}
      {points.map((point, index) => <g key={point.label}>
        {point.current !== null && <circle cx={x(index)} cy={y(point.current)} r={point.partial ? 6 : 4.5}
          fill={point.partial ? '#fff' : '#1F4FD1'} stroke="#1F4FD1" strokeWidth="2">
          <title>{point.label}: {point.partial ? 'не менее ' : ''}{point.current}</title>
        </circle>}
        <text x={x(index)} y={H - 14} fontSize="12" fill="#616977" textAnchor="middle">{point.label}{point.partial ? '*' : ''}</text>
      </g>)}
      {interactive && points.map((point, index) => <rect key={point.label} tabIndex={0} aria-label={point.label}
        x={x(index) - 20} y={PT} width="40" height={H - PT - PB} fill="transparent"
        onMouseEnter={() => setHover(index)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(index)} onBlur={() => setHover(null)} />)}
    </svg>
    {selected && hover !== null && <div className="absolute top-2 bg-white border border-[#E1E5EB] rounded-xl shadow-lg p-4 text-[14px] text-[#4A5363] pointer-events-none"
      style={{ left: Math.max(0, Math.min(68, x(hover) / W * 100 - 10)) + '%' }}>
      <p className="font-bold text-[#141A24]">{selected.label} {year}: {selected.current === null ? 'нет данных' : (selected.partial ? 'не менее ' : '') + selected.current}</p>
      {previousShown && <p>{year - 1}: {selected.previous ?? 'нет данных'}</p>}
    </div>}
    <div className="flex flex-wrap gap-5 text-[14px] text-[#4A5363] mt-2">
      <span><span className="inline-block w-5 h-[3px] bg-[#1F4FD1] align-middle mr-1" />{year}</span>
      {previousShown && <span><span className="inline-block w-5 border-t-2 border-dashed border-[#9AA3B2] align-middle mr-1" />{year - 1}</span>}
      {points.some((point) => point.partial) && <span><span className="inline-block w-3 h-3 rounded-full border-2 border-[#1F4FD1] align-middle mr-1" />* неполный охват</span>}
    </div>
  </div>;
}

