import { useEffect, useState } from "react";
import {
  api,
  request,
  recruitmentContour,
  type Vacancy,
  type Handoff,
} from "./recruitment";
export interface Funnel {
  as_of: string;
  period_from: string | null;
  period_to: string | null;
  total_applications: number;
  closures_without_reason: number;
  stages: {
    code: string;
    title: string;
    is_final: boolean;
    current_count: number;
    reached_count: number;
  }[];
  closures: {
    stage_code: string;
    stage_title: string;
    reason_code: string | null;
    reason_title: string;
    count: number;
  }[];
  open_waits: {
    total: number;
    unique_applications: number;
    due_soon_total: number;
    overdue_total: number;
    median_wait_hours: number | null;
    by_department: {
      department: string;
      total: number;
      unique_applications: number;
      due_soon_total: number;
      overdue_total: number;
      median_wait_hours: number;
    }[];
  };
}
export const dateValue = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export function rangeFor(period: string) {
  const end = new Date(),
    start = new Date(end);
  if (period === "Неделя") start.setDate(start.getDate() - 6);
  else if (period === "Квартал")
    start.setMonth(Math.floor(start.getMonth() / 3) * 3, 1);
  else if (period === "Год") start.setMonth(0, 1);
  else start.setDate(1);
  return { from: dateValue(start), to: dateValue(end) };
}
export function funnelRequest(
  from: string,
  to: string,
  vacancy: string,
  signal?: AbortSignal,
) {
  const q = new URLSearchParams({
    contour: recruitmentContour,
    period_from: from,
    period_to: to,
  });
  if (vacancy) q.set("vacancy_id", vacancy);
  return request<Funnel>("/analytics/funnel?" + q, "hr", undefined, signal);
}
export function useAnalytics(
  from: string,
  to: string,
  vacancy = "",
  refresh = 0,
) {
  const [data, setData] = useState<{
    funnel: Funnel;
    vacancies: Vacancy[];
    handoffs: Handoff[];
  } | null>(null);
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setData(null);
    if (!from || !to || from > to) {
      setError("Укажите корректные даты: начало не позже конца.");
      setLoading(false);
      return;
    }
    Promise.all([
      funnelRequest(from, to, vacancy, controller.signal),
      api.vacancies(controller.signal),
      api.handoffs(),
    ])
      .then(([funnel, vacancies, handoffs]) => {
        if (!controller.signal.aborted)
          setData({
            funnel,
            vacancies: vacancies.items,
            handoffs: handoffs.items,
          });
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(
            e instanceof Error ? e.message : "Ошибка загрузки аналитики",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [from, to, vacancy, refresh]);
  return { data, error, loading };
}
export function downloadFunnel(data: Funnel) {
  const rows: (string | number)[][] = [
    ["Срез", data.as_of],
    [
      "Решения с",
      data.period_from || "Все даты",
      "по",
      data.period_to || "Все даты",
    ],
    ["Этап", "Сейчас", "Когда-либо достигли"],
    ...data.stages.map((s) => [s.title, s.current_count, s.reached_count]),
    [],
    ["Решение", "Причина", "Количество"],
    ...data.closures.map((c) => [c.stage_title, c.reason_title, c.count]),
  ];
  const safeCell = (value: string | number) => {
    const s = String(value);
    return '"' + (/^\s*[=+@-]/.test(s) ? "'" + s : s).replace(/"/g, '""') + '"';
  };
  const url = URL.createObjectURL(
    new Blob(
      ["\ufeff" + rows.map((row) => row.map(safeCell).join(";")).join("\r\n")],
      { type: "text/csv;charset=utf-8" },
    ),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "recruitment-summary.csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
