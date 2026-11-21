import { useEffect, useState } from 'react';
import { request } from '../../api/archive';
import { annualReportsPath as path, downloadWorkbook } from '../../api/reports';
import { Card, Btn, Kpi, Badge } from '../shared/ui';
import { REPORT_TABS, type ReportTab } from './ReportShell';
import ReportBars from './ReportBars';

type Cell = { value: number | null; status: string; reason_codes: string[]; numerator?: number; denominator?: number };
type Version = { snapshot_id: string; year: number; scope_label: string; mode: string; extracted_at: string };
type Snapshot = Version & {
  period_start: string; period_end_exclusive: string; observed_until: string;
  totals: Record<string, Cell>;
  months: { month: string; metrics: Record<string, Cell> }[];
  quality: { undated_applications: number; undated_interviews: number; duplicates: number };
};
type Catalog = {
  snapshot_id: string;
  metrics: { key: string; label: string; unit: string; definition: string }[];
  vacancies: { key: string; label: string }[];
  departments?: { key: string; label: string }[];
};
type Analysis = { totals: Record<string, Cell>; rows: { dimensions: Record<string, string | number>; metrics: Record<string, Cell> }[] };
type Operations = { available: boolean; workforce: Record<string, Cell>; handoffs: Record<string, Cell>; by_department: { key: string; label: string; workforce: Record<string, Cell>; handoffs: Record<string, Cell> }[] };
const metricNames: Record<string, string> = { applications_received: 'Поступившие отклики', phone_interviews_held: 'Телефонные интервью', applications_with_phone_interview: 'Отклики с разговором', headcount:'Численность', authorized_fte:'Штатные ставки', occupied_fte:'Занятые ставки', hires:'Приняты', exits:'Выбыли', open:'Открытые передачи', open_over_15:'Ожидают более 15 календарных дней', sent:'Передано', answered:'Ответов', median_response_days:'Медиана ответа, дни' };
const statuses: Record<string, string> = { complete:'Полные данные', partial:'Неполный охват', unavailable:'Источник недоступен', future:'За пределами наблюдения' };
const reasons: Record<string, string> = { coverage_gap:'Неполный период', coverage_unknown:'Охват неизвестен', missing_business_date:'Отсутствуют даты событий', outside_period:'За пределами периода', incomplete_coverage:'Сравнение недоступно из-за неполноты', zero_baseline:'Нулевая база' };
const show = (cell: Cell) => cell.value === null ? 'Нет данных' : (cell.status === 'partial' ? 'Не менее ' : '') + cell.value.toLocaleString('ru-RU');
const field = 'border border-[#C9D0DB] rounded-xl px-3 py-2 bg-white text-[14px]';
const point = (label: string, cell?: Cell) => ({ label, value: cell?.value ?? null, partial: cell?.status === 'partial' });
const monthLabel = (month: string) => new Date(`${month.slice(0,7)}-01T12:00:00Z`).toLocaleDateString('ru-RU', { month: 'short' });
function Value({ cell }: { cell?: Cell }) {
  return cell ? <span>{show(cell)}<small className="block text-[#4A5363]">{statuses[cell.status]}{cell.denominator != null && ` · ${cell.numerator} из ${cell.denominator}`}</small></span> : <span>Нет данных</span>;
}
export default function ReportPage({ embeddedView, onPrepared }: {
  embeddedView?: 'config' | 'ready';
  onPrepared?: () => void;
}) {
  const embedded = Boolean(embeddedView);
  const [versions, setVersions] = useState<Version[]>([]);
  const [id, setId] = useState(new URLSearchParams(location.search).get('snapshot') || '');
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [findings, setFindings] = useState<{section:string; statement:string; evidence:unknown}[]>([]);
  const [tab, setTab] = useState<ReportTab>(embedded ? 'builder' : 'overview');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [first, setFirst] = useState(1);
  const [last, setLast] = useState(12);
  const [vacancy, setVacancy] = useState('');
  const [metric, setMetric] = useState('applications_received');
  const [group, setGroup] = useState('month');
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [operations, setOperations] = useState<Operations | null>(null);
  const [applied, setApplied] = useState<Record<string,unknown> | null>(null);
  const [department, setDepartment] = useState('');
  const [reload, setReload] = useState(0);
  const [loadingVersions, setLoadingVersions] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    setLoadingVersions(true);
    request<Version[]>(path,{signal:controller.signal}).then((rows) => {
      setVersions(rows); setId((current) => current || rows[0]?.snapshot_id || '');
    }).catch((e) => { if(!controller.signal.aborted) setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setLoadingVersions(false); });
    return () => controller.abort();
  },[reload]);
  useEffect(() => {
    setSnapshot(null); setCatalog(null); setFindings([]); setAnalysis(null); setApplied(null); setOperations(null);
    if(!id) return;
    const controller = new AbortController(); setError('');
    const url=new URL(location.href); url.searchParams.set('snapshot',id); history.replaceState(null,'',url);
    request<Snapshot>(path+'/'+id,{signal:controller.signal}).then(setSnapshot).catch((e)=>{if(!controller.signal.aborted)setError(e.message);});
    request<Catalog>(path+'/'+id+'/catalog',{signal:controller.signal}).then((value) => setCatalog({ ...value, departments: Array.isArray(value.departments) ? value.departments : Object.entries(value.departments || {}).map(([key, label]) => ({ key, label: String(label) })) })).catch((e)=>{if(!controller.signal.aborted)setError(e.message);});
    request<{findings:typeof findings}>(path+'/'+id+'/brief',{signal:controller.signal}).then((r)=>setFindings(r.findings)).catch((e)=>{if(!controller.signal.aborted)setError(e.message);});
    return ()=>controller.abort();
  },[id,reload]);
  async function download(suffix: '/xlsx' | '/query/xlsx' | '/operations/xlsx', body?:Record<string,unknown>) {
    setBusy(true);setError('');
    try {
      await downloadWorkbook(id, suffix, body);
    }catch(e){setError(e instanceof Error?e.message:'Ошибка выгрузки');}finally{setBusy(false);}
  }
  async function query(notify = true) {
    const body=tab==='staff'?{start_month:first,end_month:last,departments:department?[department]:[]}:{start_month:first,end_month:last,vacancy_keys:vacancy?[vacancy]:[],metrics:[metric],group_by:[group],compare_previous:true};
    setBusy(true);setError('');
    try{
      if(tab==='staff')setOperations(await request<Operations>(path+'/'+id+'/operations',{method:'POST',body:JSON.stringify(body)}));
      else setAnalysis(await request<Analysis>(path+'/'+id+'/query',{method:'POST',body:JSON.stringify(body)}));
      setApplied(body);
      if (notify) onPrepared?.();
    }catch(e){setError(e instanceof Error?e.message:'Ошибка запроса');}finally{setBusy(false);}
  }
  useEffect(() => {
    if (embedded || !id || catalog?.snapshot_id !== id) return;
    if (tab === 'builder' || tab === 'staff') void query(false);
  }, [tab, id, catalog, embedded]);
  function sliceLabel(dimensions: Analysis['rows'][number]['dimensions']) {
    return Object.entries(dimensions).map(([key, value]) => key === 'vacancy'
      ? catalog?.vacancies.find((vacancy) => vacancy.key === value)?.label || value
      : value).join(' · ') || 'Всего';
  }

  return <div className={embedded ? 'space-y-5' : 'max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5'}>
    <Card><div className="flex flex-wrap items-start justify-between gap-5"><div><h1 className="text-[28px] font-bold">{embeddedView === 'config' ? 'Новый отчёт' : embeddedView === 'ready' ? 'Готовый отчёт' : 'Годовой кадровый доклад'}{snapshot && ' · '+snapshot.year}</h1><p className="text-[#4A5363]">{snapshot?.scope_label}</p>{snapshot&&<p className="text-[13px]">С {snapshot.period_start} до {snapshot.period_end_exclusive} (исключительно)</p>}</div>
      <div className="flex flex-wrap gap-3 items-end"><label>Версия доклада<select aria-label="Версия доклада" className={field+' block'} value={id} disabled={busy} onChange={(e)=>setId(e.target.value)}><option value="">Выберите снимок</option>{versions.map((v)=><option key={v.snapshot_id} value={v.snapshot_id}>{v.year} · {v.extracted_at.slice(0,10)} · {v.snapshot_id.slice(0,6)}</option>)}</select></label>{!embedded && <Btn disabled={!snapshot||busy} onClick={()=>download('/xlsx')}>Скачать годовой XLSX</Btn>}</div></div>
      {snapshot&&<div className="mt-3"><Badge>{snapshot.mode==='demo'?'Учебный снимок':'Рабочий снимок'}</Badge></div>}
      {!embedded && <div className="flex flex-wrap gap-4 mt-5">{REPORT_TABS.map((item)=><button key={item.id} type="button" aria-pressed={tab === item.id} disabled={busy} onClick={()=>{setTab(item.id);setApplied(null);}} className={`text-[15px] font-semibold pb-2 border-b-2 ${tab===item.id?'text-[#1F4FD1] border-[#1F4FD1]':'border-transparent'}`}>{item.label}</button>)}</div>}
    </Card>
    {error&&<Card><p role="alert" className="text-[#A3171B]">{error}</p><Btn onClick={()=>setReload((n)=>n+1)}>Повторить</Btn></Card>}
    {!id&&!error&&<Card>{loadingVersions ? 'Загружаем список снимков…' : 'Доступных снимков пока нет.'}</Card>}
    {id&&!snapshot&&!error&&<Card>Загружаем снимок…</Card>}
    {snapshot&&tab==='overview'&&<>
      <div className="grid sm:grid-cols-3 gap-4">{Object.entries(snapshot.totals).map(([key,cell])=><Kpi key={key} label={metricNames[key]||key} value={show(cell)} caption={statuses[cell.status]} />)}</div>
      <ReportBars title="Итоги подбора за год" points={Object.entries(snapshot.totals).map(([key, cell]) => point(metricNames[key] || key, cell))} />
      <Card><h2 className="text-[20px] font-bold mb-4">Выводы и основания</h2>{findings.map((finding,index)=><details key={index} className="border-b border-[#E1E5EB] py-3"><summary className="font-medium">{finding.statement}</summary><p className="text-[13px] text-[#4A5363] mt-2">{finding.section}. Основание — фиксированный снимок {snapshot.year} года, выгрузка {snapshot.extracted_at.slice(0,10)}. Полнота и первичные показатели доступны на вкладках динамики и покрытия.</p></details>)}</Card>
    </>}
    {snapshot&&tab==='dynamics'&&<>
      <div className="grid lg:grid-cols-2 gap-5">{Object.keys(snapshot.totals).map((key) => <ReportBars key={key} title={metricNames[key] || key} points={snapshot.months.map((month) => point(monthLabel(month.month), month.metrics[key]))} />)}</div>
      <Card className="overflow-x-auto"><h2 className="text-[20px] font-bold mb-4">Месячная динамика</h2><table className="w-full text-left text-[14px]"><thead><tr><th>Месяц</th>{Object.keys(snapshot.totals).map((key)=><th key={key}>{metricNames[key] || key}</th>)}</tr></thead><tbody>{snapshot.months.map((month)=><tr key={month.month} className="border-t border-[#E1E5EB]"><td className="py-3">{monthLabel(month.month)}</td>{Object.keys(snapshot.totals).map((key)=><td key={key}><Value cell={month.metrics[key]}/></td>)}</tr>)}</tbody></table></Card>
    </>}
    {snapshot&&(tab==='builder'||tab==='staff')&&<>
      {embeddedView !== 'ready' && <div className={embedded ? 'grid items-start gap-5 lg:grid-cols-[2fr_1fr]' : ''}><Card>
      <h2 className="text-[20px] font-bold mb-4">{tab==='staff'?'Штат и ответы подразделений':'Конструктор среза'}</h2>
      <fieldset disabled={busy} className="flex gap-4 items-end flex-wrap">
        <label>С месяца<input type="number" min={1} max={12} className={field+' block w-24'} value={first} onChange={(e)=>{setFirst(+e.target.value);setApplied(null);}}/></label>
        <label>По месяц<input type="number" min={first} max={12} className={field+' block w-24'} value={last} onChange={(e)=>{setLast(+e.target.value);setApplied(null);}}/></label>
        {tab==='builder'?<>
          <label>Вакансия<select aria-label="Вакансия среза" className={field+' block'} value={vacancy} onChange={(e)=>{setVacancy(e.target.value);setApplied(null);}}><option value="">Все вакансии</option>{catalog?.vacancies.map((v)=><option key={v.key} value={v.key}>{v.label}</option>)}</select></label>
          <label>Показатель<select aria-label="Показатель" className={field+' block'} value={metric} onChange={(e)=>{setMetric(e.target.value);setApplied(null);}}>{catalog?.metrics.map((m)=><option key={m.key} value={m.key}>{m.label}</option>)}</select></label>
          <label>Группировка<select aria-label="Группировка" className={field+' block'} value={group} onChange={(e)=>{setGroup(e.target.value);setApplied(null);}}><option value="month">Месяц</option><option value="quarter">Квартал</option><option value="vacancy">Вакансия</option><option value="total">Весь срез</option></select></label>
        </>:<label>Подразделение<select aria-label="Подразделение" className={field+' block'} value={department} onChange={(e)=>{setDepartment(e.target.value);setApplied(null);}}><option value="">Все подразделения</option>{catalog?.departments?.map((d)=><option key={d.key} value={d.key}>{d.label}</option>)}</select></label>}
        <Btn variant="primary" disabled={busy||!catalog||first<1||last>12||first>last} onClick={() => void query()}>{embedded ? 'Сформировать отчёт' : 'Применить'}</Btn>
        {!embedded && <Btn disabled={busy||!applied} onClick={()=>applied&&download(tab==='staff'?'/operations/xlsx':'/query/xlsx',applied)}>Скачать срез XLSX</Btn>}
      </fieldset></Card>{embedded && <Card><h2 className="mb-3 text-[17px] font-bold">Формат отчёта</h2><Badge tone="blue">Excel (.xlsx)</Badge></Card>}</div>}
      {embeddedView === 'ready' && !analysis && !error && <Card>Сформируйте отчёт из выбранного снимка и показателя.</Card>}
      {embeddedView === 'ready' && applied && <Card className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-[14px] font-semibold">Месяцы {String(applied.start_month)}–{String(applied.end_month)}</p>
        <Btn variant="primary" disabled={busy} onClick={() => download('/query/xlsx', applied)}>Скачать XLSX</Btn>
      </Card>}
      {analysis&&tab==='builder'&&embeddedView!=='config'&&<>
        {Object.keys(analysis.totals).map((key) => <ReportBars key={key} title={catalog?.metrics.find((m)=>m.key===key)?.label||key} points={analysis.rows.map((row) => point(sliceLabel(row.dimensions), row.metrics[key]))} />)}
        <Card className="overflow-x-auto">{!applied&&<p className="text-[#8A4B0A] mb-3">Нажмите «Применить», чтобы обновить результат по выбранным параметрам.</p>}<table className="w-full text-left"><thead><tr><th>Срез</th>{Object.keys(analysis.totals).map((key)=><th key={key}>{catalog?.metrics.find((m)=>m.key===key)?.label||key}</th>)}</tr></thead><tbody>{analysis.rows.map((row,index)=><tr key={index} className="border-t border-[#E1E5EB]"><td className="py-3">{sliceLabel(row.dimensions)}</td>{Object.keys(analysis.totals).map((key)=><td key={key}><Value cell={row.metrics[key]}/></td>)}</tr>)}</tbody></table></Card>
      </>}
      {operations&&tab==='staff'&&(operations.available ? <>
        {!applied&&<Card>Нажмите «Применить», чтобы обновить результат по выбранным параметрам.</Card>}
        <div className="grid lg:grid-cols-2 gap-5"><ReportBars title="Численность по подразделениям" points={operations.by_department.map((d) => point(d.label,d.workforce.headcount))} /><ReportBars title="Открытые передачи по подразделениям" points={operations.by_department.map((d) => point(d.label,d.handoffs.open))} color="#7C5CDB" /></div>
        <Card><div className="grid sm:grid-cols-3 gap-4">{Object.entries({...operations.workforce,...operations.handoffs}).map(([key,cell])=><Kpi key={key} label={metricNames[key]||key} value={show(cell)} caption={statuses[cell.status]}/>)}</div><table className="w-full mt-5"><thead><tr className="text-left"><th>Подразделение</th><th>Численность</th><th>Открытые передачи</th></tr></thead><tbody>{operations.by_department.map((d)=><tr key={d.key}><td>{d.label}</td><td><Value cell={d.workforce.headcount}/></td><td><Value cell={d.handoffs.open}/></td></tr>)}</tbody></table></Card>
      </> : <Card>Источник кадрового учёта не включён в этот снимок.</Card>)}
    </>}
    {snapshot&&tab==='coverage'&&<>
      <ReportBars title="Охват помесячных показателей" points={Object.entries(statuses).map(([status, label]) => ({ label, value: snapshot.months.flatMap((month) => Object.values(month.metrics)).filter((cell) => cell.status === status).length }))} color="#7C5CDB" />
      <Card><h2 className="text-[20px] font-bold mb-4">Полнота источников</h2>{Object.entries(snapshot.totals).map(([key,cell])=><div key={key} className="border-b border-[#E1E5EB] py-3"><strong>{metricNames[key] || key}</strong><p>{statuses[cell.status]} · {cell.reason_codes.map((code)=>reasons[code]||'Ограничение источника').join(', ')||'Ограничения не указаны'}</p></div>)}<p className="mt-4">Без даты отклика — {snapshot.quality.undated_applications}. Без даты интервью — {snapshot.quality.undated_interviews}.</p></Card>
    </>}
  </div>;
}
