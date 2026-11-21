const env = (import.meta as ImportMeta & { env: Record<string, string> }).env;
const base = (env.VITE_HIRING_API_BASE || '/hiring-api').replace(/\/$/, '');
export type Audience = 'staff' | 'candidate';
export interface VacancyRef { system: string; id: string; revision: number }
export interface Vacancy { ref: VacancyRef; title: string; description: string }
export interface Document { id: string; original_name: string; kind: string }
export interface CandidateRequest {
  id: string; number: string | null; revision: number; status: string; message: string;
  contact: { channel: string; value: string }; vacancy: { title: string } | null; vacancy_ref: VacancyRef | null;
  target_question: string | null; documents: Document[]; unread_messages: number;
  information_request: { public_message: string; requested_items: string[]; answered: boolean } | null;
  addenda: { text: string; document_ids: string[]; added_at: string }[];
  outcomes: { outcome: string; public_explanation: string; next_action: string | null }[];
  withdrawal: { reason: string; notice?: string } | null;
}
export interface Message { id: string; title: string; body: string; next_action: string | null; read_at: string | null }
export interface Item { id: string; title: string; revision: number; required: boolean; status: string; document_ids: string[]; review_reason: string | null }
export interface HiringCase {
  id: string; revision: number; status: string; checklist: Item[]; starts_on: string | null;
  position_code?: string; selection?: { candidate_ref: { display_name: string }; position_code: string };
  workforce_status?: string; employee_id?: string; assignment_id?: string;
  provenance?: { source_mode: string }; is_synthetic?: boolean;
}
export const hiringStatus: Record<string, string> = {
  draft: 'Черновик', submitted: 'Подано', needs_information: 'Нужно уточнение', ready: 'Готово',
  forwarded: 'Передано в подбор', closed: 'Завершено', withdrawn: 'Отозвано', preparing: 'Подготовка',
  awaiting_documents: 'Ожидаем документы', started: 'Начало зарегистрировано', requested: 'Нужен документ',
  received: 'Получен', accepted: 'Принят', needs_revision: 'Нужно исправление', not_sent: 'Не передано',
  manual_required: 'Нужно ручное подтверждение', registered: 'Назначение зарегистрировано',
};
export function hiringToken(audience: Audience, token?: string) {
  return token || env.VITE_HIRING_TOKEN || `fixture:${audience === 'staff' ? 'hr' : 'candidate'}`;
}
export async function hiringRequest<T>(token: string, path: string, body?: unknown, method?: string): Promise<T> {
  const multipart = body instanceof FormData;
  let response: Response;
  try {
    response = await fetch(base + path, {
      method: method || (body === undefined ? 'GET' : 'POST'),
      headers: { Authorization: `Bearer ${token}`, ...(body === undefined ? {} : { 'Idempotency-Key': crypto.randomUUID() }),
        ...(!multipart && body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
      ...(body === undefined ? {} : { body: multipart ? body : JSON.stringify(body) }),
    });
  } catch { throw new Error('Сервис оформления недоступен. Проверьте подключение и повторите запрос.'); }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (data?.error?.code === 'STALE_REVISION') throw new Error('Запись изменена в другой вкладке. Обновите данные и повторите действие.');
    throw new Error(data?.error?.message || `Ошибка сервиса (${response.status}).`);
  }
  if (!data) throw new Error('Сервис вернул пустой ответ.');
  return data as T;
}
export async function hiringDownload(token: string, path: string, name: string) {
  const response = await fetch(base + path, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) throw new Error(`Документ недоступен (${response.status}).`);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function uploadBody(file: File, kind: string) {
  const body = new FormData(); body.append('file', file); body.append('kind', kind); return body;
}
