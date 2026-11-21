import React, { useState } from 'react';
import { MONTHS, Y2025, Y2024 } from './reportData';

const W = 760, H = 300, PL = 40, PR = 20, PT = 16, PB = 40;
const MAX = 140;
const x = (i: number) => PL + (i * (W - PL - PR)) / 11;
const y = (v: number) => PT + (1 - v / MAX) * (H - PT - PB);

export const LineChart: React.FC<{ interactive?: boolean }> = ({ interactive }) => {
  const [hover, setHover] = useState<number | null>(null);
  const pts = (arr: number[], to = arr.length) => arr.slice(0, to).map((v, i) => `${x(i)},${y(v)}`).join(' ');
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto">
        {[0, 35, 70, 105, 140].map((g) => (
          <g key={g}>
            <line x1={PL} x2={W - PR} y1={y(g)} y2={y(g)} stroke="#E1E5EB" />
            <text x={PL - 8} y={y(g) + 4} fontSize="12" fill="#616977" textAnchor="end">{g}</text>
          </g>
        ))}
        <polyline points={pts(Y2024)} fill="none" stroke="#9AA3B2" strokeWidth="2" strokeDasharray="5 4" />
        <polyline points={pts(Y2025, 11)} fill="none" stroke="#1F4FD1" strokeWidth="3" />
        <line x1={x(10)} y1={y(Y2025[10])} x2={x(11)} y2={y(Y2025[11])} stroke="#1F4FD1" strokeWidth="3" strokeDasharray="2 4" />
        {Y2025.slice(0, 11).map((v, i) =>
          i === 8 ? (
            <rect key={i} x={x(i) - 7} y={y(v) - 7} width="14" height="14" fill="#C2410C" transform={`rotate(45 ${x(i)} ${y(v)})`} />
          ) : (
            <circle key={i} cx={x(i)} cy={y(v)} r="4.5" fill="#1F4FD1" />
          ),
        )}
        <circle cx={x(11)} cy={y(Y2025[11])} r="7" fill="#fff" stroke="#1F4FD1" strokeWidth="3" />
        {MONTHS.map((m, i) => (
          <text key={m} x={x(i)} y={H - 14} fontSize="12" fill="#616977" textAnchor="middle">{m}{i === 11 ? '*' : ''}</text>
        ))}
        {interactive &&
          MONTHS.map((_, i) => (
            <rect key={i} x={x(i) - 25} y={PT} width="50" height={H - PT - PB} fill="transparent"
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
          ))}
      </svg>
      {interactive && hover !== null && (
        <div
          className="absolute top-2 bg-white border border-[#E1E5EB] rounded-xl shadow-lg p-4 text-[14px] text-[#4A5363] pointer-events-none"
          style={{ left: `${Math.min(70, (x(hover) / W) * 100 - 10)}%` }}
        >
          <div className="font-bold text-[#141A24] text-[16px]">{MONTHS[hover]} 2025: {Y2025[hover]} откликов</div>
          <div>2024: {Y2024[hover]}</div>
          {hover === 8 && <><div>Медиана базы: 79,5</div><div>Выше медианы на 48%</div></>}
        </div>
      )}
      <div className="flex flex-wrap gap-5 text-[14px] text-[#4A5363] mt-2">
        <span><span className="inline-block w-5 h-[3px] bg-[#1F4FD1] align-middle mr-1" />2025</span>
        <span><span className="inline-block w-5 border-t-2 border-dashed border-[#9AA3B2] align-middle mr-1" />2024</span>
        <span><span className="inline-block w-3 h-3 rounded-full border-2 border-[#1F4FD1] align-middle mr-1" />* неполный месяц: выгрузка 26.12</span>
        <span><span className="inline-block w-3 h-3 bg-[#C2410C] rotate-45 align-middle mr-1" />необычный месяц</span>
      </div>
    </div>
  );
};

export default LineChart;
