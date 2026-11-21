import React, { useState } from 'react';
import { Card, Kpi, Btn, Chip } from '../shared/ui';
import { ViewToggle } from './Dynamics';
import { CONSTRUCTOR_VACANCIES, PRESETS, BUILDER_ROWS } from './reportData';

const Check: React.FC<{ checked: boolean; onChange: () => void; children: React.ReactNode }> = ({ checked, onChange, children }) => (
  <label className="flex items-center gap-3 text-[16px] cursor-pointer">
    <input type="checkbox" checked={checked} onChange={onChange} className="w-5 h-5 accent-[#1F4FD1]" />
    {children}
  </label>
);

const toggle = <T,>(arr: T[], v: T) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
const pct = (n: number, r: number) => `${((n / r) * 100).toFixed(2).replace('.', ',')}%`;

export const Builder: React.FC<{ initialApplied?: boolean }> = ({ initialApplied = false }) => {
  const [preset, setPreset] = useState('Скорость первого разговора');
  const [from, setFrom] = useState('01.07.2025');
  const [to, setTo] = useState('31.12.2025');
  const [vacs, setVacs] = useState<string[]>([CONSTRUCTOR_VACANCIES[0], CONSTRUCTOR_VACANCIES[1]]);
  const [allOutcomes, setAllOutcomes] = useState(true);
  const [metrics, setMetrics] = useState<string[]>(['Отклики', 'Доля с первым разговором за 14 дней']);
  const [groups, setGroups] = useState<string[]>(['Квартал', 'Вакансия']);
  const [dirty, setDirty] = useState(!initialApplied);
  const [applied, setApplied] = useState(initialApplied);
  const [changed, setChanged] = useState(initialApplied ? 0 : 3);
  const [view, setView] = useState<'chart' | 'table'>('chart');
  const [exported, setExported] = useState(false);

  const touch = () => {
    setDirty(true);
    setChanged((c) => c + 1);
    setExported(false);
  };
  const apply = () => {
    setApplied(true);
    setDirty(false);
    setChanged(0);
  };

  const totalR = BUILDER_ROWS.reduce((a, r) => a + r.r, 0);
  const totalN = BUILDER_ROWS.reduce((a, r) => a + r.n, 0);

  return (
    <div className="grid lg:grid-cols-[360px_1fr] gap-5 items-start">
      <Card className="space-y-5">
        <h2 className="text-[22px] font-bold">Фильтры</h2>
        <div>
          <div className="text-[15px] font-bold text-[#4A5363] mb-2">Готовые срезы</div>
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((p) => (
              <Chip key={p} active={preset === p} onClick={() => { setPreset(p); touch(); }}>{p}</Chip>
            ))}
          </div>
        </div>
        <div>
          <div className="text-[15px] font-bold text-[#4A5363] mb-2">Период</div>
          <div className="grid grid-cols-2 gap-3">
            {([['С', from, setFrom], ['По', to, setTo]] as const).map(([l, v, set]) => (
              <div key={l}>
                <div className="text-[14px] font-semibold text-[#4A5363] mb-1">{l}</div>
                <input value={v} onChange={(e) => { set(e.target.value); touch(); }}
                  className="w-full border border-[#C9D0DB] rounded-xl px-3 py-3 text-[16px] outline-none focus:border-[#1F4FD1]" />
              </div>
            ))}
          </div>
        </div>
        <div className="space-y-3">
          <div className="text-[15px] font-bold text-[#4A5363]">Вакансии · выбрано {vacs.length}</div>
          {CONSTRUCTOR_VACANCIES.map((v) => (
            <Check key={v} checked={vacs.includes(v)} onChange={() => { setVacs(toggle(vacs, v)); touch(); }}>{v}</Check>
          ))}
        </div>
        <div className="space-y-2">
          <div className="text-[15px] font-bold text-[#4A5363]">Исходы</div>
          <Check checked={allOutcomes} onChange={() => { setAllOutcomes(!allOutcomes); touch(); }}>Все применимые исходы</Check>
          <div className="text-[13px] text-[#4A5363]">Для доли учитываются отклики с датой</div>
        </div>
        <div className="space-y-3">
          <div className="text-[15px] font-bold text-[#4A5363]">Показатель</div>
          {['Отклики', 'Доля с первым разговором за 14 дней', 'Разговоры по исходам'].map((m) => (
            <Check key={m} checked={metrics.includes(m)} onChange={() => { setMetrics(toggle(metrics, m)); touch(); }}>{m}</Check>
          ))}
        </div>
        <div>
          <div className="text-[15px] font-bold text-[#4A5363] mb-2">Группировка</div>
          <div className="flex flex-wrap gap-2">
            {['Квартал', 'Вакансия', 'Месяц', 'Подразделение'].map((g) => (
              <Chip key={g} active={groups.includes(g)} onClick={() => { setGroups(toggle(groups, g)); touch(); }}>{g}</Chip>
            ))}
          </div>
        </div>
        <Btn variant="primary" className="w-full" onClick={apply}>
          Применить фильтры{dirty && changed > 0 ? ` · изменено ${changed}` : ''}
        </Btn>
      </Card>

      {!applied ? (
        <Card className="min-h-[420px]">
          <div className="bg-[#F6F7F9] rounded-2xl p-8 max-w-[340px]">
            <div className="w-[60px] h-[60px] rounded-xl bg-[#E8EEFC] flex items-center justify-center text-[#1F4FD1] text-[28px] mb-4">↗</div>
            <div className="text-[20px] font-bold">Фильтры изменены</div>
            <p className="text-[16px] text-[#4A5363] mt-2">Нажмите «Применить фильтры», чтобы график и таблица показали новый результат.</p>
          </div>
        </Card>
      ) : (
        <div className="space-y-5">
          {exported && (
            <div className="rounded-2xl border-2 border-[#9FD0AC] bg-[#E3F2E7] p-5">
              <div className="text-[20px] font-bold text-[#1D7A40]">Excel среза готов</div>
              <div className="text-[17px] text-[#1D7A40]">builder-2025-H2-2vac.xlsx · 2 вакансии, 4 строки, тот же результат, что на экране</div>
            </div>
          )}
          <Card className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-2">
              <div className="text-[16px] text-[#4A5363]">Итого по срезу</div>
              <div className="flex flex-wrap gap-2">
                {['Июль – декабрь 2025', 'Инженер информационных систем', 'Специалист по обращениям', 'Квартал × вакансия'].map((t) => (
                  <span key={t} className="bg-[#EEF3FE] text-[#1F4FD1] text-[14px] font-semibold px-3 py-1 rounded-md">{t}</span>
                ))}
              </div>
              <div className="text-[14px] text-[#4A5363]">Экспорт: 2 вакансии · июль–декабрь 2025 · квартал × вакансия</div>
            </div>
            <Btn onClick={() => setExported(true)}>Скачать Excel этого среза</Btn>
          </Card>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Kpi value={totalR} label="откликов" caption="июль–декабрь 2025" />
            <Kpi value={`${totalN} из ${totalR}`} label="первый разговор за 14 дней" caption="числитель / знаменатель" />
            <Kpi value={pct(totalN, totalR)} label="доля" caption="годом ранее 47,31% (123 из 260)" />
            <Kpi tone="success" value={<span className="text-[#1D7A40]">+8,13 п.п.</span>} label="доля" caption="к тому же периоду 2024" />
          </div>

          <Card className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-[22px] font-bold">Доля с первым разговором за 14 дней</h2>
              <ViewToggle value={view} onChange={setView} />
            </div>
            {view === 'chart' ? (
              <div className="flex items-end gap-10 h-[260px] pt-4">
                {BUILDER_ROWS.map((r) => {
                  const p = (r.n / r.r) * 100;
                  return (
                    <div key={r.q + r.v} className="flex flex-col items-center gap-1 w-[110px]">
                      <span className="text-[14px] font-bold">{pct(r.n, r.r)}</span>
                      <div className="w-[70px] h-[180px] bg-[#F0F2F6] rounded flex items-end">
                        <div className="w-full bg-[#1F4FD1] rounded-b" style={{ height: `${p}%` }} />
                      </div>
                      <span className="text-[13px] text-[#4A5363] text-center">{r.q}<br />{r.v}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-[15px] text-[#4A5363]">Значения — в таблице результата ниже.</p>
            )}
          </Card>

          <Card className="space-y-4">
            <h2 className="text-[22px] font-bold">Таблица результата</h2>
            <table className="w-full text-left text-[16px] border border-[#E1E5EB] rounded-xl">
              <thead><tr className="text-[14px] text-[#4A5363] border-b border-[#E1E5EB]"><th className="p-3">Квартал</th><th>Вакансия</th><th>Откликов</th><th>Разговор ≤ 14 дн.</th><th>Доля</th></tr></thead>
              <tbody>
                {BUILDER_ROWS.map((r) => (
                  <tr key={r.q + r.v} className="border-b border-[#E1E5EB]"><td className="p-3">{r.q}</td><td>{r.v}</td><td>{r.r}</td><td>{r.n} из {r.r}</td><td>{pct(r.n, r.r)}</td></tr>
                ))}
                <tr className="font-bold"><td className="p-3">Итого</td><td /><td>{totalR}</td><td>{totalN} из {totalR}</td><td>{pct(totalN, totalR)}</td></tr>
              </tbody>
            </table>
          </Card>
        </div>
      )}
    </div>
  );
};

export default Builder;
