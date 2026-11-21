import { useEffect, useState } from "react";
import { Card, Badge, Btn } from "../shared/ui";
import ServiceAccess from "../shared/ServiceAccess";
import { developmentRequest, type Actor } from "../../api/development";
import { Status, useOperation } from "./ServiceAccess";
type Step = {
  key: string;
  title: string;
  description: string;
  material_url: string | null;
  acknowledged_at: string | null;
};
type Program = {
  id: string;
  revision: number;
  status: string;
  template_code: string;
  completed_count: number;
  total_count: number;
  steps: Step[];
};
type Template = { code: string; title: string };
const env = (import.meta as ImportMeta & { env: Record<string, string> }).env;
export function Workspace({
  onNavigate,
}: {
  onNavigate: (tab: string) => void;
}) {
  return (
    <ServiceAccess initialLogin="employee">
      {(token, _role, actor) => (
        <WorkspaceContent
          key={actor.actor_id}
          token={token}
          actor={actor}
          onNavigate={onNavigate}
        />
      )}
    </ServiceAccess>
  );
}
function WorkspaceContent({
  token,
  actor,
  onNavigate,
}: {
  token: string;
  actor: Actor;
  onNavigate: (tab: string) => void;
}) {
  const [programs, setPrograms] = useState<Program[]>([]),
    [templates, setTemplates] = useState<Template[]>([]);
  const op = useOperation();
  async function load() {
    const [ps, ts] = await Promise.all([
      developmentRequest<{ items: Program[] }>(token, "/onboarding/programs"),
      developmentRequest<{ items: Template[] }>(token, "/onboarding/templates"),
    ]);
    setPrograms(ps.items);
    setTemplates(ts.items);
  }
  useEffect(() => {
    void op.run(load);
  }, [token]);
  const active = programs.filter((p) => p.status === "active"),
    total = active.reduce((n, p) => n + p.total_count, 0),
    done = active.reduce((n, p) => n + p.completed_count, 0);
  async function acknowledge(program: Program, step: Step) {
    const res = await fetch(
      (env.VITE_DEVELOPMENT_API_BASE || "/workforce-api") +
        `/onboarding/programs/${program.id}/steps/${step.key}/acknowledge`,
      {
        method: "POST",
        headers: {
          Authorization: "Bearer " + token,
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({ expected_revision: program.revision }),
      },
    );
    const data = await res.json();
    if (!res.ok)
      throw new Error(
        data?.error?.message || "Не удалось подтвердить ознакомление.",
      );
    await load();
  }
  return (
    <div className="max-w-[1240px] mx-auto px-6 py-8 space-y-5">
      <div className="bg-[#1F4FD1] rounded-3xl p-8 flex items-center justify-between gap-6 text-white">
        <div>
          <h1 className="text-[32px] font-bold">Добрый день, {actor.login}!</h1>
          <p className="text-[18px] mt-2 text-[#DCE5FB]">
            Ваши программы адаптации и рабочие разделы.
          </p>
        </div>
        <div className="flex gap-4">
          {[
            [
              total ? `${Math.round((done / total) * 100)}%` : "—",
              "адаптации пройдено",
            ],
            [String(active.length), "активных программ"],
            [String(Math.max(0, total - done)), "шагов осталось"],
          ].map(([n, label]) => (
            <div
              key={label}
              className="bg-white/15 rounded-2xl px-5 py-4 min-w-[160px]"
            >
              <div className="text-[28px] font-bold">{n}</div>
              <div className="text-[#DCE5FB]">{label}</div>
            </div>
          ))}
        </div>
      </div>
      <Status {...op} />
      <div className="grid grid-cols-3 gap-5">
        {[
          [
            "🛡",
            "bg-[#F1EDFF]",
            "Опросы и обратная связь",
            "Доступные опросы, результаты и личные обращения",
            "surveys",
          ],
          [
            "🏅",
            "bg-[#FFEFD9]",
            "Забота и мотивация",
            "Мероприятия, благодарности и материалы",
            "care",
          ],
          [
            "💼",
            "bg-[#E3F2E7]",
            "Внутренняя мобильность",
            "Вакансии и временные задачи",
            "vacancies",
          ],
        ].map(([icon, bg, title, text, tab]) => (
          <Card key={tab} className="space-y-3">
            <div className="flex gap-4 items-center">
              <div
                className={`${bg} w-[52px] h-[52px] rounded-xl flex items-center justify-center text-[22px]`}
              >
                {icon}
              </div>
              <h2 className="text-[18px] font-bold">{title}</h2>
            </div>
            <p className="text-[#4A5363]">{text}</p>
            <Btn variant="link" onClick={() => onNavigate(tab)}>
              Открыть раздел
            </Btn>
          </Card>
        ))}
      </div>
      <div className="grid grid-cols-[2fr_1fr] gap-5 items-start">
        <div className="space-y-5">
          <Card className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-[22px] font-bold">Адаптация</h2>
              <Btn disabled={op.busy} onClick={() => void op.run(load)}>
                Обновить
              </Btn>
            </div>
            {!programs.length && (
              <p>Вам пока не назначена программа адаптации.</p>
            )}
            {programs.map((p) => (
              <div key={p.id} className="space-y-3 border-t pt-4">
                <h3 className="font-bold">
                  {templates.find((t) => t.code === p.template_code)?.title ||
                    "Программа адаптации"}
                </h3>
                <p>
                  {p.completed_count} из {p.total_count} шагов ·{" "}
                  {p.status === "active"
                    ? "В работе"
                    : p.status === "completed"
                      ? "Завершена"
                      : "Отменена"}
                </p>
                <div className="h-[10px] rounded-full bg-[#E8ECF2]">
                  <div
                    className="h-full rounded-full bg-[#1F4FD1]"
                    style={{
                      width: `${p.total_count ? (p.completed_count / p.total_count) * 100 : 0}%`,
                    }}
                  />
                </div>
                {p.steps.map((s) => (
                  <div key={s.key} className="border-t py-3 space-y-2">
                    <div className="flex justify-between gap-3">
                      <strong>{s.title}</strong>
                      <Badge tone={s.acknowledged_at ? "green" : "gray"}>
                        {s.acknowledged_at
                          ? "Ознакомление подтверждено"
                          : "Не подтверждено"}
                      </Badge>
                    </div>
                    <p className="text-[#4A5363]">{s.description}</p>
                    {s.material_url && /^https?:\/\//i.test(s.material_url) && (
                      <a
                        className="block text-[#1F4FD1]"
                        href={s.material_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Открыть материал
                      </a>
                    )}
                    {!s.acknowledged_at && p.status === "active" && (
                      <Btn
                        disabled={op.busy}
                        onClick={() =>
                          void op.run(
                            () => acknowledge(p, s),
                            "Ознакомление сохранено.",
                          )
                        }
                      >
                        Подтвердить ознакомление
                      </Btn>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </Card>
          <Card className="space-y-4">
            <h2 className="text-[22px] font-bold">Мои обращения и документы</h2>
            <p className="text-[#4A5363]">
              Документы по материальной помощи подаются и дополняются в
              соответствующем обращении.
            </p>
            <Btn onClick={() => onNavigate("support")}>Материальная помощь</Btn>
            <p className="text-sm text-[#4A5363]">
              Выдача справок и оформление отпуска в этом сервисе пока не
              реализованы.
            </p>
          </Card>
        </div>
        <div className="space-y-5">
          <Card className="space-y-3">
            <h2 className="text-[22px] font-bold">Моё развитие</h2>
            <p>Цели, согласованные планы и подтверждение результатов.</p>
            <Btn onClick={() => onNavigate("development")}>
              Открыть план развития
            </Btn>
          </Card>
          <Card className="space-y-3">
            <h2 className="text-[22px] font-bold">Кадровые сведения</h2>
            <p>
              Программы адаптации и назначения доступны в кадровом разделе
              согласно вашим правам.
            </p>
            <Btn onClick={() => onNavigate("onboarding")}>
              Открыть адаптацию
            </Btn>
            {actor.grants.some(
              (g) => g.role === "hr" || g.role === "admin",
            ) && (
              <Btn onClick={() => onNavigate("workforce")}>
                Сотрудники и назначения
              </Btn>
            )}
          </Card>
          <Card className="space-y-3">
            <h2 className="text-[22px] font-bold">Личное обращение</h2>
            <p className="text-[#4A5363]">
              Выберите адресата, отправьте вопрос и прочитайте ответ в разделе
              обратной связи.
            </p>
            <Btn onClick={() => onNavigate("surveys")}>
              Отправить личное обращение
            </Btn>
          </Card>
          <Card className="space-y-3">
            <h2 className="text-[22px] font-bold">Ближайшие события</h2>
            <p>
              Актуальные даты, места и ваши записи доступны в календаре
              мероприятий.
            </p>
            <Btn onClick={() => onNavigate("care")}>Открыть мероприятия</Btn>
          </Card>
        </div>
      </div>
    </div>
  );
}
export default Workspace;
