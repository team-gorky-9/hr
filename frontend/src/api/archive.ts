export type Contour = 'training' | 'working';
const environment = (import.meta as ImportMeta & { env: Record<string, string> }).env;
export const contour: Contour = environment.VITE_ARCHIVE_CONTOUR === 'working' ? 'working' : 'training';
const base = environment.VITE_ARCHIVE_API_BASE || '/api/v1';

export interface Vacancy {
  vacancy_id: string; position_id: string; title: string; status: string;
}
export interface Application {
  application_id: string; source: string; posting_title: string | null;
  position_title: string | null; external_position_title: string | null;
  applied_at: string | null; stage_code: string; is_active: boolean;
}
export interface Evidence {
  candidate_text_id: string; fragment: string; utf16_start: number; utf16_end: number;
}
export interface Hit {
  candidate_id: string; candidate_code: string; evidence: Evidence | null;
  in_reserve: boolean; applications: Application[];
  filter_matches: { kind: string; values: (string | boolean)[] }[];
}
export interface SearchResult { items: Hit[]; mode: string; semantic_status: string }
export interface Reserve {
  reserve_id: string; candidate_id: string; reason: string | null; contact_basis: string | null;
  added_at: string; valid_until: string | null; status: string; added_by: { login: string } | null;
}
export interface TextSource { text: string; version: number; is_current: boolean }
export interface History {
  stage: { title: string };
  items: { seq: number; to_stage: { title: string }; created_at: string; comment: string | null; rejection_reason: { title: string } | null }[];
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(base + path, {
      ...options, credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', ...options.headers },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new Error('Не удалось связаться с сервером. Повторите запрос.');
  }
  const json = await response.json().catch(() => null);
  if (!response.ok) throw new Error(json?.error?.message || `Сервер вернул ошибку ${response.status}.`);
  if (!json) throw new Error('Сервер вернул пустой ответ.');
  return json as T;
}
export const archiveApi = {
  vacancies: (signal: AbortSignal) => request<{ items: Vacancy[] }>(`/vacancies?contour=${contour}`, { signal }),
  search: (query: string, onlyReserve: boolean, signal: AbortSignal) =>
    request<SearchResult>('/search/candidates', {
      method: 'POST', signal,
      body: JSON.stringify({ contour, query, limit: 50, filters: { in_reserve: onlyReserve ? true : null } }),
    }),
  reserve: (positionId: string, signal?: AbortSignal) =>
    request<{ items: Reserve[] }>(`/positions/${positionId}/reserve?contour=${contour}`, { signal }),
  source: (id: string, signal: AbortSignal) => request<TextSource>(`/candidate-texts/${id}`, { signal }),
  history: (id: string, signal: AbortSignal) => request<History>(`/applications/${id}/history`, { signal }),
  save: (candidateId: string, positionId: string, reason: string, contactBasis: string) =>
    request<{ entry: Reserve; created: boolean }>('/reserve', {
      method: 'POST', body: JSON.stringify({ candidate_id: candidateId, position_id: positionId, reason, contact_basis: contactBasis }),
    }),
};
