export type ServiceName = "recognition" | "feedback" | "mobility";
const env = (import.meta as ImportMeta & { env: Record<string, string> }).env;
const bases: Record<ServiceName, string> = {
  recognition:
    env.VITE_RECOGNITION_API_BASE || "/recognition/api/v1/recognition",
  feedback: env.VITE_FEEDBACK_API_BASE || "/feedback/api/v1/feedback",
  mobility: env.VITE_MOBILITY_API_BASE || "/mobility/api/v1/mobility",
};
const messages: Record<string, string> = {
  UNAUTHENTICATED: "Неверная учётная запись.",
  AUTH_REQUIRED: "Войдите в раздел.",
  STALE_REVISION: "Запись изменилась. Обновите данные и повторите действие.",
  INVALID_STATE: "Состояние записи изменилось. Обновите данные.",
  INVALID_CODE: "Код приглашения не найден.",
  CODE_ALREADY_USED: "По этому коду ответ уже принят.",
  NOT_FOUND: "Запись не найдена или недоступна вам.",
  ACTIVE_REGISTRATION_EXISTS: "У вас уже есть действующая запись.",
  INVALID_INPUT: "Проверьте заполненные поля.",
  OUT_OF_RANGE: "Ответ выходит за допустимую шкалу.",
  CONFLICT_OF_INTEREST:
    "Участник не может принять решение по собственной заявке.",
};
export async function serviceRequest<T>(
  service: ServiceName,
  token: string | null,
  path: string,
  body?: unknown,
  method?: string,
): Promise<T> {
  const response = await fetch(bases[service] + path, {
    method: method || (body === undefined ? "GET" : "POST"),
    credentials: token ? "same-origin" : "omit",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const code = data?.error?.code || data?.detail?.code;
    throw new Error(
      messages[code] ||
        data?.error?.message ||
        `Не удалось выполнить действие (${response.status}${code ? ": " + code : ""}).`,
    );
  }
  if (!data) throw new Error("Сервис вернул пустой ответ.");
  return data;
}
export interface Actor {
  id?: string;
  actor_id?: string;
  name?: string;
  login?: string;
  roles: string[];
  assignments?: string[];
  organization_id?: string;
}
export interface Page<T> {
  items: T[];
  next_cursor?: string | null;
}
export async function allPages<T>(
  service: ServiceName,
  token: string,
  path: string,
): Promise<T[]> {
  const result: T[] = [];
  let cursor: string | null | undefined;
  do {
    const page = await serviceRequest<Page<T>>(
      service,
      token,
      path +
        (path.includes("?") ? "&" : "?") +
        "limit=100" +
        (cursor ? "&cursor=" + encodeURIComponent(cursor) : ""),
    );
    result.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);
  return result;
}
