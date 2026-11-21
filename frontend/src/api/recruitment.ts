export const environment = (import.meta as ImportMeta & { env: Record<string, string> }).env;
export const recruitmentContour = environment.VITE_RECRUITMENT_CONTOUR === 'working' ? 'working' : 'training';
const base = environment.VITE_RECRUITMENT_API_BASE || '/legacy-api/api/v1';
// Default: fixed id of the stand account dept_demo (app/db/seed.py demo_user_id); override per deployment.
export const recipientId = environment.VITE_RECRUITMENT_RECIPIENT_ID || '91fb005a-a5e2-5d38-b6ee-a5e968e182a9';
export type Role = 'hr' | 'dept';
export interface Stage { code: string; title: string; is_final: boolean }
export interface Vacancy { vacancy_id: string; title: string; employer: string; channel: string; applications_count: number; approved_profile_version: number | null }
export interface ApplicationRow { application_id: string; candidate_code: string; headline: string | null; applied_at: string | null; current_stage_title: string; formal_result: string | null; rank_group: string; assessment_status: string; rank_reason: string }
export interface Evidence { candidate_text_id: string; quote: string; utf16_start: number; utf16_end: number }
export interface Check { requirement_id: string; description: string; result: string; basis: string; is_preliminary: boolean; explanation: string | null; evidence: Evidence[] }
export interface ApplicationDetail { application_id: string; stage: Stage; vacancy: { title: string } | null; posting_title: string | null; assessment_status: string; candidate: { candidate_id: string; code: string; headline: string | null; current_text_id: string | null; is_training: boolean; card: Record<string, unknown> | null }; assessment: { assessment_id: string; version: number; is_stale: boolean; formal_result: string; summary: string | null; formal_checks: Check[]; competency_scores: { name: string; explanation: string | null; evidence: Evidence[] }[] } | null }
export interface History { last_seq: number | null; source: string; items: { seq: number; to_stage: Stage; comment: string | null; created_at: string; actor: { login: string } | null; rejection_reason: { title: string } | null }[] }
export interface Feedback { feedback_id: string; outcome: string; comment: string | null; rejection_reason: { title: string } | null; interview_status: string; received_at: string }
export interface Handoff { attempt_id: string; application_id: string; candidate_code: string; vacancy_title: string | null; recipient_name: string; recipient_department: string; due_date: string; handed_off_at: string; deadline_status: string; business_days_left: number | null; status: string; latest_feedback: Feedback | null; extensions_count: number; markdown?: string; feedback_history?: Feedback[]; deadline_extensions?: { reason_title: string; comment: string | null; previous_due_date: string; new_due_date: string }[] }
export interface Guide { interview_id: string; guide_version: number; is_stale: boolean; core: Question[]; clarifications: Question[]; document_requests: { requirement_id: string; title: string; reason: string | null }[] }
export interface Question { question_id: string; question: string; gap: string | null; criterion: { good_answer: string | null; insufficient_answer: string | null } | null; answer: { text: string; revision: number } | null }
export interface Interview { id: string; revision: number; result: string; summary: string | null; held_at: string | null; attempt_at: string | null }
export interface Reason { code: string; title: string; side: string }
export class ApiError extends Error { constructor(message: string, public status: number, public code: string) { super(message); } }
export async function request<T>(path: string, role: Role = 'hr', body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try { response = await fetch(base + path, { method: body === undefined ? 'GET' : 'POST', signal, headers: { 'Content-Type': 'application/json', 'X-User-Login': role === 'dept' ? (environment.VITE_RECRUITMENT_DEPT_LOGIN || 'dept_demo') : (environment.VITE_RECRUITMENT_HR_LOGIN || 'hr_demo') }, body: body === undefined ? undefined : JSON.stringify(body) }); }
  catch (e) { if (e instanceof DOMException && e.name === 'AbortError') throw e; throw new Error('Не удалось связаться с сервером подбора. Повторите запрос.'); }
  const json = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(json?.error?.message || `Ошибка сервера ${response.status}`, response.status, json?.error?.code || '');
  return json as T;
}
export const api = {
  vacancies: (signal?: AbortSignal) => request<{ items: Vacancy[] }>(`/vacancies?contour=${recruitmentContour}`, 'hr', undefined, signal),
  applications: (id: string, signal?: AbortSignal) => request<{ items: ApplicationRow[] }>(`/vacancies/${id}/applications?contour=${recruitmentContour}`, 'hr', undefined, signal),
  application: (id: string) => request<ApplicationDetail>(`/applications/${id}`),
  history: (id: string) => request<History>(`/applications/${id}/history`),
  source: (id: string) => request<{ text: string; version: number; is_current: boolean }>(`/candidate-texts/${id}`),
  handoffs: (role: Role = 'hr') => request<{ items: Handoff[] }>(`/handoffs?contour=${recruitmentContour}`, role),
  applicationHandoffs: (id: string) => request<{ items: Handoff[] }>(`/applications/${id}/handoffs`),
  handoff: (id: string, role: Role) => request<Handoff>(`/handoffs/${id}`, role),
  summary: (id: string) => request<{ summary_revision: string; markdown: string }>(`/applications/${id}/handoff-summary`),
  stages: () => request<{ items: Stage[] }>('/references/stages'),
  reasons: () => request<{ items: Reason[] }>('/references/rejection-reasons'),
  guide: (id: string) => request<Guide>(`/applications/${id}/interview-guide`),
  interviews: (id: string) => request<{ items: Interview[] }>(`/applications/${id}/interviews`),
};
export const resultLabel = (value: string | null) => ({ met: 'Выполнено', not_met: 'Не выполнено', unknown: 'Нужно уточнить' }[value || ''] || 'Не оценено');
export const assessmentLabel = (value: string) => ({ ready: 'Оценка актуальна', stale: 'Оценка устарела', no_approved_profile: 'Нет утверждённого профиля', mapping_required: 'Требуется сопоставить публикацию', not_applicable: 'Профиль неприменим', pending: 'Оценка не готова', no_assessment: 'Оценки нет' }[value] || value);
export const feedbackLabel = (value: string) => ({ fit: 'Подошёл', not_fit: 'Не подошёл', pending: 'Рассмотрение продолжается' }[value] || value);
export const deadlineLabel = (value: string) => ({ on_track: 'Ожидаем ответ', due_soon: 'Срок скоро', overdue: 'Просрочено', responded: 'Ответ получен', closed_without_response: 'Закрыто без ответа' }[value] || value);
export const errorMessage = (e: unknown) => e instanceof Error ? e.message : 'Не удалось выполнить действие';

