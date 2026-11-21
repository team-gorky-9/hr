export type SupportRole = 'employee' | 'coordinator' | 'specialist' | 'secretary' | 'executor';
export const supportRoles: { id: SupportRole; label: string }[] = [
  { id: 'employee', label: 'Сотрудник' }, { id: 'coordinator', label: 'Координатор' },
  { id: 'specialist', label: 'Проверяющий' }, { id: 'secretary', label: 'Секретарь' },
  { id: 'executor', label: 'Исполнитель' },
];
// Public synthetic identities from services/social-support/fixtures/actors.json.
export const supportFixtureActors = {
  specialist: '50000000-0000-0000-0000-000000000003',
  secretary: '50000000-0000-0000-0000-000000000004',
  executor: '50000000-0000-0000-0000-000000000007',
};
export interface SupportRule {
  id: string; title: string; source_reference: string; is_synthetic: boolean;
  required_items: { key: string; title: string }[];
}
export interface SupportDocument {
  id: string; item_key: string; original_name: string; size_bytes: number;
  visibility: string; created_at: string;
}
export interface SupportExtract {
  id: string; version: number; outcome: string; public_explanation: string; decided_on: string;
}
export interface SupportCase {
  id: string; revision: number; number: string | null; status: string;
  rule_version_id?: string; statement?: string; created_at?: string; submitted_at: string | null;
  documents?: SupportDocument[]; submissions?: { document_ids: string[]; submission_revision: number }[];
  public_message?: string | null; staff_status?: string;
  assigned_specialist_id?: string; assigned_secretary_id?: string;
  execution?: { status: string; occurred_on: string | null };
  extract?: SupportExtract;
}
export interface SupportEvent { id: string; action: string; recorded_at: string; public: { message?: string } }
const env = (import.meta as ImportMeta & { env: Record<string, string> }).env;
const base = env.VITE_SUPPORT_API_BASE || '/support-api';

export async function supportRequest<T>(role: SupportRole, path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(base + path, {
      ...init,
      headers: {
        ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        Authorization: 'Bearer fixture:' + role,
        ...init.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new Error('Сервис помощи недоступен. Повторите запрос.');
  }
  const result = await response.json().catch(() => null);
  if (!response.ok) throw new Error(result?.error?.message || `Ошибка сервера ${response.status}`);
  return result as T;
}
export async function downloadSupportDocument(role: SupportRole, item: SupportCase, doc: SupportDocument) {
  const response = await fetch(`${base}/cases/${item.id}/documents/${doc.id}/content`, {
    headers: { Authorization: 'Bearer fixture:' + role },
  });
  if (!response.ok) throw new Error('Документ недоступен.');
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url; link.download = doc.original_name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
