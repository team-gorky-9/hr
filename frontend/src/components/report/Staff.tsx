import React, { useState } from 'react';
import { Card, Badge, Btn } from '../shared/ui';
import { STAFF_DEPTS, ANSWERS_BY_MONTH } from './reportData';

export const Staff: React.FC<{ onDownload: () => void }> = ({ onDownload }) => {
  const [selected, setSelected] = useState<string[]>(STAFF_DEPTS.map((d) => d.name));
  const toggle = (n: string) => setSelected((s) => (s.includes(n) ? s.filter((x) => x !== n) : [...s, n]));
  const max = Math.max(...ANSWERS_BY_MONTH);
  return (
    <div className="space-y-5">
      <Card className="space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex flex-wrap gap-5">
            <div>
              <div className="text-[14px] font-semibold text-[#4A5363] mb-1">Период</div>
              <input readOnly value="01.01.2025 – 31.12.2025" className="border border-[#C9D0DB] rounded-xl px-4 py-3 text-[16px] w-[260px]" />
            </div>
            <div>
              <div className="text-[14px] font-semibold text-[#4A5363] mb-1">Дата среза</div>
              <input readOnly value="31.12.2025" className="border border-[#C9D0DB] rounded-xl px-4 py-3 text-[16px] w-[170px]" />
            </div>
          </div>
          <Btn onClick={onDownload}>Скачать Excel: {selected.length} подразделения</Btn>
        </div>
        <div>
          <div className="text-[15px] font-bold text-[#4A5363] mb-2">Подразделения · выбрано {selected.length}</div>
          <div className="flex flex-wrap gap-3">
            {STAFF_DEPTS.map((d) => {
              const on = selected.includes(d.name);
              return (
                <button key={d.name} type="button" onClick={() => toggle(d.name)}
                  className={`px-4 py-2 rounded-full border text-[16px] font-semibold ${on ? 'border-[#1F4FD1] text-[#1F4FD1] bg-[#EEF3FE]' : 'border-[#C9D0DB] text-[#141A24]'}`}>
                  {on ? '✓ ' : ''}{d.name}
                </button>
              );
            })}
            <span className="px-4 py-2 rounded-full border border-dashed border-[#C9D0DB] text-[#4A5363] text-[16px]">+ Добавить</span>
          </div>
        </div>
      </Card>

      <div className="grid lg:grid-cols-2 gap-5">
        <Card>
          <div className="flex justify-between"><h2 className="text-[20px] font-bold">На 31.12.2025</h2><Badge tone="blue">на дату</Badge></div>
          <div className="grid grid-cols-4 gap-3 mt-4">
            {[['128', 'штатных ставок'], ['118', 'занятых ставок'], ['116', 'сотрудников'], ['10', 'открытых передач']].map(([n, l]) => (
              <div key={l}><div className="text-[30px] font-bold">{n}</div><div className="text-[14px] text-[#4A5363]">{l}</div></div>
            ))}
          </div>
        </Card>
        <Card>
          <div className="flex justify-between"><h2 className="text-[20px] font-bold">За 2025 год</h2><Badge tone="purple">за период</Badge></div>
          <div className="grid grid-cols-4 gap-3 mt-4">
            {[['24', 'принято'], ['19', 'выбыло'], ['142', 'ответа на передачи'], ['5 дн.', 'медиана срока ответа']].map(([n, l]) => (
              <div key={l}><div className="text-[30px] font-bold">{n}</div><div className="text-[14px] text-[#4A5363]">{l}</div></div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid lg:grid-cols-[2fr_1fr] gap-5">
        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Рейтинг по открытым передачам</h2>
          <p className="text-[15px] text-[#4A5363]">Открытые передачи — на 31.12.2025 · ответы и медиана — за 2025 год</p>
          <table className="w-full text-left text-[17px] border border-[#E1E5EB] rounded-xl">
            <thead><tr className="text-[14px] text-[#4A5363] border-b border-[#E1E5EB]"><th className="p-3">Подразделение</th><th>Открыто (на дату)</th><th>Старше 15 дней</th><th>Медиана ответа</th><th>Ответов</th></tr></thead>
            <tbody>
              {STAFF_DEPTS.filter((d) => selected.includes(d.name)).map((d) => (
                <tr key={d.name} className="border-b border-[#E1E5EB] last:border-0">
                  <td className="p-3">{d.name}</td><td>{d.open}</td>
                  <td><Badge tone={d.old ? 'red' : 'gray'}>{d.old}</Badge></td><td>{d.median}</td><td>{d.answers}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Ответы по месяцам</h2>
          <p className="text-[15px] text-[#4A5363]">{selected.length} подразделения · 142 ответа за период</p>
          <div className="flex items-end gap-2 h-[170px]">
            {ANSWERS_BY_MONTH.map((v, i) => (
              <div key={i} className="flex-1 bg-[#5B80E0] rounded-t" style={{ height: `${(v / max) * 100}%` }} />
            ))}
          </div>
          <div className="flex gap-2 text-[13px] text-[#4A5363]">
            {'ЯФМАМИИАСОНД'.split('').map((l, i) => <span key={i} className="flex-1 text-center">{l}</span>)}
          </div>
        </Card>
      </div>
    </div>
  );
};

export default Staff;
