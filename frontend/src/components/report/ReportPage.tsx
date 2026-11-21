import { useEffect, useState } from 'react';
import { request } from '../../api/archive';
import { annualReportsPath as path, downloadWorkbook } from '../../api/reports';
import { Card, Btn, Kpi, Badge } from '../shared/ui';
import { REPORT_TABS, type ReportTab } from './ReportShell';
import ReportBars from './ReportBars';
import { AnnualTrends, Findings, monthLabel, type AnnualSeries, type Cell } from './AnnualVisuals';

type Version = { snapshot_id: string; year: number; scope_label: string; mode: string; extracted_at: string };
type Snapshot = Version & AnnualSeries & {
  period_start: string; period_end_exclusive: string; observed_until: string;
  totals: Record<string, Cell>;
  quality: { undated_applications: number; undated_interviews: number; duplicates: number };
};
type Catalog = {
  snapshot_id: string;
  metrics: { key: string; label: string; unit: string; definition: string }[];
  vacancies: { key: string; label: string }[];
  departments?: { key: string; label: string }[];
};
type Analysis = { totals: Record<string, Cell>; rows: { dimensions: Record<string, string | number>; metrics: Record<string, Cell> }[] };
type Operations = { available: boolean; workforce: Record<string, Cell>; handoffs: Record<string, Cell>; months: { month: string; handoffs: Record<string, Cell> }[]; by_department: { key: string; label: string; workforce: Record<string, Cell>; handoffs: Record<string, Cell> }[] };
const metricNames: Record<string, string> = { applications_received: 'Поступившие отклики', phone_interviews_held: 'Телефонные собеседования', applications_with_phone_interview: 'Отклики с разговором', headcount:'Численность', authorized_fte:'Штатные ставки', occupied_fte:'Занятые ставки', hires:'Приняты', exits:'Выбыли', open:'Открытые передачи', open_over_15:'Ожидают более 15 календарных дней', sent:'Передано', answered:'Ответов', median_response_days:'Медиана ответа, дни' };
const statuses: Record<string, string> = { complete:'Полные данные', partial:'Неполный охват', unavailable:'Источник недоступен', future:'За пределами наблюдения' };
const reasons: Record<string, string> = { coverage_gap:'Неполный период', coverage_unknown:'Охват неизвестен', missing_business_date:'Отсутствуют даты событий', outside_period:'За пределами периода', incomplete_coverage:'Сравнение недоступно из-за неполноты', zero_baseline:'Нулевая база' };
const show = (cell: Cell) => cell.value === null ? 'Нет данных' : (cell.status === 'partial' ? 'Не менее ' : '') + cell.value.toLocaleString('ru-RU');
const field = 'border border-[#C9D0DB] rounded-xl px-3 py-2 bg-white text-[14px]';
const point = (label: string, cell?: Cell) => ({ label, value: cell?.value ?? null, partial: cell?.status === 'partial' });
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
  const [futureNotice, setFutureNotice] = useState(false);
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
    <div data-tour="report-header" className={'bg-white border border-[#E1E5EB] rounded-2xl px-6 pt-6 ' + (embedded ? 'pb-6' : '')}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><div className="flex flex-wrap items-center gap-3"><h1 className="text-[28px] font-bold text-[#141A24]">{embeddedView === 'config' ? 'Новый отчёт' : embeddedView === 'ready' ? 'Готовый отчёт' : 'Годовой кадровый доклад'}{snapshot && ' · '+snapshot.year}</h1>{snapshot && <Badge tone={snapshot.mode==='demo' ? 'amber' : 'gray'}>{snapshot.mode==='demo'?'Учебный':'Рабочий'}</Badge>}</div>
          {snapshot && <p className="text-[16px] text-[#4A5363] mt-1">{snapshot.scope_label} · период с {snapshot.period_start} до {snapshot.period_end_exclusive}</p>}
        </div>
        <div className="flex flex-wrap gap-3 items-end"><label className="text-[13px] font-semibold text-[#4A5363]">Версия доклада<select aria-label="Версия доклада" className="block mt-1 min-w-[200px] border border-[#C9D0DB] rounded-xl px-4 py-3 text-[16px] bg-white" value={id} disabled={busy} onChange={(e)=>setId(e.target.value)}><option value="">Выберите снимок</option>{versions.map((v)=><option key={v.snapshot_id} value={v.snapshot_id}>{v.year} · {v.extracted_at.slice(0,10)} · {v.snapshot_id.slice(0,6)}</option>)}</select></label>{!embedded && <Btn disabled={!snapshot||busy} onClick={()=>download('/xlsx')}>Скачать годовой XLSX</Btn>}</div>
      </div>
      {!embedded && <div className="flex flex-wrap gap-x-7 mt-6">{REPORT_TABS.map((item)=><button key={item.id} type="button" aria-pressed={tab === item.id} disabled={busy} onClick={()=>{setTab(item.id);setApplied(null);}} className={`text-[16px] font-semibold pb-3 border-b-[3px] transition-colors ${tab===item.id?'text-[#1F4FD1] border-[#1F4FD1]':'text-[#141A24] border-transparent hover:text-[#1F4FD1]'}`}>{item.label}</button>)}</div>}
    </div>
    {error&&<Card><p role="alert" className="text-[#A3171B]">{error}</p><Btn onClick={()=>setReload((n)=>n+1)}>Повторить</Btn></Card>}
    {!id&&!error&&<Card>{loadingVersions ? 'Загружаем список снимков…' : 'Доступных снимков пока нет.'}</Card>}
    {id&&!snapshot&&!error&&<Card>Загружаем снимок…</Card>}
    {snapshot&&tab==='overview'&&<>
      <div className="grid sm:grid-cols-3 gap-4">{Object.entries(snapshot.totals).map(([key,cell])=><Kpi key={key} label={metricNames[key]||key} value={show(cell)} caption={statuses[cell.status]} />)}</div>
      <Findings key={id} rows={findings} year={snapshot.year} onOpenBuilder={() => setTab('builder')} onDownload={() => void download('/xlsx')} />
      <AnnualTrends key={id} series={snapshot} />
    </>}
    {snapshot&&tab==='dynamics'&&<>
      <AnnualTrends key={id} series={snapshot} dynamics />
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
      </fieldset></Card>{embedded && <Card className="space-y-3"><h2 className="text-[17px] font-bold">Формат отчёта</h2><div className="flex flex-wrap items-center gap-2"><Badge tone="blue">Excel (.xlsx)</Badge><Btn variant="link" onClick={() => setFutureNotice(true)}>PDF</Btn><Btn variant="link" onClick={() => setFutureNotice(true)}>Презентация</Btn></div>{futureNotice && <p role="status" className="text-[14px] text-[#4A5363]">Будет добавлено позже</p>}</Card>}</div>}
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
        <div className="grid lg:grid-cols-2 gap-5">
          {([{ title: 'На конец выбранного периода', tone: 'blue', keys: ['authorized_fte','occupied_fte','headcount','open'] }, { title: 'За выбранный период', tone: 'purple', keys: ['hires','exits','answered','median_response_days'] }] as const).map(({ title, tone, keys }) => <Card key={title}>
            <div className="flex justify-between gap-2"><h2 className="text-[20px] font-bold">{title}</h2><Badge tone={tone}>{tone === 'blue' ? 'На дату' : 'За период'}</Badge></div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">{keys.map((key) => <div key={key}><strong>{metricNames[key]}</strong><div className="mt-1"><Value cell={operations.workforce[key] ?? operations.handoffs[key]} /></div></div>)}</div>
          </Card>)}
        </div>
        <div className="grid lg:grid-cols-[2fr_1fr] gap-5">
          <Card className="overflow-x-auto"><h2 className="text-[22px] font-bold">Рейтинг по открытым передачам</h2><table className="w-full mt-5"><thead><tr className="text-left"><th>Подразделение</th><th>Численность</th><th>Открытые передачи</th></tr></thead><tbody>{[...operations.by_department].sort((a,b)=>(b.handoffs.open?.value??0)-(a.handoffs.open?.value??0)).map((d)=><tr key={d.key} className="border-t border-[#E1E5EB]"><td className="py-3">{d.label}</td><td><Value cell={d.workforce.headcount}/></td><td><Value cell={d.handoffs.open}/></td></tr>)}</tbody></table></Card>
          <Card className="space-y-3"><h2 className="text-[22px] font-bold">Ответы по месяцам</h2><div className="flex items-end gap-2 h-[170px]">{operations.months.map((m) => <div key={m.month} className="flex flex-col justify-end items-center flex-1 h-full gap-1"><strong className="text-[12px]">{m.handoffs.answered?.value ?? '—'}</strong><div className="w-full bg-[#5B80E0] rounded-t" style={{height: 80*(m.handoffs.answered?.value??0)/Math.max(1,...operations.months.map((month)=>month.handoffs.answered?.value??0))+'%'}} /></div>)}</div><div className="flex gap-2 text-[12px] text-[#4A5363]">{operations.months.map((m)=><span key={m.month} className="flex-1 text-center">{monthLabel(m.month)}</span>)}</div></Card>
        </div>
      </> : <Card>Источник кадрового учёта не включён в этот снимок.</Card>)}
    </>}
    {snapshot&&tab==='coverage'&&<>
      <Card className="space-y-4"><h2 className="text-[22px] font-bold">Охват помесячных показателей</h2><div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3.5">{Object.entries(statuses).map(([status,label],index) => <div key={status} className={'rounded-2xl border p-4 min-h-[120px] '+ ['bg-white border-[#E1E5EB]','bg-[#FFEFD9] border-[#F3C98B]','bg-[#EEF1F5] border-dashed border-[#C9D0DB]','bg-[#F1EDFF] border-[#D5C9F5]'][index]}><p className="text-[26px] font-bold">{snapshot.months.flatMap((month)=>Object.values(month.metrics)).filter((cell)=>cell.status===status).length}</p><p>{label}</p></div>)}</div></Card>
      <Card><h2 className="text-[20px] font-bold mb-4">Полнота источников</h2>{Object.entries(snapshot.totals).map(([key,cell])=><div key={key} className="border-b border-[#E1E5EB] py-3"><strong>{metricNames[key] || key}</strong><p>{statuses[cell.status]} · {cell.reason_codes.map((code)=>reasons[code]||'Ограничение источника').join(', ')||'Ограничения не указаны'}</p></div>)}<p className="mt-4">Без даты отклика — {snapshot.quality.undated_applications}. Без даты интервью — {snapshot.quality.undated_interviews}.</p></Card>
    </>}
  </div>;
}
