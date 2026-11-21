import { useState } from "react";
import { Card, Kpi, Badge, Btn, PageTitle } from "../shared/ui";
import { rangeFor, useAnalytics } from "../../api/analytics";
import {
  api,
  deadlineLabel,
  feedbackLabel,
  type Handoff,
} from "../../api/recruitment";
export const HeadSummary = () => {
  const [refresh, setRefresh] = useState(0),
    [selected, setSelected] = useState<Handoff | null>(null);
  const [detailError, setDetailError] = useState(""),
    [busy, setBusy] = useState(false);
  const range = rangeFor("Неделя");
  const { data, error, loading } = useAnalytics(
    range.from,
    range.to,
    "",
    refresh,
  );
  const attention =
    data?.handoffs.filter(
      (h) =>
        h.deadline_status === "overdue" || h.deadline_status === "due_soon",
    ) || [];
  const open = async (id: string) => {
    setBusy(true);
    setDetailError("");
    setSelected(null);
    try {
      setSelected(await api.handoff(id, "hr"));
    } catch (e) {
      setDetailError(
        e instanceof Error ? e.message : "Не удалось открыть передачу",
      );
    } finally {
      setBusy(false);
    }
  };
  const f = data?.funnel;
  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-6">
      <PageTitle
        title="Сводка по подбору"
        subtitle={
          f
            ? `Срез ${new Date(f.as_of).toLocaleString("ru-RU")}`
            : "Актуальные данные подбора"
        }
        right={
          <Btn disabled={loading} onClick={() => setRefresh((x) => x + 1)}>
            Обновить
          </Btn>
        }
      />
      {error && (
        <Card>
          <p role="alert" className="text-red-700">
            {error}
          </p>
        </Card>
      )}
      {loading && <p role="status">Загружаем сводку…</p>}
      {f && (
        <>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Kpi
              label="Вакансии в контуре"
              value={String(data.vacancies.length)}
              caption="каталог подбора"
            />
            <Kpi
              label="Откликов в контуре"
              value={String(f.total_applications)}
              caption="за всё время"
            />
            <Kpi
              label="Ждут решения руководителя"
              value={String(f.open_waits.unique_applications)}
              caption={`${f.open_waits.total} открытых передач`}
            />
            <Kpi
              label="Просрочено передач"
              value={String(f.open_waits.overdue_total)}
              caption={`${f.open_waits.due_soon_total} со скорым сроком ответа`}
            />
          </div>
          <Card className="space-y-4">
            <h2 className="text-[22px] font-bold text-[#141A24]">
              Требует внимания
            </h2>
            <p className="text-[16px] text-[#4A5363]">
              Открытые передачи с подходящим или нарушенным сроком ответа.
            </p>
            {!attention.length && <p>Таких передач сейчас нет.</p>}
            {attention.map((a) => (
              <div
                key={a.attempt_id}
                className="flex items-center justify-between gap-3 border-b pb-3"
              >
                <div>
                  <Badge
                    tone={a.deadline_status === "overdue" ? "red" : "amber"}
                  >
                    {deadlineLabel(a.deadline_status)}
                  </Badge>
                  <p className="text-[17px] font-bold mt-2">
                    {a.candidate_code} ·{" "}
                    {a.vacancy_title || "Вакансия не указана"}
                  </p>
                  <p className="text-[#616977] text-[13px]">
                    {a.recipient_name} · {a.recipient_department} · ответ до{" "}
                    {a.due_date}
                  </p>
                </div>
                <Btn disabled={busy} onClick={() => void open(a.attempt_id)}>
                  Открыть передачу
                </Btn>
              </div>
            ))}
          </Card>
          {detailError && (
            <p role="alert" className="text-red-700">
              {detailError}
            </p>
          )}
          {selected && (
            <Card>
              <div className="flex justify-between">
                <h2 className="text-[20px] font-bold">
                  {selected.candidate_code} · {selected.vacancy_title}
                </h2>
                <Btn onClick={() => setSelected(null)}>Закрыть</Btn>
              </div>
              <p className="my-3">
                {selected.recipient_name} ·{" "}
                {deadlineLabel(selected.deadline_status)} · до{" "}
                {selected.due_date}
              </p>
              {selected.latest_feedback ? (
                <p>
                  {feedbackLabel(selected.latest_feedback.outcome)}.{" "}
                  {selected.latest_feedback.comment}
                </p>
              ) : (
                <p>Ответ департамента ещё не получен.</p>
              )}
              {selected.markdown && (
                <p className="whitespace-pre-wrap text-[14px] mt-4">
                  {selected.markdown}
                </p>
              )}
            </Card>
          )}
          <Card className="overflow-x-auto">
            <h2 className="text-[20px] font-bold mb-3">Вакансии и отклики</h2>
            <table className="w-full text-left">
              <thead>
                <tr className="text-[14px] text-[#4A5363] border-b">
                  {["Вакансия", "Откликов", "Работодатель", "Канал"].map(
                    (h) => (
                      <th className="py-4 pr-4" key={h}>
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {data.vacancies.map((v) => (
                  <tr
                    key={v.vacancy_id}
                    className="border-b last:border-0 text-[16px]"
                  >
                    <td className="py-4 pr-4">{v.title}</td>
                    <td>{v.applications_count}</td>
                    <td>{v.employer || "Не указан"}</td>
                    <td>{v.channel || "Не указан"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.vacancies.length && (
              <p className="text-[#616977] mt-3">В контуре нет вакансий.</p>
            )}
          </Card>
        </>
      )}
    </div>
  );
};
export default HeadSummary;
