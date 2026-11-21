const env = (import.meta as ImportMeta & { env: Record<string, string> }).env;
const base = (env.VITE_HIRING_API_BASE || '/hiring-api').replace(/\/$/, '');

export interface PublicVacancy {
  id: string;
  title: string;
  description: string;
  position_code: string;
  revision: number;
  published_at: string;
  system: 'requirements' | 'legacy';
  is_synthetic: boolean;
  employer?: string;
}

interface Publication extends Omit<PublicVacancy, 'system' | 'id' | 'revision' | 'description' | 'published_at'> {
  ref: Pick<PublicVacancy, 'id' | 'system' | 'revision'>;
  description?: string;
  published_at?: string;
}

function toVacancy({ ref, description = '', published_at = '', ...row }: Publication): PublicVacancy {
  return { ...row, ...ref, description, published_at };
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(base + '/candidate-portal/public-vacancies' + path, { signal });
  if (response.status === 404 && path) throw new Error('Вакансия больше не опубликована.');
  if (!response.ok || !response.headers.get('Content-Type')?.includes('application/json')) {
    throw new Error('Каталог вакансий недоступен. Повторите запрос.');
  }
  return response.json() as Promise<T>;
}

export async function listPublicVacancies(signal?: AbortSignal): Promise<PublicVacancy[]> {
  const { items } = await request<{ items: Publication[] }>('', signal);
  if (!Array.isArray(items)) throw new Error('Не удалось прочитать каталог вакансий.');
  return items.map(toVacancy);
}

export async function getPublicVacancy(id: string, signal?: AbortSignal): Promise<PublicVacancy> {
  return toVacancy(await request<Publication>('/' + encodeURIComponent(id), signal));
}
