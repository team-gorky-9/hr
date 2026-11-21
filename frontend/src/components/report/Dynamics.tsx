import React, { useState } from 'react';
import { Card, Badge } from '../shared/ui';
import LineChart from './LineChart';
import { MONTHS, Y2025, Y2024, MATRIX, VACANCY_DELTA, fmt } from './reportData';

export const ViewToggle: React.FC<{ value: 'chart' | 'table'; onChange: (v: 'chart' | 'table') => void }> = ({ value, onChange }) => (
  <div className="inline-flex bg-[#E8ECF2] rounded-xl p-1">
    {([['chart', 'График'], ['table', 'Таблица']] as const).map(([id, l]) => (
      <button key={id} type="button" onClick={() => onChange(id)}
        className={`px-4 py-2 rounded-lg text-[15px] font-semibold ${value === id ? 'bg-white text-[#141A24] shadow-sm' : 'text-[#4A5363]'}`}>
        {l}
      </button>
    ))}
  </div>
);

const shade = (v: number) => {
  const t = Math.min(1, Math.max(0, (v - 8) / 20));
  const a = [212, 223, 250], b = [124, 153, 238];
  return `rgb(${a.map((c, i) => Math.round(c + (b[i] - c) * t)).join(',')})`;
};

export const Dynamics: React.FC = () => {
  const [view, setView] = useState<'chart' | 'table'>('chart');
  const [cell, setCell] = useState<{ r: number; c: number } | null>(null);
  const t25 = Y2025.reduce((a, b) => a + b, 0), t24 = Y2024.reduce((a, b) => a + b, 0);

  if (view === 'table')
    return (
      <Card className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[22px] font-bold">Поступления по месяцам: 2025 и 2024</h2>
          <ViewToggle value={view} onChange={setView} />
        </div>
        <p className="text-[15px] text-[#4A5363]">Тот же результат, что и на графике. Подходит для экранного чтения и печати.</p>
        <table className="w-full text-left text-[17px] border border-[#E1E5EB] rounded-xl">
          <thead><tr className="text-[14px] text-[#4A5363] border-b border-[#E1E5EB]"><th className="p-3">Месяц</th><th>2025</th><th>2024</th><th>Изменение</th><th>Примечание</th></tr></thead>
          <tbody>
            {MONTHS.map((m, i) => {
              const d = Y2025[i] - Y2024[i];
              return (
                <tr key={m} className="border-b border-[#E1E5EB]">
                  <td className="p-3">{m}</td><td>{Y2025[i]}</td><td>{Y2024[i]}</td><td>{d > 0 ? `+${d}` : d}</td>
                  <td>
                    {i === 8 && <Badge tone="amber">Необычный месяц: медиана 79,5</Badge>}
                    {i === 11 && <Badge tone="gray">Неполный месяц: выгрузка 26.12</Badge>}
                  </td>
                </tr>
              );
            })}
            <tr className="font-bold"><td className="p-3">Итого</td><td>{fmt(t25)}</td><td>{t24}</td><td>+{t25 - t24}</td><td /></tr>
          </tbody>
        </table>
      </Card>
    );

  return (
    <div className="space-y-5">
      <div className="grid lg:grid-cols-[1.6fr_1fr] gap-5">
        <Card>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[22px] font-bold">Поступления по месяцам: 2025 и 2024</h2>
            <ViewToggle value={view} onChange={setView} />
          </div>
          <LineChart interactive />
        </Card>
        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Вклад вакансий в разницу</h2>
          <p className="text-[15px] text-[#4A5363]">Годовая разница: 962 → 1 077, +115</p>
          <table className="w-full text-left text-[16px] border border-[#E1E5EB] rounded-xl">
            <thead><tr className="text-[14px] text-[#4A5363] border-b border-[#E1E5EB]"><th className="p-3">Вакансия</th><th>2024</th><th>2025</th><th>Изм.</th></tr></thead>
            <tbody>
              {VACANCY_DELTA.map((r) => (
                <tr key={r.name} className="border-b border-[#E1E5EB] last:border-0">
                  <td className="p-3">{r.name}</td><td>{r.y24}</td><td>{r.y25}</td>
                  <td><Badge tone={r.d > 5 ? 'green' : r.d < 0 ? 'red' : 'gray'}>{r.d > 0 ? `+${r.d}` : r.d}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <Card className="space-y-3 overflow-x-auto">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[22px] font-bold">Матрица «вакансия × месяц»</h2>
          <span className="text-[14px] text-[#4A5363]">Нажмите на ячейку, чтобы увидеть значение и покрытие</span>
        </div>
        <table className="w-full min-w-[900px] text-left">
          <thead>
            <tr className="text-[14px] text-[#4A5363]">
              <th className="p-3">Вакансия × месяц</th>
              {MONTHS.map((m) => <th key={m} className="text-center">{m}</th>)}
              <th className="text-center">Итого</th>
            </tr>
          </thead>
          <tbody>
            {MATRIX.map((row, r) => (
              <tr key={row.name} className="border-t border-[#E1E5EB]">
                <td className="p-3 text-[16px] w-[200px]">{row.name}</td>
                {row.values.map((v, c) => (
                  <td key={c} className="text-center relative p-1">
                    <button type="button" onClick={() => setCell(cell?.r === r && cell?.c === c ? null : { r, c })}
                      className="w-[56px] py-2 rounded-lg text-[16px] font-semibold text-[#141A24]" style={{ background: shade(v) }}>
                      {v}
                    </button>
                    {cell?.r === r && cell?.c === c && (
                      <div className="absolute z-10 left-1/2 -translate-x-1/2 top-12 w-[260px] text-left bg-white border border-[#E1E5EB] rounded-xl shadow-lg p-4 text-[14px] text-[#4A5363]">
                        <div className="font-bold text-[#141A24] text-[16px]">{row.name} · {MONTHS[c].toLowerCase()} 2025</div>
                        <div>{v} откликов</div>
                        <div>Покрытие: дата есть у {v} из {v}</div>
                        <div>{c === 11 ? 'Месяц неполный' : 'Месяц полный'}</div>
                      </div>
                    )}
                  </td>
                ))}
                <td className="text-center text-[17px] font-bold">{row.values.reduce((a, b) => a + b, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
};

export default Dynamics;
