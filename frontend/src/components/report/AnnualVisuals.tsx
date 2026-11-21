import { useState } from 'react';
import { Badge, Btn, Card } from '../shared/ui';
import { ViewToggle } from './Dynamics';
import LineChart from './LineChart';

export type Cell = { value: number | null; status: string; reason_codes: string[]; numerator?: number; denominator?: number };
type VacancyMetric = {
  vacancy_key: string; label: string; applications_received: Cell; applications_with_phone_interview: Cell;
};
type Outcome = 'continue' | 'stop' | 'pending';
type Month = { month: string; metrics: Record<string, Cell>; outcomes: Record<Outcome, Cell>; vacancies: VacancyMetric[] };
export type AnnualSeries = { year: number; months: Month[]; previous_months: Month[]; vacancies: VacancyMetric[] };
export type Finding = { section: string; statement: string; evidence: unknown };

export const monthLabel = (month: string) => /^\d{4}-\d{2}/.test(month)
  ? new Date(month.slice(0, 7) + '-01T12:00:00Z').toLocaleDateString('ru-RU', { month: 'short' })
  : month;
export const cellValue = (cell?: Cell) => cell?.value == null ? '—'
  : (cell.status === 'partial' ? 'Не менее ' : '') + cell.value.toLocaleString('ru-RU');
const outcomeColors = [
  { key: 'continue', label: 'Продолжили подбор', color: '#1F4FD1' },
  { key: 'stop', label: 'Завершили рассмотрение', color: '#C2410C' },
  { key: 'pending', label: 'Исход не зафиксирован', color: '#9AA3B2' },
] as const;
const tableClass = 'w-full text-left text-[15px] border border-[#E1E5EB] rounded-xl';

export function Findings({ rows, year, onOpenBuilder, onDownload }: {
  rows: Finding[];
  year: number;
  onOpenBuilder: () => void;
  onDownload: () => void;
}) {
  const [basis, setBasis] = useState<Finding | null>(null);
  return <div className={basis ? 'grid gap-5 lg:grid-cols-[1fr_1fr]' : ''}>
    <Card className="space-y-3">
      <h2 className="text-[22px] font-bold">Главные выводы</h2>
      {rows.length === 0 && <p className="text-[#4A5363]">В снимке нет опубликованных выводов.</p>}
      {rows.map((row, index) => <div key={index} className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-start gap-3"><span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-[#1F4FD1]" /><p>{row.statement}</p></div>
        <Btn variant="link" onClick={() => setBasis(row)}>Показать основание</Btn>
      </div>)}
    </Card>
    {basis && <div className="rounded-2xl border-2 border-[#1F4FD1] bg-white p-6 space-y-4">
      <div className="flex items-center justify-between gap-3"><h2 className="text-[22px] font-bold">Основание вывода</h2><button type="button" className="text-[24px]" aria-label="Закрыть" onClick={() => setBasis(null)}>×</button></div>
      <p className="font-bold">{basis.statement}</p>
      <p className="text-[14px] text-[#4A5363]">Раздел «{basis.section}», снимок {year} года. Покрытие и исходные показатели доступны в докладе.</p>
      <div className="flex flex-wrap gap-3"><Btn variant="primary" onClick={onOpenBuilder}>Открыть в конструкторе</Btn><Btn onClick={onDownload}>Скачать годовой XLSX</Btn></div>
    </div>}
  </div>;
}

