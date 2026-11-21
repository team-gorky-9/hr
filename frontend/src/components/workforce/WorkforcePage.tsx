import { useEffect, useState, type FormEvent } from 'react';
import { Card, Btn, Badge } from '../shared/ui';
import { developmentRequest, type Session } from '../../api/development';
const input='block w-full border border-[#C9D0DB] rounded-lg px-3 py-2 text-[14px] bg-white';
type Assignment={id:string;revision:number;department_id:string;position_code:string;starts_on:string;ends_on:string|null};
type Employee={id:string;revision:number;display_name:string;account_actor_id:string|null;assignments?:Assignment[]};
type Department={id:string;revision:number;name:string;code:string};
type Program={template_code:string;id:string;revision:number;employee_id:string;status:string;workforce_assignment_id:string;completed_count:number;total_count:number;steps:{key:string;title:string;description:string;material_url:string|null;acknowledged_at:string|null}[]};
type Template={code:string;version:number;title:string};
type Actor={actor_id:string;login:string};
async function command<T>(session:Session,path:string,body:unknown,method='POST'):Promise<T>{
 const res=await fetch('/workforce-api'+path,{method,headers:{'Content-Type':'application/json',Authorization:'Bearer '+session.access_token,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
 const data=await res.json();if(!res.ok)throw new Error(data?.error?.message||'Ошибка кадрового сервиса');return data;
}
function values(event:FormEvent<HTMLFormElement>){event.preventDefault();return Object.fromEntries(new FormData(event.currentTarget)) as Record<string,string>;}
function Field({label,name,type='text',value,required=true}:{label:string;name:string;type?:string;value?:string;required?:boolean}){return <label className="block text-[14px]">{label}<input className={input} name={name} type={type} defaultValue={value} required={required}/></label>;}
export default function WorkforcePage({initialTab='employees'}:{initialTab?:'employees'|'onboarding'}){
 const [session,setSession]=useState<Session|null>(null);const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 const [tab,setTab]=useState(initialTab);const [employees,setEmployees]=useState<Employee[]>([]);const [departments,setDepartments]=useState<Department[]>([]);const [actors,setActors]=useState<Actor[]>([]);
 const [selected,setSelected]=useState<Employee|null>(null);const [programs,setPrograms]=useState<Program[]>([]);const [templates,setTemplates]=useState<Template[]>([]);
 const [mode,setMode]=useState('assign');const staff=Boolean(session?.actor.grants.some((g)=>g.role==='hr'||g.role==='admin'));
 const read=<T,>(path:string)=>developmentRequest<T>(session!.access_token,path);
 async function refresh(){if(!session)return;setError('');
  try{
   if(staff){const [es,ds,as]=await Promise.all([read<{items:Employee[]}>('/employees'),read<{items:Department[]}>('/departments'),read<{items:Actor[]}>('/actors')]);setEmployees(es.items);setDepartments(ds.items);setActors(as.items);if(selected)setSelected(await read<Employee>('/employees/'+selected.id));}
   const [ps,ts]=await Promise.all([read<{items:Program[]}>('/onboarding/programs'),read<{items:Template[]}>('/onboarding/templates')]);setPrograms(ps.items);setTemplates(ts.items);
  }catch(e){setError(e instanceof Error?e.message:'Не удалось прочитать данные');}
 }
 useEffect(()=>{void refresh();},[session]);
 async function run(action:()=>Promise<unknown>){setBusy(true);setError('');try{await action();await refresh();}catch(e){setError(e instanceof Error?e.message:'Не удалось сохранить');}finally{setBusy(false);}}
 function deptSelect(name='department_id'){return <label>Подразделение<select name={name} className={input} required><option value="">Выберите</option>{departments.map((d)=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>;}
 const basis=(v:Record<string,string>)=>({reference:v.reference,issued_on:v.issued_on});
 return <div className="max-w-[1240px] mx-auto px-6 py-8 space-y-5">
 <div className="flex justify-between"><h1 className="text-[28px] font-bold">{tab==='employees'?'Сотрудники и назначения':'Адаптация сотрудника'}</h1>{session&&<div className="flex gap-3 items-center"><Badge>{session.actor.login}</Badge><Btn onClick={()=>{void developmentRequest(session.access_token,'/session',undefined,'DELETE');setSession(null);setSelected(null);setEmployees([]);setPrograms([]);}}>Выйти</Btn></div>}</div>
 {error&&<Card><p role="alert" className="text-[#A3171B]">{error}</p><Btn onClick={refresh}>Обновить данные</Btn></Card>}
 {!session?<Card className="max-w-[500px]"><form className="space-y-3" onSubmit={async(e)=>{const v=values(e);setError('');setBusy(true);try{setSession(await developmentRequest<Session>(null,'/sessions',{login:v.login,password:v.password}));}catch(err){setError(err instanceof Error?err.message:'Ошибка входа');}finally{setBusy(false);}}}><Field name="login" label="Логин"/><Field name="password" label="Пароль" type="password"/><Btn type="submit" variant="primary" disabled={busy}>Войти</Btn></form></Card>:<>
 <div className="flex gap-3">{staff&&<Btn onClick={()=>setTab('employees')}>Сотрудники</Btn>}<Btn onClick={()=>setTab('onboarding')}>Адаптация</Btn><Btn onClick={refresh}>Обновить</Btn></div>
 {tab==='employees'&&staff&&<div className="grid grid-cols-[360px_1fr] gap-5 items-start">
 <div className="space-y-4"><Card><h2 className="text-[18px] font-bold mb-3">Сотрудники</h2>{employees.map((e)=><button key={e.id} className="block w-full text-left py-3 border-b border-[#E1E5EB] text-[#1F4FD1]" onClick={()=>void run(async()=>setSelected(await read<Employee>('/employees/'+e.id)))}>{e.display_name}</button>)}{!employees.length&&<p>Сотрудников пока нет.</p>}</Card>
 <Card><h2 className="text-[18px] font-bold mb-3">Добавить сотрудника</h2><form className="space-y-3" onSubmit={(e)=>{const v=values(e);void run(async()=>{const result=await command<Employee>(session,'/employees',{display_name:v.name,source_refs:[{system:'manual',id:v.source}],account_actor_id:v.actor||null,confirmation_basis:v.basis});setSelected(await read<Employee>('/employees/'+result.id));});}}>
 <Field label="ФИО" name="name"/><Field label="Реквизиты источника" name="source"/><Field label="Основание подтверждения" name="basis"/><label>Кабинет сотрудника<select className={input} name="actor"><option value="">Связать позднее</option>{actors.map((a)=><option key={a.actor_id} value={a.actor_id}>{a.login}</option>)}</select></label><Btn type="submit" variant="primary" disabled={busy}>Создать сотрудника</Btn></form></Card></div>
 {selected?<div className="space-y-4"><Card><h2 className="text-[22px] font-bold">{selected.display_name}</h2><p className="text-[#4A5363]">Назначения и их основания</p>{selected.assignments?.map((a)=><div key={a.id} className="border-t border-[#E1E5EB] py-3"><strong>{a.position_code}</strong><p>{departments.find((d)=>d.id===a.department_id)?.name} · {a.starts_on} — {a.ends_on||'действует'}</p></div>)}</Card>
 <Card><div className="flex gap-2 mb-4">{[['assign','Назначить'],['correct','Исправить'],['transfer','Перевести'],['end','Завершить'],['employee','Карточка']].map(([key,label])=><Btn key={key} onClick={()=>setMode(key)}>{label}</Btn>)}</div>
 <form key={selected.id+mode} className="space-y-3" onSubmit={(e)=>{const v=values(e);void run(async()=>{
  if(mode==='employee'){await command(session,'/employees/'+selected.id,{expected_revision:selected.revision,display_name:v.name,account_actor_id:v.actor||null,correction_basis:v.reason},'PATCH');return;}
  const a=selected.assignments?.find((x)=>x.id===v.assignment);
  if(mode==='assign')await command(session,'/employees/'+selected.id+'/assignments',{department_id:v.department_id,position_code:v.position,starts_on:v.starts_on,basis:basis(v)});
  if(mode==='correct'&&a)await command(session,'/assignments/'+a.id+'/correct',{expected_revision:a.revision,starts_on:v.starts_on,reason:v.reason,basis:basis(v)});
  if(mode==='transfer'&&a)await command(session,'/assignments/'+a.id+'/transfer',{expected_revision:a.revision,ends_on:v.ends_on,new_department_id:v.department_id,new_position_code:v.position,starts_on:v.starts_on,basis:basis(v)});
  if(mode==='end'&&a)await command(session,'/assignments/'+a.id+'/end',{expected_revision:a.revision,ends_on:v.ends_on,reason:v.reason});
 });}}>
 {mode==='employee'?<><Field label="ФИО" name="name" value={selected.display_name}/><label>Кабинет<select className={input} name="actor" defaultValue={selected.account_actor_id||''}><option value="">Без связи</option>{actors.map((a)=><option key={a.actor_id} value={a.actor_id}>{a.login}</option>)}</select></label><Field label="Основание исправления" name="reason"/></>:<>
 {mode!=='assign'&&<label>Назначение<select className={input} name="assignment" required>{selected.assignments?.map((a)=><option key={a.id} value={a.id}>{a.position_code} · {a.starts_on}</option>)}</select></label>}
 {(mode==='assign'||mode==='transfer')&&<>{deptSelect()}<Field label="Код должности" name="position"/></>}
 {mode!=='end'&&<Field label="Дата начала" type="date" name="starts_on"/>}
 {(mode==='end'||mode==='transfer')&&<Field label="Дата окончания прежнего назначения" type="date" name="ends_on"/>}
 {(mode==='end'||mode==='correct')&&<Field label="Причина" name="reason"/>}
 {mode!=='end'&&<><Field label="Реквизиты основания" name="reference"/><Field label="Дата основания" type="date" name="issued_on"/></>}
 </>}<Btn type="submit" variant="primary" disabled={busy}>Сохранить</Btn></form></Card>
 <Card><h2 className="text-[18px] font-bold mb-3">Назначить адаптацию</h2><form className="space-y-3" onSubmit={(e)=>{const v=values(e);const t=templates.find((t)=>t.code+':'+t.version===v.template);if(t)void run(()=>command(session,'/onboarding/programs',{workforce_assignment_id:v.assignment,template_code:t.code,template_version:t.version}));}}>
 <label>Назначение<select className={input} name="assignment" required>{selected.assignments?.map((a)=><option key={a.id} value={a.id}>{a.position_code} · {a.starts_on}</option>)}</select></label><label>Программа<select className={input} name="template" required>{templates.map((t)=><option key={t.code+':'+t.version} value={t.code+':'+t.version}>{t.title} · версия {t.version}</option>)}</select></label><Btn type="submit" variant="primary" disabled={busy}>Назначить программу</Btn></form></Card></div>:<Card>Выберите сотрудника.</Card>}
 </div>}
 {tab==='onboarding'&&<div className="space-y-4">{programs.length===0&&<Card>Доступных программ пока нет.</Card>}{programs.map((program)=><Card key={program.id}><div className="flex justify-between"><h2 className="text-[20px] font-bold">{templates.find((t)=>t.code===program.template_code)?.title||'Вводная программа'}</h2><Badge>{program.completed_count} из {program.total_count}</Badge></div>{program.steps.map((step)=><div key={step.key} className="border-t border-[#E1E5EB] py-4 mt-3"><h3 className="font-semibold">{step.title}</h3><p className="text-[#4A5363] my-2">{step.description}</p>{step.material_url&&<a className="text-[#1F4FD1] block mb-2" href={step.material_url} target="_blank" rel="noreferrer">Открыть материал</a>}{step.acknowledged_at?<Badge tone="green">Ознакомление подтверждено</Badge>:!staff&&<Btn disabled={busy||program.status!=='active'} onClick={()=>void run(()=>command(session,`/onboarding/programs/${program.id}/steps/${step.key}/acknowledge`,{expected_revision:program.revision}))}>Подтвердить ознакомление</Btn>}</div>)}{staff&&program.status==='active'&&<form className="flex gap-3 mt-3" onSubmit={(e)=>{const v=values(e);void run(()=>command(session,'/onboarding/programs/'+program.id+'/cancel',{expected_revision:program.revision,reason:v.reason}));}}><Field name="reason" label="Причина отмены"/><Btn type="submit" disabled={busy}>Отменить программу</Btn></form>}</Card>)}</div>}
 </>}
 </div>;
}
