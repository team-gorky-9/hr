export type StudentRole = 'candidate' | 'hr' | 'department';
const env = (import.meta as ImportMeta & { env: Record<string, string> }).env;
const base = env.VITE_STUDENTS_API_BASE || '/api/v1/students';
export const fixtureMentorId = '00000000-0000-4000-8000-000000000103';

export interface Opportunity {
  id: string; revision: number; title: string; description: string;
  starts_on: string; ends_on: string; capacity: number; available_places?: number;
  mentor_actor_id: string; status: string;
}
export interface StudentApplication {
  id: string; revision: number; opportunity_id: string; status: string;
  university_label: string; programme_label: string; comment: string; reason: string | null;
}
export interface Criterion { key: string; text: string; required: boolean }
export interface Task {
  id: string; version: number; title: string; description: string; criteria: Criterion[];
}
export interface ReviewResult {
  criterion_key: string; result: 'confirmed' | 'needs_revision' | 'not_verified'; reason: string;
}
export interface Submission {
  id: string; attempt_no: number; task_version_id: string; text: string;
  artifact_url: string | null; submitted_at: string;
  review: { results: ReviewResult[]; reviewed_at: string } | null;
}
export interface Placement {
  id: string; revision: number; opportunity_id: string; application_id: string;
  starts_on: string; ends_on: string; status: string; work_state?: string;
  completion?: { outcome: string; reason: string };
  university_result?: { result: string; source_reference?: string; source_author?: string; occurred_on?: string };
  career_interest?: { interested: boolean; note?: string };
}
export interface CareerPackage {
  package_id: string; transfer_status: string; education_status: string;
  purpose: string; contact_basis: string; interest_withdrawn: boolean;
}

export async function studentsRequest<T>(token: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(base + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
      credentials: 'same-origin', signal,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new Error('Сервис практики недоступен. Повторите запрос.');
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error?.message || 'Ошибка сервиса практики (' + response.status + ').');
  if (!data) throw new Error('Не удалось прочитать данные практики. Повторите запрос.');
  return data as T;
}
