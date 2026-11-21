import { useEffect, useState } from "react";
import { Card, Kpi, Badge, Bar, Btn, PageTitle } from "../shared/ui";
import {
  dateValue,
  downloadFunnel,
  funnelRequest,
  rangeFor,
  useAnalytics,
} from "../../api/analytics";
import { recruitmentContour } from "../../api/recruitment";
import ReportPage from "../report/ReportPage";

export type AnalyticsView = "dashboard" | "config" | "ready";
export const AnalyticsDashboard = ({
  onExportReport,
}: {
  onExportReport?: () => void;
}) => {
  const [view, setView] = useState<AnalyticsView>("dashboard");
  const [period, setPeriod] = useState("Месяц"),
    [range, setRange] = useState(() => rangeFor("Месяц"));
  const [vacancy, setVacancy] = useState(""),
    [refresh, setRefresh] = useState(0);
  const { data, error, loading } = useAnalytics(
    range.from,
    range.to,
    vacancy,
    refresh,
  );
  const [months, setMonths] = useState<
    { label: string; hired: number; rejected: number }[]
  >([]);
  const [trendError, setTrendError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setMonths([]);
    setTrendError("");
    const end = new Date(range.to + "T12:00:00");
    if (Number.isNaN(end.valueOf())) return;
    Promise.all(
      Array.from({ length: 6 }, (_, i) => {
        const start = new Date(end.getFullYear(), end.getMonth() - 5 + i, 1);
        const last = new Date(start.getFullYear(), start.getMonth() + 1, 0);
        return funnelRequest(
          dateValue(start),
          dateValue(last > end ? end : last),
          vacancy,
          controller.signal,
        ).then((f) => ({
          label: start.toLocaleDateString("ru-RU", {
            month: "short",
            year: "2-digit",
          }),
          hired: f.closures
            .filter((c) => c.stage_code === "hired")
            .reduce((n, c) => n + c.count, 0),
          rejected: f.closures
            .filter((c) => c.stage_code !== "hired")
            .reduce((n, c) => n + c.count, 0),
        }));
      }),
    )
      .then(setMonths)
      .catch((e) => {
        if (!controller.signal.aborted)
          setTrendError(e instanceof Error ? e.message : "Динамика недоступна");
      });
    return () => controller.abort();
  }, [range.to, vacancy, refresh]);
  if (view !== "dashboard")
    return (
      <>
        <div className="max-w-[1240px] mx-auto px-6 pt-6">
          <Btn onClick={() => setView("dashboard")}>← Аналитика подбора</Btn>
        </div>
        <ReportPage />
      </>
    );
  const f = data?.funnel;
  const rejects = f?.closures.filter((c) => c.stage_code !== "hired") || [];
  const hired =
    f?.closures
      .filter((c) => c.stage_code === "hired")
      .reduce((n, c) => n + c.count, 0) || 0;
  const sources = Object.entries(
    (data?.vacancies || [])
      .filter((v) => !vacancy || v.vacancy_id === vacancy)
      .reduce<Record<string, number>>((all, v) => {
        all[v.channel || "Источник не указан"] =
          (all[v.channel || "Источник не указан"] || 0) + v.applications_count;
        return all;
      }, {}),
  );
  const trendMax = Math.max(1, ...months.flatMap((m) => [m.hired, m.rejected]));
  const field =
    "border border-[#E1E5EB] rounded-lg px-3 py-2 bg-white text-[13px]";
  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-6 space-y-6">
      <Card>
        <PageTitle
          title="Аналитика и отчёты"
          subtitle={`${recruitmentContour === "training" ? "Учебный контур" : "Рабочий контур"} · ${f ? "срез " + new Date(f.as_of).toLocaleString("ru-RU") : "загрузка данных"}`}
          right={
            <div className="flex gap-3">
              <Btn
                disabled={!f || loading}
                onClick={() => f && downloadFunnel(f)}
              >
                Скачать CSV
              </Btn>
              <Btn
                variant="primary"
                onClick={() =>
                  onExportReport ? onExportReport() : setView("config")
                }
              >
                Годовой отчёт и Excel
              </Btn>
            </div>
          }
        />
        <div className="flex flex-wrap items-end gap-3 mt-5 pt-4 border-t border-[#E1E5EB]">
          <div className="inline-flex rounded-lg bg-[#F3F5F8] p-1">
            {["Неделя", "Месяц", "Квартал", "Год"].map((p) => (
              <button
                key={p}
                onClick={() => {
                  setPeriod(p);
                  setRange(rangeFor(p));
                }}
                className={`px-3 py-2 text-[13px] rounded-md ${period === p ? "bg-white shadow-sm" : "text-[#616977]"}`}
              >
                {p}
              </button>
            ))}
          </div>
          <label className="text-[12px] text-[#616977]">
            Решения с
            <input
              aria-label="Начало периода решений"
              className={"block " + field}
              type="date"
              value={range.from}
              onChange={(e) => {
                setPeriod("Свой период");
                setRange({ ...range, from: e.target.value });
              }}
            />
          </label>
          <label className="text-[12px] text-[#616977]">
            по
            <input
              aria-label="Конец периода решений"
              className={"block " + field}
              type="date"
              value={range.to}
              onChange={(e) => {
                setPeriod("Свой период");
                setRange({ ...range, to: e.target.value });
              }}
            />
          </label>
          <label className="text-[12px] text-[#616977]">
            Вакансия
            <select
              className={"block " + field}
              value={vacancy}
              onChange={(e) => setVacancy(e.target.value)}
            >
              <option value="">Все вакансии</option>
              {data?.vacancies.map((v) => (
                <option key={v.vacancy_id} value={v.vacancy_id}>
                  {v.title}
                </option>
              ))}
            </select>
          </label>
          <Btn disabled={loading} onClick={() => setRefresh((x) => x + 1)}>
            Обновить
          </Btn>
        </div>
        <p className="text-[12px] text-[#616977] mt-3">
          Период относится к решениям о завершении рассмотрения. Воронка и
          ожидания показывают текущий срез.
        </p>
      </Card>
      {error && (
        <Card>
          <p role="alert" className="text-red-700">
            {error}
          </p>
        </Card>
      )}
      {loading && <p role="status">Загружаем аналитику…</p>}
      {f && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Kpi
              label="Откликов в контуре"
              value={String(f.total_applications)}
              caption="все даты, выбранная вакансия"
            />
            <Kpi
              label="Ждут ответа департамента"
              value={String(f.open_waits.unique_applications)}
              caption={`${f.open_waits.overdue_total} просроченных передач`}
            />
            <Kpi
              label="Принято на работу"
              value={String(hired)}
              caption="решения за выбранный период"
            />
            <Kpi
              label="Завершено без найма"
              value={String(rejects.reduce((n, c) => n + c.count, 0))}
              caption={`${f.closures_without_reason} без указанной причины`}
            />
          </div>
          <Card className="!bg-[#FAF7FF] !border-[#E5DBFF]">
            <h2 className="text-[15px] font-bold mb-3">
              Главное в текущем срезе
            </h2>
            <p className="text-[13px] text-[#334155]">
              Открытых передач: {f.open_waits.total}. Срок скоро истекает у{" "}
              {f.open_waits.due_soon_total}, просрочено{" "}
              {f.open_waits.overdue_total}. Медиана текущего ожидания:{" "}
              {f.open_waits.median_wait_hours == null
                ? "нет открытых ожиданий"
                : (f.open_waits.median_wait_hours / 24).toFixed(1) +
                  " календарных дней"}
              .
            </p>
          </Card>
          <div className="grid lg:grid-cols-2 gap-6">
            <Card>
              <h2 className="text-[16px] font-bold mb-2">Воронка подбора</h2>
              <p className="text-[12px] text-[#616977] mb-5">
                Разные отклики, когда-либо достигшие этапа; справа — сейчас на
                этапе.
              </p>
              <div className="space-y-3">
                {f.stages.map((s) => (
                  <div
                    key={s.code}
                    className="flex items-center gap-3 text-[13px]"
                  >
                    <span className="w-44 shrink-0">{s.title}</span>
                    <Bar
                      pct={
                        (s.reached_count / Math.max(1, f.total_applications)) *
                        100
                      }
                    />
                    <strong>{s.reached_count}</strong>
                    <span className="text-[#616977]">({s.current_count})</span>
                  </div>
                ))}
              </div>
            </Card>
            <Card>
              <h2 className="text-[16px] font-bold mb-2">Источники откликов</h2>
              <p className="text-[12px] text-[#616977] mb-5">
                Канал вакансии, текущие отклики выбранного контура.
              </p>
              <div className="space-y-3">
                {sources.map(([name, count]) => (
                  <div
                    key={name}
                    className="flex items-center gap-3 text-[13px]"
                  >
                    <span className="w-36">{name}</span>
                    <Bar
                      pct={
                        (count / Math.max(1, ...sources.map((s) => s[1]))) * 100
                      }
                      color="#5C83F6"
                    />
                    <strong>{count}</strong>
                  </div>
                ))}
              </div>
              {!sources.length && <p>Нет откликов.</p>}
            </Card>
            <Card>
              <h2 className="text-[16px] font-bold mb-2">
                Динамика решений по месяцам
              </h2>
              <p className="text-[12px] text-[#616977] mb-4">
                Шесть месяцев до выбранной даты окончания. Синий — найм, красный
                — завершение без найма.
              </p>
              {trendError ? (
                <p role="alert">{trendError}</p>
              ) : (
                <div className="h-44 flex items-end justify-between gap-3 border-b border-[#E1E5EB]">
                  {months.map((m) => (
                    <div
                      key={m.label}
                      className="flex-1 flex flex-col items-center gap-2"
                    >
                      <div className="flex items-end gap-1 h-32">
                        <div
                          title={`Принято: ${m.hired}`}
                          className="w-5 bg-[#1F4FD1] rounded-t"
                          style={{ height: `${(m.hired / trendMax) * 120}px` }}
                        />
                        <div
                          title={`Без найма: ${m.rejected}`}
                          className="w-5 bg-[#C84A2A] rounded-t"
                          style={{
                            height: `${(m.rejected / trendMax) * 120}px`,
                          }}
                        />
                      </div>
                      <span className="text-[11px] text-[#616977]">
                        {m.label}
                      </span>
                      <span className="text-[11px]">
                        {m.hired} / {m.rejected}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
            <Card>
              <h2 className="text-[16px] font-bold mb-2">
                Причины завершения без найма
              </h2>
              <p className="text-[12px] text-[#616977] mb-5">
                Решения за выбранный период.
              </p>
              <div className="space-y-3">
                {rejects.map((c, i) => (
                  <div key={i} className="flex items-center gap-3 text-[13px]">
                    <span className="w-44">{c.reason_title}</span>
                    <Bar
                      pct={
                        (c.count /
                          Math.max(1, ...rejects.map((r) => r.count))) *
                        100
                      }
                      color="#C84A2A"
                    />
                    <strong>{c.count}</strong>
                  </div>
                ))}
              </div>
              {!rejects.length && (
                <p className="text-[#616977]">
                  За этот период нет таких решений.
                </p>
              )}
            </Card>
          </div>
          <Card>
            <h2 className="text-[18px] font-bold mb-4">
              Ожидания ответа департаментов
            </h2>
            <table className="w-full text-left text-[14px]">
              <thead>
                <tr className="border-b text-[#616977]">
                  {[
                    "Департамент",
                    "Открытых передач",
                    "Откликов",
                    "Срок подходит",
                    "Просрочено",
                    "Медиана ожидания",
                  ].map((h) => (
                    <th className="pb-3 pr-3" key={h}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {f.open_waits.by_department.map((d) => (
                  <tr key={d.department} className="border-b last:border-0">
                    <td className="py-3">{d.department}</td>
                    <td>{d.total}</td>
                    <td>{d.unique_applications}</td>
                    <td>
                      <Badge tone={d.due_soon_total ? "amber" : "gray"}>
                        {d.due_soon_total}
                      </Badge>
                    </td>
                    <td>
                      <Badge tone={d.overdue_total ? "red" : "gray"}>
                        {d.overdue_total}
                      </Badge>
                    </td>
                    <td>{(d.median_wait_hours / 24).toFixed(1)} кал. дн.</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!f.open_waits.total && (
              <p className="text-[#616977] mt-3">Открытых ожиданий нет.</p>
            )}
          </Card>
        </>
      )}
    </div>
  );
};
export default AnalyticsDashboard;
