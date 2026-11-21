const env = (import.meta as ImportMeta & { env: Record<string, string> }).env;
const base = (env.VITE_FEEDBACK_API_BASE || '/feedback/api/v1/feedback').replace(/\/$/, '');

type Question = { key: string; text: string; min: number; max: number };
type Topic = { key: string; label: string };

export type DemoCycle = {
  id: string;
  title: string;
  status: 'open' | 'closed';
  has_results: boolean;
};

export type SurveyForm = {
  id: string;
  title: string;
  status: 'open' | 'closed';
  privacy_notice: string;
  questions: Question[];
  topic_options: Topic[];
};

type PublishedCount = { status: 'shown'; count: number } | { status: 'suppressed' };
type PublishedGroup = { key: string; label: string } & ({ status: 'suppressed' } | {
  status: 'shown';
  response_count: number;
  scales: { question_key: string; categories: ({ value: number } & PublishedCount)[] }[];
  topics: ({ key: string } & PublishedCount)[];
});

export type SurveyResults = Pick<SurveyForm, 'questions' | 'topic_options'> & {
  cycle_id: string;
  groups: PublishedGroup[];
  notice: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(base + path, {
    ...init, credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer',
  });
  const result = await response.json().catch(() => null);
  if (!response.ok) {
    const code = result?.detail?.code;
    if (code === 'CODE_ALREADY_USED') throw new Error('Этот код уже использован.');
    if (code === 'INVALID_CODE') throw new Error('Проверьте код для этого опроса.');
    if (response.status === 409) throw new Error('Ответы на этот опрос больше не принимаются.');
    if (response.status === 404) throw new Error('Опрос или его итоги недоступны.');
    throw new Error('Не удалось выполнить запрос. Проверьте поля или повторите позже.');
  }
  if (!result) throw new Error('Сервис опросов недоступен.');
  return result as T;
}

export const feedbackApi = {
  catalog: (signal: AbortSignal) => request<{ items: DemoCycle[] }>('/demo/cycles', { signal }),
  form: (id: string, signal: AbortSignal) => request<SurveyForm>(`/cycles/${encodeURIComponent(id)}/form`, { signal }),
  results: (id: string, signal: AbortSignal) => request<SurveyResults>(`/demo/cycles/${encodeURIComponent(id)}/results`, { signal }),
  submit: (id: string, body: { access_code: string; answers: { question_key: string; value: number }[]; topic_key: string }) =>
    request<{ accepted: boolean }>(`/cycles/${encodeURIComponent(id)}/responses`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }),
};