function Occupancy({ series }: { series: AnnualSeries }) {
  const quarters = Array.from({ length: 4 }, (_, index) => {
    const months = series.months.slice(index * 3, index * 3 + 3);
    const parts = outcomeColors.map(({ key, color, label }) => {
      const cells = months.map((month) => month.outcomes[key]);
      const known = cells.flatMap((cell) => cell?.value == null ? [] : [cell.value]);
      return { color, label, value: known.length ? known.reduce((sum, value) => sum + value, 0) : null,
        partial: cells.some((cell) => cell?.status !== 'complete') };
    });
    return { label: `Кв. ${index + 1}`, parts, total: parts.reduce((sum, cell) => sum + (cell.value ?? 0), 0) };
  });
  const max = Math.max(1, ...quarters.map((quarter) => quarter.total));
  return <Card className="space-y-4">
    <h2 className="text-[22px] font-bold">Разговоры по исходам</h2>
    <div className="flex items-end gap-3 sm:gap-8 h-[220px]">
      {quarters.map((quarter) => <div key={quarter.label} className="flex h-full flex-1 flex-col items-center justify-end gap-1 text-[14px]">
        <span className="font-bold">{quarter.parts.some((part) => part.value !== null)
          ? (quarter.parts.some((part) => part.partial) ? '≥ ' : '') + quarter.total : '—'}</span>
        <div className="flex w-full max-w-[100px] flex-col-reverse overflow-hidden rounded-t" style={{ height: 85 * quarter.total / max + '%' }}>
          {quarter.parts.map((part) => <div key={part.label} title={part.label + ': ' + (part.value ?? 'нет данных')}
            className="w-full" style={{ height: 100 * (part.value ?? 0) / Math.max(quarter.total, 1) + '%', backgroundColor: part.color }} />)}
        </div>
        <span className="text-[#4A5363]">{quarter.label}</span>
      </div>)}
    </div>
    <div className="flex flex-wrap gap-4 text-[14px] text-[#4A5363]">{outcomeColors.map(({ key, label, color }) =>
      <span key={key}><span className="mr-1 inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: color }} />{label}</span>)}</div>
  </Card>;
}

function VacancyTable({ series, changes }: { series: AnnualSeries; changes: boolean }) {
  const rows = [...series.vacancies].sort((first, second) => (second.applications_received.value ?? 0) - (first.applications_received.value ?? 0));
  return <Card className="space-y-3 overflow-x-auto">
    <h2 className="text-[22px] font-bold">{changes ? 'Вклад вакансий в разницу' : 'Рейтинг вакансий'}</h2>
    <table className={tableClass}>
      <thead className="text-[14px] text-[#4A5363] border-b border-[#E1E5EB]"><tr>
        <th className="p-3">Вакансия</th><th>{changes ? series.year - 1 : 'Откликов'}</th><th>{changes ? series.year : 'С разговором'}</th>{changes && <th>Изм.</th>}
      </tr></thead>
      <tbody>{rows.map((row) => {
        const curr = row.applications_received;
        const months = series.previous_months.map((month) => month.vacancies.find((item) => item.vacancy_key === row.vacancy_key)?.applications_received);
        const comparable = months.length > 0 && months.every((cell) => cell?.status === 'complete' && cell.value != null);
        const prev = comparable ? months.reduce((sum, cell) => sum + (cell?.value ?? 0), 0) : null;
        const delta = prev != null && curr.status === 'complete' && curr.value != null ? curr.value - prev : null;
        return <tr key={row.vacancy_key} className="border-b border-[#E1E5EB] last:border-0">
          <td className="p-3">{row.label}</td><td>{changes ? prev ?? '—' : cellValue(curr)}</td>
          <td>{changes ? cellValue(curr) : cellValue(row.applications_with_phone_interview)}</td>
          {changes && <td>{delta == null ? '—' : <Badge tone={delta > 0 ? 'green' : delta < 0 ? 'red' : 'gray'}>{delta > 0 ? '+' : ''}{delta}</Badge>}</td>}
        </tr>;
      })}</tbody>
    </table>
  </Card>;
}

function Matrix({ series }: { series: AnnualSeries }) {
  const [selected, setSelected] = useState<{ label: string; month: string; cell?: Cell } | null>(null);
  const max = Math.max(1, ...series.months.flatMap((month) => month.vacancies.map((row) => row.applications_received.value ?? 0)));
  return <Card className="space-y-3">
    <h2 className="text-[22px] font-bold">Матрица «вакансия × месяц»</h2>
    <p className="text-[14px] text-[#4A5363]">Нажмите на ячейку, чтобы увидеть значение и покрытие.</p>
    <div className="overflow-x-auto"><table className="w-full min-w-[850px] text-left">
      <thead><tr className="text-[14px] text-[#4A5363]"><th className="p-3">Вакансия</th>{series.months.map((month) => <th className="text-center" key={month.month}>{monthLabel(month.month)}</th>)}<th>Итого</th></tr></thead>
      <tbody>{series.vacancies.map((vacancy) => <tr key={vacancy.vacancy_key} className="border-t border-[#E1E5EB]"><td className="p-3">{vacancy.label}</td>
        {series.months.map((month) => {
          const cell = month.vacancies.find((row) => row.vacancy_key === vacancy.vacancy_key)?.applications_received;
          const fill = (cell?.value ?? 0) / max;
          return <td className="p-1 text-center" key={month.month}><button type="button" aria-label={vacancy.label + ' · ' + monthLabel(month.month)}
            onClick={() => setSelected({ label: vacancy.label, month: monthLabel(month.month), cell })}
            className="w-full rounded-lg px-2 py-2 font-semibold" style={{ background: cell?.value == null ? '#EEF1F5' : `rgba(31, 79, 209, ${0.1 + 0.35 * fill})` }}>
            {cell?.status === 'partial' && '≥ '}{cell?.value ?? '—'}
          </button></td>;
        })}
        <td className="font-bold">{cellValue(vacancy.applications_received)}</td>
      </tr>)}</tbody>
    </table></div>
    {selected && <p role="status" className="rounded-xl bg-[#EEF3FE] p-3 text-[14px]">
      {selected.label} · {selected.month}: {cellValue(selected.cell)}. {selected.cell?.status === 'complete' ? 'Полный охват.' : 'Данные неполны или отсутствуют.'}
    </p>}
  </Card>;
}

export function AnnualTrends({ series, dynamics = false }: { series: AnnualSeries; dynamics?: boolean }) {
  const [view, setView] = useState<'chart' | 'table'>('chart');
  const points = series.months.map((month) => {
    const current = month.metrics.applications_received;
    const previous = series.previous_months.find((row) => row.month.slice(-2) === month.month.slice(-2))?.metrics.applications_received;
    return { label: monthLabel(month.month), current: current?.value ?? null, previous: previous?.status === 'complete' ? previous.value : null, partial: current?.status === 'partial' };
  });
  return <>
    <div className="grid lg:grid-cols-[1.7fr_1fr] gap-5">
      <Card className="min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <h2 className="text-[22px] font-bold">Динамика откликов по месяцам</h2><ViewToggle value={view} onChange={setView} />
        </div>
        {view === 'chart' ? <LineChart interactive points={points} year={series.year} /> :
          <table className={tableClass}><thead><tr><th className="p-3">Месяц</th><th>{series.year}</th><th>{series.year - 1}</th></tr></thead>
            <tbody>{points.map((month) => <tr key={month.label} className="border-t border-[#E1E5EB]">
              <td className="p-3">{month.label}</td><td>{month.partial && '≥ '}{month.current ?? '—'}</td><td>{month.previous ?? '—'}</td>
            </tr>)}</tbody></table>}
      </Card>
      <VacancyTable key={series.year} series={series} changes={dynamics} />
    </div>
    {dynamics ? <Matrix series={series} /> : <Occupancy series={series} />}
  </>;
}

