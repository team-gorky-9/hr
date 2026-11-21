import React, { useState } from 'react';
import { Card, Kpi, Btn, Badge } from '../shared/ui';
import LineChart from './LineChart';
import { VACANCY_RATING, VACANCY_DELTA, OUTCOMES, OUTCOME_LEGEND } from './reportData';
import { ViewToggle } from './Dynamics';

const insights = [
  'Откликов на 115 больше, чем в 2024 году (+12%). Почти весь прирост дали две вакансии.',
  'В сентябре откликов необычно много: 118 при медиане 79,5 по 12 месяцам базы.',
  'Цифровое развитие отвечает дольше всех: медиана 9 дней, 1 передача старше 15 дней.',
];

export const Overview: React.FC<{ onOpenBuilder: () => void; onDownloadSlice: () => void }> = ({
  onOpenBuilder,
  onDownloadSlice,
}) => {
  const [basis, setBasis] = useState<number | null>(null);
  const [view, setView] = useState<'chart' | 'table'>('chart');
  const rows = [
    ...VACANCY_DELTA.slice(0, 2),
    { name: 'Остальные 4 строки', y24: 572, y25: 584, d: 12 },
  ];

  return (
    <div className="space-y-5">
      <div className="grid sm:grid-cols-3 gap-4">
        <Kpi value="1 077" label="откликов" caption="за 2025 год" />
        <Kpi value="857" label="разговоров" caption="за 2025 год" />
        <Kpi value="739" label="разных откликов с разговором" caption="за 2025 год" />
      </div>
      <div className="grid sm:grid-cols-3 gap-4">
        <Kpi value={<span>116 <span className="text-[16px] font-bold">сотрудников</span></span>} caption="на 31.12.2025" />
        <Kpi value={<span>10 <span className="text-[16px] font-bold">открытых передач</span></span>} caption="на 31.12.2025" />
        <Kpi tone="danger" value={<span className="text-[#A3171B]">1 <span className="text-[16px] font-bold text-[#141A24]">передача старше 15 дней</span></span>} caption="на 31.12.2025" />
      </div>

      <div className={`grid gap-5 ${basis !== null ? 'lg:grid-cols-[1fr_520px]' : ''}`}>
        <Card className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-[22px] font-bold">Главные выводы</h2>
            {basis === null && <Badge tone="purple">Сводка ИИ · проверьте основание</Badge>}
          </div>
          {insights.map((t, i) => (
            <div key={i} className="flex items-start justify-between gap-4">
              <div className="flex gap-3 text-[16px] text-[#141A24]">
                <span className="mt-2 w-2 h-2 rounded-full bg-[#1F4FD1] shrink-0" />
                {t}
              </div>
              {basis === null && (
                <Btn variant="link" className="whitespace-nowrap" onClick={() => setBasis(i)}>Показать основание</Btn>
              )}
            </div>
          ))}
        </Card>

        {basis !== null && (
          <div className="bg-white border-2 border-[#1F4FD1] rounded-2xl p-6 space-y-4 lg:row-span-2 lg:col-start-2 lg:row-start-1">
            <div className="flex items-center justify-between">
              <h2 className="text-[22px] font-bold">Основание вывода</h2>
              <button type="button" aria-label="Закрыть" onClick={() => setBasis(null)} className="text-[24px] text-[#4A5363]">×</button>
            </div>
            <p className="text-[17px] font-bold text-[#141A24]">«{insights[basis]}»</p>
            <table className="w-full text-[16px] border border-[#E1E5EB] rounded-xl">
              <thead>
                <tr className="text-[14px] text-[#4A5363] border-b border-[#E1E5EB] text-left">
                  <th className="p-3">Вакансия</th><th>2024</th><th>2025</th><th>Δ</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.name} className="border-b border-[#E1E5EB]">
                    <td className="p-3">{r.name}</td><td>{r.y24}</td><td>{r.y25}</td>
                    <td><Badge tone={r.d > 20 ? 'green' : 'gray'}>+{r.d}</Badge></td>
                  </tr>
                ))}
                <tr><td className="p-3">Итого</td><td>962</td><td>1 077</td><td><Badge tone="green">+115</Badge></td></tr>
              </tbody>
            </table>
            <p className="text-[14px] text-[#4A5363]">
              Источник: версия v3 от 15.01.2026 · лист «Отклики» · все исходы · дата отклика внутри периода
            </p>
            <div className="flex gap-3">
              <Btn variant="primary" onClick={onOpenBuilder}>Открыть в конструкторе</Btn>
              <Btn onClick={onDownloadSlice}>Скачать этот срез</Btn>
            </div>
          </div>
        )}
      </div>

      <div className="grid lg:grid-cols-[1.7fr_1fr] gap-5">
        <Card>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[22px] font-bold">Динамика откликов по месяцам</h2>
            <ViewToggle value={view} onChange={setView} />
          </div>
          {view === 'chart' ? <LineChart /> : <p className="text-[15px] text-[#4A5363]">Табличный вид — вкладка «Динамика и причины».</p>}
        </Card>
        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Рейтинг вакансий</h2>
          <p className="text-[15px] text-[#4A5363]">Поступило откликов и сколько из них с разговором · 2025</p>
          <table className="w-full text-left text-[16px] border border-[#E1E5EB] rounded-xl">
            <thead>
              <tr className="text-[14px] text-[#4A5363] border-b border-[#E1E5EB]"><th className="p-3">Вакансия</th><th>Откликов</th><th>С разговором</th></tr>
            </thead>
            <tbody>
              {VACANCY_RATING.map((r) => (
                <tr key={r.name} className="border-b border-[#E1E5EB] last:border-0"><td className="p-3">{r.name}</td><td>{r.r}</td><td>{r.t}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <div className="grid lg:grid-cols-[1.7fr_1fr] gap-5">
        <Card>
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-[22px] font-bold">Разговоры по исходам</h2>
            <span className="text-[14px] text-[#4A5363]">857 за 2025 год</span>
          </div>
          <div className="flex items-end gap-8 h-[240px]">
            {OUTCOMES.map((o) => (
              <div key={o.q} className="flex flex-col items-center gap-1 w-[110px]">
                <span className="text-[14px] font-bold">{o.total}</span>
                <div className="w-full flex flex-col-reverse rounded overflow-hidden" style={{ height: `${o.total * 0.8}px` }}>
                  {(['a', 'b', 'c', 'd'] as const).map((k, i) => (
                    <div key={k} style={{ height: `${(o[k] / o.total) * 100}%`, background: OUTCOME_LEGEND[i].color }} className="border-t border-white" />
                  ))}
                </div>
                <span className="text-[13px] text-[#4A5363]">{o.q}</span>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-4 mt-3 text-[14px] text-[#4A5363]">
            {OUTCOME_LEGEND.map((l) => (
              <span key={l.key}><span className="inline-block w-3 h-3 rounded-sm mr-1" style={{ background: l.color }} />{l.label}</span>
            ))}
          </div>
        </Card>
        <Card className="space-y-4">
          <h2 className="text-[22px] font-bold">Полнота данных</h2>
          {[
            ['green', 'Полно', 'Даты есть у всех откликов', '1 077 из 1 077'],
            ['green', 'Полно', 'Журнал собеседований за 12 месяцев', '857 разговоров'],
            ['amber', 'Частично', 'Декабрь неполный', 'выгрузка 26.12, 5 дней нет'],
          ].map(([t, b, h, s]) => (
            <div key={h} className="flex gap-3 items-start">
              <Badge tone={t as 'green' | 'amber'}>{b}</Badge>
              <div><div className="text-[16px] font-bold">{h}</div><div className="text-[14px] text-[#4A5363]">{s}</div></div>
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
};

export default Overview;
