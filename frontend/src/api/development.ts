const env = (import.meta as ImportMeta & { env: Record<string, string> }).env;
const base = env.VITE_DEVELOPMENT_API_BASE || '/workforce-api';

export interface Actor { actor_id: string; login: string; grants: { role: string }[] }
export interface Session { access_token: string; actor: Actor }
export interface Goal {
  id: string; owner_actor_id: string; title: string; description: string; revision: number;
  status: 'private' | 'shared'; shared_with_actor_id: string | null;
}
export interface Criterion { key: string; text: string; required: boolean }
export interface Activity { key: string; title: string; criterion_keys: string[]; resource_note: string }
export interface Plan {
  id: string; goal_id: string; title: string; revision: number; owner_actor_id: string;
  manager_actor_id: string; reviewer_actor_id: string; status: 'proposed' | 'returned' | 'active' | 'closed';
  criteria: Criterion[]; activities: Activity[]; goal_snapshot: Goal; decision_note: string | null;
  closure: null | { outcome: string; reason: string; closed_at: string };
}
export interface ReviewResult { criterion_key: string; result: 'confirmed' | 'needs_revision' | 'not_verified'; reason: string }
export interface Submission {
  id: string; activity_key: string; attempt_no: number; statement: string;
  criterion_keys: string[]; artifact: { kind: string; value: string; mutable_source: boolean };
  created_at: string; review: null | { id: string; results: ReviewResult[] };
}
export interface Progress { completed_count: number; total_count: number; criteria: { key: string; state: string }[] }
export interface ResultPackage {
  package_id: string; purpose: string;
  items: { criterion_text: string; reviewed_at: string; source_submission_id: string }[];
  limitations: { delivery_status: string; note: string };
}

export async function developmentRequest<T>(token: string | null, path: string, body?: unknown, method?: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(base + path, {
      method: method || (body === undefined ? 'GET' : 'POST'),
      credentials: 'same-origin', signal,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: 'Bearer ' + token } : {}),
        ...(path === '/sessions' ? { 'Idempotency-Key': crypto.randomUUID() } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new Error('Нет связи с Workforce. Повторите запрос.');
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error?.message || `Ошибка сервера ${response.status}`);
  if (!data) throw new Error('Сервер вернул пустой ответ.');
  return data as T;
}