// The server stores check explanations as "[basis] {json}" (app/assessment/service.py _explanation).
// HR must see a sentence, not the machine record.
const basisLabel: Record<string, string> = { resume: 'резюме', interview: 'интервью', document: 'документам' };
const needsLabel: Record<string, string> = { interview: 'на собеседовании', document: 'документом', resume: 'по резюме' };
type Counts = { confirmed?: number; contradicted?: number; no_info?: number; total?: number };
const counted = (title: string, c?: Counts) => !c?.total ? '' :
  `${title}: подтверждено ${c.confirmed || 0} из ${c.total}` + (c.contradicted ? `, противоречит ${c.contradicted}` : '') + (c.no_info ? `, нет сведений ${c.no_info}` : '');
export function readableExplanation(text: string | null | undefined): string {
  if (!text) return '';
  const match = text.match(/^\[(\w+)\]\s*(\{[\s\S]*\})\s*$/);
  if (!match) return text;
  let d: Record<string, any>;
  try { d = JSON.parse(match[2]); } catch { return ''; }
  const source = basisLabel[match[1]] || match[1];
  const parts: string[] = [];
  if ('mandatory' in d || 'desired' in d || 'on_interview' in d) {
    const mandatory = counted(`Обязательные индикаторы по ${source}`, d.mandatory);
    const desired = counted('желательные', d.desired);
    if (mandatory) parts.push(mandatory);
    if (desired) parts.push(desired);
    if (!mandatory && !desired) parts.push(`В ${source === 'резюме' ? 'резюме' : 'источнике'} нет сведений по индикаторам этой компетенции`);
    if (d.on_interview) parts.push(`проверить на собеседовании: ${d.on_interview}`);
  } else {
    if (d.gap) parts.push(`Нужно уточнить: ${d.gap}`);
    if (d.months_low != null || d.months_high != null) {
      const low = d.months_low ?? d.months_high, high = d.months_high ?? d.months_low;
      parts.push(`опыт по резюме: ${low === high ? low : `${low}–${high}`} мес.`);
    }
    if (typeof d.notes === 'string' && d.notes) parts.push(d.notes);
    if (Array.isArray(d.notes)) parts.push(...d.notes.filter((n: unknown) => typeof n === 'string'));
    if (d.needs) parts.push(`подтвердить ${needsLabel[d.needs] || d.needs}`);
    if (d.downgraded) parts.push('вывод модели без подтверждающей цитаты — проверьте сами');
  }
  if (!parts.length) return '';
  const sentence = parts.join('; ');
  return sentence.charAt(0).toUpperCase() + sentence.slice(1) + (sentence.endsWith('.') ? '' : '.');
}
