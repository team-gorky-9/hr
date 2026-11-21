const env = (import.meta as ImportMeta & { env: Record<string, string> }).env;
const base = (env.VITE_REQUIREMENTS_API_BASE || "/requirements-api").replace(
  /\/$/,
  "",
);
export interface PublicVacancy {
  department_name?: string | null;
  id: string;
  organization_id: string;
  department_id: string;
  revision: number;
  title: string;
  description: string;
  position_code: string;
  published_at: string;
  status: "published" | "closed";
}
export async function publicVacancies(
  signal?: AbortSignal,
): Promise<PublicVacancy[]> {
  const response = await fetch(base + "/public/vacancies", { signal });
  if (!response.ok)
    throw new Error("Не удалось загрузить вакансии. Повторите запрос.");
  return (await response.json()).items;
}
export async function publicVacancy(
  id: string,
  signal?: AbortSignal,
): Promise<PublicVacancy> {
  const response = await fetch(
    base + "/public/vacancies/" + encodeURIComponent(id),
    { signal },
  );
  if (!response.ok)
    throw new Error(
      response.status === 404
        ? "Вакансия не найдена или ещё не опубликована."
        : "Не удалось загрузить вакансию. Повторите запрос.",
    );
  return response.json();
}
