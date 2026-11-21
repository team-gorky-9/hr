import { forgetSession, requireSessionToken } from "./session";
const env = (import.meta as ImportMeta & { env: Record<string, string> }).env;
const base = env.VITE_REQUIREMENTS_API_BASE || "/requirements-api";
export type RequirementsRole = "hr" | "department";
export type Verification = "resume" | "documents" | "interview" | "test";
export interface Position {
  id: string;
  code: string;
  title: string;
}
export interface Source {
  id: string;
  original_name: string;
  revision: number;
  position_code: string;
  extraction_status: string;
  extracted_text: string | null;
  reason: string | null;
}
export interface SourceRef {
  source_document_id: string;
  address: string;
  quote: string;
}
export interface RowSource {
  key: string;
  origin: "source" | "team";
  note?: string | null;
  source_refs: SourceRef[];
}
export interface Alternative {
  key: string;
  level?: string | null;
  enrollment_status?: string | null;
  field_group?: string | null;
  field_examples?: string[];
  field_exclusions?: string[];
  degree_fields?: string[] | null;
  retraining_fields?: string[] | null;
}
export interface RuleParams {
  schema_version?: string;
  scope?: "total_commercial" | "relevant_role";
  minimum_defined?: boolean;
  min_months?: number | null;
  relevance_hint?: string | null;
  alternatives?: Alternative[];
  requires_requirement?: string | null;
}
export interface StagedRow extends RowSource {
  is_mandatory: boolean;
  verification: Verification;
  check_stage?: string | null;
  acceptance?: {
    met?: string | null;
    not_met?: string | null;
    unknown?: string | null;
    limit?: string | null;
  };
}
export interface Requirement extends StagedRow {
  kind:
    | "education_level"
    | "education_field"
    | "experience"
    | "knowledge"
    | "other";
  description: string;
  params: RuleParams;
}
export interface Indicator extends StagedRow {
  text: string;
  excluded_from_scoring?: boolean;
  same_as?: string | null;
}
export interface Competency extends RowSource {
  code: string;
  name: string;
  rank?: string | null;
  target_level_min?: number | null;
  target_level_max?: number | null;
  indicators: Indicator[];
}
export interface Content {
  schema_version: "requirement-draft/1.0";
  position_code: string;
  is_synthetic: boolean;
  note?: string | null;
  sources: {
    source_document_id: string;
    role: string;
    observed_revision?: string | null;
    is_primary: boolean;
  }[];
  formal_requirements: Requirement[];
  competencies: Competency[];
}
export interface Draft {
  id: string;
  position_code: string;
  status: "editing" | "in_review" | "returned" | "approved";
  contour: string;
  revision: number;
  content_revision: number;
  content: Content;
  review_note: string | null;
  accepted_content_revision: number | null;
  assigned_reviewer_actor_id: string | null;
}
export interface Profile {
  id: string;
  draft_id: string;
  position_code: string;
  version: number;
  contour: string;
  content: Content;
  approval_basis: string;
  approved_at: string;
  is_current: boolean;
  sources_snapshot: {
    source_document_id: string;
    original_name: string;
    extracted_text: string | null;
    source_revision: number;
  }[];
}
export interface History {
  id: string;
  action: string;
  reason: string | null;
  created_at: string;
  actor_id: string;
  content_revision: number;
}
export interface Vacancy {
  id: string;
  title: string;
  description: string;
  position_code: string;
  department_id: string;
  profile_id: string;
  profile_version: number;
  revision: number;
  status: "draft" | "published" | "closed";
  close_reason: string | null;
  history?: {
    revision: number;
    action: string;
    actor_id: string;
    recorded_at: string;
  }[];
}
export interface Page<T> {
  items: T[];
  next_cursor?: string | null;
}
export class RequirementsError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
  }
}
export async function requirementsRequest<T>(
  _role: RequirementsRole,
  path: string,
  body?: unknown,
  method?: string,
): Promise<T> {
  const token = requireSessionToken();
  const multipart = body instanceof FormData;
  let response: Response;
  try {
    response = await fetch(base + path, {
      method: method || (body === undefined ? "GET" : "POST"),
      headers: {
        Authorization: "Bearer " + token,
        ...(multipart ? {} : { "Content-Type": "application/json" }),
        ...(body === undefined
          ? {}
          : { "Idempotency-Key": crypto.randomUUID() }),
      },
      body:
        body === undefined
          ? undefined
          : multipart
            ? body
            : JSON.stringify(body),
    });
  } catch {
    throw new Error(
      "Не удалось связаться с сервисом требований. Обновите данные или повторите действие.",
    );
  }
  const data = await response.json().catch(() => null);
  if (response.status === 401) forgetSession(token);
  if (!response.ok) {
    const detail = data?.error;
    throw new RequirementsError(
      (detail?.message || `Ошибка сервера ${response.status}`) +
        (detail?.field ? ` Поле: ${detail.field}.` : "") +
        (response.status === 409
          ? " Обновите карточку и повторите действие с актуальной редакцией."
          : ""),
      response.status,
      detail?.code,
    );
  }
  if (!data) throw new Error("Сервис вернул некорректный ответ.");
  return data as T;
}
export async function requirementsList<T>(
  role: RequirementsRole,
  path: string,
): Promise<T[]> {
  const items: T[] = [];
  let cursor: string | null | undefined;
  do {
    const page: Page<T> = await requirementsRequest(
      role,
      path +
        (cursor
          ? `${path.includes("?") ? "&" : "?"}cursor=${encodeURIComponent(cursor)}`
          : ""),
    );
    items.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);
  return items;
}
export async function downloadSource(
  _role: RequirementsRole,
  source: { id: string; original_name: string },
) {
  const token = requireSessionToken();
  const response = await fetch(base + "/documents/" + source.id + "/content", {
    headers: { Authorization: "Bearer " + token },
  });
  if (response.status === 401) forgetSession(token);
  if (!response.ok) throw new Error("Не удалось получить исходный файл.");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = source.original_name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
