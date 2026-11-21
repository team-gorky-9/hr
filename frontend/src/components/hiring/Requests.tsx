import { useEffect, useState } from 'react';
import { Card, Btn, Badge } from '../shared/ui';
import { ActionForm, textField, longField, reasonField, type Field } from './ActionForm';
import { hiringRequest, hiringDownload, hiringStatus, uploadBody, type Audience, type CandidateRequest, type Message, type Vacancy } from '../../api/hiring';
export function Requests({ token, audience, run, busy }: { token: string; audience: Audience; run: (action: () => Promise<void>) => Promise<void>; busy: boolean }) {
  const [rows, setRows] = useState<CandidateRequest[]>([]), [selected, setSelected] = useState<CandidateRequest | null>(null);
  const [vacancies, setVacancies] = useState<Vacancy[]>([]), [messages, setMessages] = useState<Message[]>([]);
  const candidate = audience === 'candidate';
  const load = async () => { const [list, catalog] = await Promise.all([
    hiringRequest<{ items: CandidateRequest[] }>(token, '/candidate-requests'),
    hiringRequest<{ items: Vacancy[] }>(token, '/candidate-portal/vacancies'),
  ]); setRows(list.items); setVacancies(catalog.items); };
  useEffect(() => { setRows([]); setSelected(null); setMessages([]); void run(load).catch(() => {}); }, [token]);
  async function open(id: string) {
    const [row, inbox] = await Promise.all([hiringRequest<CandidateRequest>(token, '/candidate-requests/' + id), hiringRequest<{ items: Message[] }>(token, `/candidate-requests/${id}/messages`)]);
    setSelected(row); setMessages(inbox.items);
  }
  async function command(action: string, values: unknown, method?: string) {
    await hiringRequest(token, `/candidate-requests/${selected!.id}${action ? '/' + action : ''}`, values, method);
    await load(); await open(selected!.id);
  }
  const vacancyField: Field = { name: 'vacancy', label: 'Вакансия (учебный снимок сервера)', options: [['', 'Без выбранной вакансии'], ...vacancies.map(v => [v.ref.id, v.title] as [string, string])] };
  const vacancy = (id: string) => vacancies.find(v => v.ref.id === id)?.ref;
  const contactFields: Field[] = [longField('message', 'Расскажите о себе и желаемой работе'), { name: 'channel', label: 'Способ связи', options: [['email', 'Электронная почта'], ['phone', 'Телефон'], ['messenger', 'Мессенджер'], ['other', 'Другой']] }, textField('contact', 'Контакт'), { ...vacancyField, optional: true }];
  const r = selected;
  const active = r && !['closed', 'withdrawn'].includes(r.status);
  return <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
    <div className="lg:col-span-4 space-y-4">
      <Card><div className="flex justify-between items-center mb-4"><h2 className="text-xl font-bold">{candidate ? 'Мои обращения' : 'Обращения кандидатов'}</h2><Btn disabled={busy} variant="link" onClick={() => void run(load).catch(() => {})}>Обновить</Btn></div>
        {!rows.length && <p className="text-[#616977]">Обращений пока нет.</p>}
        {rows.map(row => <button key={row.id} onClick={() => void run(() => open(row.id)).catch(() => {})} className={`block w-full text-left rounded-xl border p-4 mb-3 ${row.id === r?.id ? 'border-[#1F4FD1] bg-[#EEF3FE]' : 'border-[#E1E5EB]'}`}>
          <strong>{row.vacancy?.title || 'Обращение без вакансии'}</strong><p className="text-sm my-2">{row.number || 'Черновик'} · {hiringStatus[row.status] || row.status}</p>
          {!!row.unread_messages && <Badge tone="amber">Сообщений: {row.unread_messages}</Badge>}
        </button>)}
      </Card>
      {candidate && <Card><ActionForm title="Новое обращение" fields={contactFields} busy={busy} submit="Создать черновик" onSubmit={v => run(async () => {
        const row = await hiringRequest<CandidateRequest>(token, '/candidate-requests', { message: v.message, contact: { channel: v.channel, value: v.contact }, vacancy_ref: vacancy(v.vacancy) || null });
        await load(); await open(row.id);
      })} /></Card>}
    </div>
    <div className="lg:col-span-8 space-y-4">
      {!r && <Card><h2 className="text-xl font-bold">{candidate ? 'Личный кабинет' : 'Рассмотрение обращения'}</h2><p className="text-[#616977] mt-2">Выберите обращение, чтобы увидеть документы, уточнения и результат.</p></Card>}
      {r && <>
        <Card><div className="flex justify-between gap-3"><h2 className="text-xl font-bold">{r.vacancy?.title || 'Без выбранной вакансии'}</h2><Badge tone="blue">{hiringStatus[r.status]}</Badge></div>
          <p className="text-sm text-[#616977] mt-2">{r.number || 'Черновик'} · редакция {r.revision}</p><p className="mt-4 whitespace-pre-wrap">{r.message}</p><p className="mt-2 text-sm">Контакт: {r.contact.value} · сообщён кандидатом</p>
          {r.target_question && <p className="mt-4 text-amber-800">Цель обращения требует уточнения: {({ no_target: 'вакансия не выбрана', vacancy_closed: 'вакансия закрыта', vacancy_unknown: 'редакция вакансии неизвестна' } as Record<string, string>)[r.target_question] || r.target_question}.</p>}
          {r.withdrawal && <p className="mt-4">{r.withdrawal.notice || 'Обращение отозвано.'} {r.withdrawal.reason}</p>}
        </Card>
        {r.information_request && <Card className="!bg-[#FFF8E8] !border-[#F3E2B5]"><h3 className="font-bold">{r.information_request.answered ? 'Уточнение получено' : 'Нужно ответить кадровику'}</h3><p className="mt-2">{r.information_request.public_message}</p><ul className="list-disc pl-5 my-3">{r.information_request.requested_items.map(i => <li key={i}>{i}</li>)}</ul>
          {candidate && r.status === 'needs_information' && <ActionForm title="Ответить на запрос" busy={busy} fields={[longField('text', 'Ответ кадровику')]} submit="Отправить дополнение" onSubmit={v => run(() => command('addendum', { expected_revision: r.revision, text: v.text, document_ids: r.documents.filter(d => d.kind === 'candidate_addendum').map(d => d.id) }))} />}
        </Card>}
        {!!r.addenda.length && <Card><h3 className="font-bold mb-3">Дополнения кандидата</h3>{r.addenda.map((a, i) => <p key={i} className="border-b py-2 whitespace-pre-wrap">{a.text}</p>)}</Card>}
        <Card><h3 className="font-bold mb-3">Документы</h3>{!r.documents.length && <p className="text-sm text-[#616977] mb-3">Документы пока не приложены.</p>}{r.documents.map(d => <div key={d.id} className="flex justify-between gap-3 py-2 border-b"><span>{d.original_name}</span><Btn variant="link" onClick={() => void run(() => hiringDownload(token, `/candidate-requests/${r.id}/documents/${d.id}/content`, d.original_name)).catch(() => {})}>Скачать</Btn></div>)}
          {candidate && ['draft', 'submitted', 'needs_information'].includes(r.status) && <div className="mt-4"><ActionForm title="Приложить документ" busy={busy} fields={[{ name: 'file', label: 'Файл резюме или дополнения', type: 'file' }]} onSubmit={(_, form) => run(async () => { const file = new FormData(form).get('file') as File; await command('documents', uploadBody(file, r.status === 'draft' ? 'candidate_resume' : 'candidate_addendum')); })} /></div>}
        </Card>
        {candidate && <Card><div className="space-y-3">
          {r.status === 'draft' && <><ActionForm title="Изменить черновик" busy={busy} fields={contactFields.map(f => ({ ...f, value: f.name === 'message' ? r.message : f.name === 'contact' ? r.contact.value : f.name === 'channel' ? r.contact.channel : r.vacancy_ref?.id }))} onSubmit={v => run(() => command('', { expected_revision: r.revision, message: v.message, contact: { channel: v.channel, value: v.contact }, ...(v.vacancy ? { vacancy_ref: vacancy(v.vacancy) } : { clear_vacancy: true }) }, 'PATCH'))} /><Btn variant="primary" disabled={busy} onClick={() => void run(() => command('submit', { expected_revision: r.revision })).catch(() => {})}>Подать обращение</Btn></>}
          {['submitted', 'needs_information', 'ready'].includes(r.status) && <ActionForm title="Выбрать вакансию" fields={[vacancyField]} busy={busy} onSubmit={v => run(() => command('choose-vacancy', { expected_revision: r.revision, vacancy_ref: vacancy(v.vacancy) }))} />}
          {active && <ActionForm title="Отозвать обращение" fields={[reasonField]} busy={busy} submit="Подтвердить отзыв" onSubmit={v => run(() => command('withdraw', { expected_revision: r.revision, reason: v.reason }))} />}
        </div></Card>}
        {!candidate && active && <Card><h3 className="font-bold mb-4">Действия кадровика</h3><div className="space-y-3">
          {['submitted', 'needs_information', 'ready'].includes(r.status) && <ActionForm title="Запросить уточнение" busy={busy} fields={[longField('public_message', 'Вопрос кандидату'), longField('items', 'Какие сведения нужны — по одному на строку')]} onSubmit={v => run(() => command('information-request', { expected_revision: r.revision, public_message: v.public_message, requested_items: v.items.split('\n').map(x => x.trim()).filter(Boolean) }))} />}
          {['submitted', 'needs_information'].includes(r.status) && <ActionForm title="Подтвердить готовность к рассмотрению" busy={busy} fields={[longField('review_basis', 'Основание достаточности сведений')]} onSubmit={v => run(() => command('ready', { expected_revision: r.revision, review_basis: v.review_basis }))} />}
          {r.status === 'ready' && <ActionForm title="Зарегистрировать передачу в подбор" note="Ручное подтверждение уже существующих записей подбора. Автоматического обмена нет." busy={busy} fields={[textField('system', 'Система подбора'), textField('candidate', 'ID записи кандидата (UUID)'), textField('application', 'ID рассмотрения (UUID)'), vacancyField, longField('identity_basis', 'Основание связи с человеком'), textField('source_reference', 'Источник регистрации')]} onSubmit={v => run(() => command('record-consideration', { expected_revision: r.revision, candidate_ref: { system: v.system, id: v.candidate }, application_ref: { system: v.system, id: v.application }, selected_vacancy_ref: vacancy(v.vacancy), identity_basis: v.identity_basis, source_reference: v.source_reference }))} />}
          {['ready', 'forwarded'].includes(r.status) && <ActionForm title="Сообщить публичный результат" busy={busy} fields={[{ name: 'outcome', label: 'Результат', options: [...(r.status === 'forwarded' ? [['continue', 'Рассмотрение продолжается'] as [string, string]] : []), ['declined', 'Отказ'], ['no_open_opportunity', 'Нет открытой вакансии'], ['completed', 'Завершено']] }, longField('public_explanation', 'Объяснение для кандидата'), textField('next_action', 'Следующий шаг (обязателен при продолжении)', true), textField('source_reference', 'Источник решения')]} onSubmit={v => run(() => command('public-outcome', { expected_revision: r.revision, ...v, next_action: v.next_action || null }))} />}
        </div></Card>}
        {!!r.outcomes.length && <Card><h3 className="font-bold">Результат рассмотрения</h3>{r.outcomes.map((o, i) => <div key={i} className="mt-3"><p>{o.public_explanation}</p>{o.next_action && <p className="mt-2 text-[#1F4FD1]">Следующий шаг: {o.next_action}</p>}</div>)}</Card>}
        <Card><h3 className="font-bold mb-3">Сообщения в кабинете</h3>{!messages.length && <p className="text-sm text-[#616977]">Новых сообщений нет.</p>}{messages.map(m => <div key={m.id} className="py-3 border-b"><strong>{m.title}</strong><p className="my-2">{m.body}</p>{m.next_action && <p>{m.next_action}</p>}{candidate && !m.read_at && <Btn variant="link" disabled={busy} onClick={() => void run(async () => { await hiringRequest(token, `/candidate-requests/${r.id}/messages/${m.id}/read`, {}); await open(r.id); await load(); }).catch(() => {})}>Отметить прочитанным</Btn>}</div>)}</Card>
      </>}
    </div>
  </div>;
}



