import { useEffect, useState } from "react";
import { Card, Btn, Badge } from "../shared/ui";
import {
  EmployeeServiceAccess,
  fieldClass,
  Status,
  useOperation,
} from "./ServiceAccess";
import {
  mobilityRequest as request,
  type Opportunity,
  type Interest,
  type Proposal,
  type Participation,
  type VacancyInterest,
  type ManagerAssignment,
} from "../../api/mobility";
import type { Actor, Page } from "./service";
import { values } from "./ServiceAccess";
import { publicVacancies, type PublicVacancy } from "../../api/portal";
const names: Record<string, string> = {
  draft: "Черновик",
  open: "Открыто",
  submitted: "Интерес направлен",
  selected: "Выбрано для согласования",
  not_selected: "Не выбрано",
  withdrawn: "Отозвано",
  awaiting_employee: "Ждёт вашего согласия",
  awaiting_manager: "На согласовании руководителя",
  agreed: "Согласовано",
  declined: "Отказ",
  active: "Участие начато",
  completed: "Завершено",
  stopped: "Остановлено",
  prepared: "Интерес сохранён",
  recorded: "Рассмотрение зарегистрировано",
};
export function VacancyShowcase() {
  return (
    <EmployeeServiceAccess service="mobility">
      {(token, actor) => (
        <MobilityContent key={actor.actor_id} token={token} actor={actor} />
      )}
    </EmployeeServiceAccess>
  );
}
function MobilityContent({ token, actor }: { token: string; actor: Actor }) {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]),
    [interests, setInterests] = useState<Interest[]>([]),
    [proposals, setProposals] = useState<Proposal[]>([]),
    [participations, setParticipations] = useState<Participation[]>([]),
    [vacancyInterests, setVacancyInterests] = useState<VacancyInterest[]>([]),
    [vacancies, setVacancies] = useState<PublicVacancy[]>([]),
    [peers, setPeers] = useState<
      { actor_id: string; login: string; roles: string[] }[]
    >([]),
    [assignments, setAssignments] = useState<ManagerAssignment[]>([]),
    [query, setQuery] = useState(""),
    [department, setDepartment] = useState(""),
    [tab, setTab] = useState("vacancies"),
    [packageNote, setPackageNote] = useState("");
  const op = useOperation();
  const owner = actor.roles.includes("owner"),
    hr = actor.roles.includes("hr"),
    employee = actor.roles.includes("employee");
  const person = (id: string) =>
    peers.find((p) => p.actor_id === id)?.login || "Сотрудник";
  async function load() {
    const [os, is, ps, parts, vs, people, managers, published] =
      await Promise.all([
        request<Page<Opportunity>>(token, "/opportunities"),
        request<Page<Interest>>(token, "/interests"),
        request<Page<Proposal>>(token, "/proposals"),
        request<Page<Participation>>(token, "/participations"),
        request<Page<VacancyInterest>>(token, "/vacancy-interests"),
        request<Page<{ actor_id: string; login: string; roles: string[] }>>(
          token,
          "/colleagues",
        ),
        request<Page<ManagerAssignment>>(token, "/manager-assignments"),
        publicVacancies(),
      ]);
    setOpportunities(os.items);
    setInterests(is.items);
    setProposals(ps.items);
    setParticipations(parts.items);
    setVacancyInterests(vs.items);
    setPeers(people.items);
    setAssignments(managers.items);
    setVacancies(published);
  }
  async function command(path: string, body: unknown, method?: string) {
    await request(token, path, body, method);
    await load();
  }
  useEffect(() => {
    void op.run(load);
  }, [token]);
  const filtered = vacancies.filter(
    (v) =>
      (!department || v.department_id === department) &&
      (!query ||
        (v.title + " " + v.description)
          .toLowerCase()
          .includes(query.toLowerCase())),
  );
  return (
    <div className="max-w-[1240px] mx-auto px-6 py-8 space-y-5">
      <div className="bg-[#E3F2E7] rounded-3xl p-8 flex items-center gap-5">
        <div className="w-16 h-16 rounded-2xl bg-white flex items-center justify-center text-[28px]">
          💼
        </div>
        <div>
          <h1 className="text-[32px] font-bold">Витрина вакансий</h1>
          <p className="text-[18px] text-[#4A5363]">
            Постоянный переход и временное участие — отдельные процессы с
            подтверждением условий.
          </p>
        </div>
      </div>
      <Status {...op} />
      <div className="flex gap-3">
        {[
          ["vacancies", "Постоянные вакансии"],
          ["opportunities", "Временные задачи"],
          ["agreements", "Согласования и результаты"],
        ].map(([key, label]) => (
          <Btn
            key={key}
            variant={tab === key ? "primary" : "secondary"}
            onClick={() => setTab(key)}
          >
            {label}
          </Btn>
        ))}
        <Btn disabled={op.busy} onClick={() => void op.run(load)}>
          Обновить
        </Btn>
      </div>
      {tab === "vacancies" && (
        <>
          <div className="flex gap-4">
            <input
              className={fieldClass}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Название или описание"
              aria-label="Поиск вакансий"
            />
            <select
              className={fieldClass}
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
            >
              <option value="">Все подразделения</option>
              {Array.from(
                new Map(
                  vacancies.map((v) => [v.department_id, v.department_name]),
                ).entries(),
              ).map(([id, title]) => (
                <option key={id} value={id}>
                  {title}
                </option>
              ))}
            </select>
          </div>
          <div className="grid lg:grid-cols-[2fr_1fr] gap-5 items-start">
            <div className="space-y-5">
              {!filtered.length && (
                <Card>По этим условиям опубликованных вакансий нет.</Card>
              )}
              {filtered.map((v) => (
                <Card key={v.id} className="space-y-3">
                  <h2 className="text-[24px] font-bold">{v.title}</h2>
                  <p>{v.department_name}</p>
                  <p className="whitespace-pre-wrap text-[#4A5363]">
                    {v.description}
                  </p>
                  <Badge>Опубликованная редакция {v.revision}</Badge>
                  {employee && (
                    <form
                      className="space-y-3"
                      onSubmit={(e) => {
                        const val = values(e);
                        void op.run(
                          () =>
                            command("/vacancy-interests", {
                              vacancy_ref: "requirements:" + v.id,
                              publication_revision: v.revision,
                              comment: val.comment,
                            }),
                          "Интерес сохранён. Это ещё не регистрация рассмотрения.",
                        );
                      }}
                    >
                      <textarea
                        className={fieldClass}
                        name="comment"
                        placeholder="Комментарий кадровику"
                        aria-label="Комментарий к интересу"
                      />
                      <Btn
                        type="submit"
                        variant="primary"
                        disabled={
                          op.busy ||
                          vacancyInterests.some(
                            (i) =>
                              i.vacancy_ref === "requirements:" + v.id &&
                              i.publication_revision === v.revision,
                          )
                        }
                      >
                        Сообщить об интересе
                      </Btn>
                    </form>
                  )}
                </Card>
              ))}
            </div>
            <Card className="space-y-4">
              <h2 className="text-[22px] font-bold">
                {hr ? "Интерес сотрудников" : "Мой интерес к вакансиям"}
              </h2>
              {!vacancyInterests.length && (
                <p>Сохранённых обращений пока нет.</p>
              )}
              {vacancyInterests.map((i) => (
                <div key={i.id} className="border-t pt-3 space-y-2">
                  <strong>
                    {vacancies.find(
                      (v) => "requirements:" + v.id === i.vacancy_ref,
                    )?.title || "Ранее опубликованная вакансия"}
                  </strong>
                  <Badge tone="blue">{names[i.status]}</Badge>
                  <p>{i.comment}</p>
                  {i.consideration_ref && (
                    <p>Рассмотрение: {i.consideration_ref}</p>
                  )}
                  {i.confirmation_basis && <p>{i.confirmation_basis}</p>}
                  {hr && i.status === "prepared" && (
                    <form
                      className="space-y-2"
                      onSubmit={(e) => {
                        const v = values(e);
                        void op.run(() =>
                          command(
                            `/vacancy-interests/${i.id}/record-consideration`,
                            {
                              expected_revision: i.revision,
                              consideration_ref: v.ref,
                              confirmation_basis: v.basis,
                            },
                          ),
                        );
                      }}
                    >
                      <input
                        className={fieldClass}
                        name="ref"
                        placeholder="Ссылка на зарегистрированное рассмотрение"
                        aria-label="Ссылка на рассмотрение"
                        required
                      />
                      <textarea
                        className={fieldClass}
                        name="basis"
                        placeholder="Основание подтверждения"
                        aria-label="Основание подтверждения"
                        required
                      />
                      <Btn type="submit" disabled={op.busy}>
                        Подтвердить регистрацию
                      </Btn>
                    </form>
                  )}
                </div>
              ))}
            </Card>
          </div>
        </>
      )}
      {tab === "opportunities" && (
        <>
          <div className="grid lg:grid-cols-[2fr_1fr] gap-5 items-start">
            <div className="space-y-5">
              {!opportunities.length && (
                <Card>Доступных временных задач пока нет.</Card>
              )}
              {opportunities.map((o) => (
                <Card key={o.id} className="space-y-3">
                  <div className="flex justify-between">
                    <h2 className="text-[24px] font-bold">{o.title}</h2>
                    <Badge>{names[o.status]}</Badge>
                  </div>
                  <p>{o.result_description}</p>
                  <p>
                    {o.starts_on} — {o.ends_on} · {o.time_percent}% рабочего
                    времени
                  </p>
                  <p>Владелец: {person(o.owner_actor_id)}</p>
                  {o.status === "draft" &&
                    o.owner_actor_id === actor.actor_id && (
                      <Btn
                        disabled={op.busy}
                        onClick={() =>
                          void op.run(() =>
                            command(`/opportunities/${o.id}/open`, {
                              expected_revision: o.revision,
                            }),
                          )
                        }
                      >
                        Открыть задачу
                      </Btn>
                    )}
                  {o.status === "open" && employee && (
                    <form
                      className="space-y-2"
                      onSubmit={(e) => {
                        const v = values(e);
                        void op.run(
                          () =>
                            command(`/opportunities/${o.id}/interests`, {
                              comment: v.comment,
                            }),
                          "Интерес направлен владельцу задачи.",
                        );
                      }}
                    >
                      <textarea
                        className={fieldClass}
                        name="comment"
                        placeholder="Чем можете помочь"
                        aria-label="Комментарий к задаче"
                      />
                      <Btn
                        type="submit"
                        variant="primary"
                        disabled={
                          op.busy ||
                          interests.some(
                            (i) =>
                              i.opportunity_id === o.id &&
                              i.employee_actor_id === actor.actor_id &&
                              ["submitted", "selected"].includes(i.status),
                          )
                        }
                      >
                        Предложить участие
                      </Btn>
                    </form>
                  )}
                </Card>
              ))}
            </div>
            <div className="space-y-5">
              <Card className="space-y-4">
                <h2 className="text-[22px] font-bold">Заявки на участие</h2>
                {!interests.length && <p>Заявок пока нет.</p>}
                {interests.map((i) => {
                  const opportunity = opportunities.find(
                    (o) => o.id === i.opportunity_id,
                  );
                  const own = opportunity?.owner_actor_id === actor.actor_id;
                  return (
                    <div key={i.id} className="border-t pt-3 space-y-2">
                      <strong>
                        {opportunity?.title || "Задача"} ·{" "}
                        {person(i.employee_actor_id)}
                      </strong>
                      <p>{i.comment}</p>
                      <Badge>{names[i.status]}</Badge>
                      {i.reason && <p>{i.reason}</p>}
                      {own && i.status === "submitted" && (
                        <Btn
                          disabled={op.busy}
                          onClick={() =>
                            void op.run(() =>
                              command(`/interests/${i.id}/select`, {
                                expected_revision: i.revision,
                              }),
                            )
                          }
                        >
                          Выбрать для согласования
                        </Btn>
                      )}
                      {["submitted", "selected"].includes(i.status) &&
                        (own || i.employee_actor_id === actor.actor_id) && (
                          <form
                            className="space-y-2"
                            onSubmit={(e) => {
                              const v = values(e);
                              void op.run(() =>
                                command(
                                  `/interests/${i.id}/${own ? "decline" : "withdraw"}`,
                                  {
                                    expected_revision: i.revision,
                                    reason: v.reason,
                                  },
                                ),
                              );
                            }}
                          >
                            <input
                              className={fieldClass}
                              name="reason"
                              placeholder="Причина"
                              aria-label="Причина отказа или отзыва"
                              required
                            />
                            <Btn type="submit" disabled={op.busy}>
                              {own ? "Не выбрать" : "Отозвать интерес"}
                            </Btn>
                          </form>
                        )}
                      {own && i.status === "selected" && (
                        <form
                          className="space-y-2"
                          onSubmit={(e) => {
                            const v = values(e),
                              manager = assignments.find(
                                (a) =>
                                  a.employee_actor_id === i.employee_actor_id &&
                                  a.manager_actor_id === v.manager,
                              );
                            if (manager)
                              void op.run(() =>
                                command(`/interests/${i.id}/proposal`, {
                                  manager_actor_id: manager.manager_actor_id,
                                  manager_source_reference:
                                    manager.source_reference,
                                  starts_on: v.starts,
                                  ends_on: v.ends,
                                  time_percent: Number(v.percent),
                                }),
                              );
                          }}
                        >
                          <details>
                            <summary className="cursor-pointer">
                              Предложить условия
                            </summary>
                            <select
                              className={fieldClass}
                              name="manager"
                              required
                            >
                              <option value="">
                                Подтверждённый руководитель
                              </option>
                              {assignments
                                .filter(
                                  (a) =>
                                    a.employee_actor_id === i.employee_actor_id,
                                )
                                .map((a) => (
                                  <option
                                    key={a.manager_actor_id}
                                    value={a.manager_actor_id}
                                  >
                                    {person(a.manager_actor_id)}
                                  </option>
                                ))}
                            </select>
                            <label>
                              Начало
                              <input
                                className={fieldClass}
                                name="starts"
                                type="date"
                                defaultValue={opportunity?.starts_on}
                                required
                              />
                            </label>
                            <label>
                              Окончание
                              <input
                                className={fieldClass}
                                name="ends"
                                type="date"
                                defaultValue={opportunity?.ends_on}
                                required
                              />
                            </label>
                            <label>
                              Доля рабочего времени, %
                              <input
                                className={fieldClass}
                                name="percent"
                                type="number"
                                min={1}
                                max={100}
                                defaultValue={opportunity?.time_percent}
                                required
                              />
                            </label>
                            <Btn type="submit" disabled={op.busy}>
                              Отправить условия сотруднику
                            </Btn>
                          </details>
                        </form>
                      )}
                    </div>
                  );
                })}
              </Card>
              {owner && (
                <Card>
                  <h2 className="text-xl font-bold mb-3">
                    Новая временная задача
                  </h2>
                  <form
                    className="space-y-3"
                    onSubmit={(e) => {
                      const v = values(e);
                      void op.run(() =>
                        command("/opportunities", {
                          organization_id: actor.organization_id,
                          owner_actor_id: actor.actor_id,
                          title: v.title,
                          result_description: v.result,
                          starts_on: v.starts,
                          ends_on: v.ends,
                          time_percent: Number(v.percent),
                        }),
                      );
                    }}
                  >
                    <input
                      className={fieldClass}
                      name="title"
                      placeholder="Название"
                      aria-label="Название задачи"
                      required
                    />
                    <textarea
                      className={fieldClass}
                      name="result"
                      placeholder="Ожидаемый результат"
                      aria-label="Ожидаемый результат"
                      required
                    />
                    <label>
                      Начало
                      <input
                        className={fieldClass}
                        name="starts"
                        type="date"
                        required
                      />
                    </label>
                    <label>
                      Окончание
                      <input
                        className={fieldClass}
                        name="ends"
                        type="date"
                        required
                      />
                    </label>
                    <label>
                      Доля рабочего времени, %
                      <input
                        className={fieldClass}
                        name="percent"
                        type="number"
                        min={1}
                        max={100}
                        defaultValue={20}
                        required
                      />
                    </label>
                    <Btn type="submit" disabled={op.busy}>
                      Создать черновик
                    </Btn>
                  </form>
                </Card>
              )}
            </div>
          </div>
        </>
      )}
      {tab === "agreements" && (
        <>
          <Card className="space-y-4">
            <h2 className="text-[22px] font-bold">
              Согласование условий участия
            </h2>
            {!proposals.length && <p>Предложений пока нет.</p>}
            {proposals.map((p) => (
              <div key={p.id} className="border-t pt-4 space-y-3">
                <strong>
                  {person(p.employee_actor_id)} · {names[p.status]}
                </strong>
                <p>
                  {p.starts_on} — {p.ends_on}, {p.time_percent}% времени ·
                  редакция условий {p.conditions_revision}
                </p>
                {p.reason && <p>{p.reason}</p>}
                {((p.employee_actor_id === actor.actor_id &&
                  p.status === "awaiting_employee") ||
                  (p.manager_actor_id === actor.actor_id &&
                    p.status === "awaiting_manager")) && (
                  <form
                    className="space-y-2"
                    onSubmit={(e) => {
                      const v = values(e);
                      void op.run(() =>
                        command(
                          `/proposals/${p.id}/${p.employee_actor_id === actor.actor_id ? "employee-response" : "manager-response"}`,
                          {
                            expected_revision: p.revision,
                            accepted: v.choice === "yes",
                            reason: v.reason || null,
                          },
                        ),
                      );
                    }}
                  >
                    <select name="choice" className={fieldClass}>
                      <option value="yes">Согласовать</option>
                      <option value="no">Отказать</option>
                    </select>
                    <textarea
                      className={fieldClass}
                      name="reason"
                      placeholder="Пояснение (обязательно для отказа руководителя)"
                      aria-label="Пояснение решения"
                    />
                    <Btn type="submit" disabled={op.busy}>
                      Сохранить решение
                    </Btn>
                  </form>
                )}
                {p.owner_actor_id === actor.actor_id &&
                  p.status === "agreed" &&
                  !participations.some(
                    (part) =>
                      part.opportunity_id ===
                        interests.find((i) => i.id === p.interest_id)
                          ?.opportunity_id &&
                      part.employee_actor_id === p.employee_actor_id,
                  ) && (
                    <Btn
                      disabled={op.busy}
                      onClick={() =>
                        void op.run(() =>
                          command(`/proposals/${p.id}/start`, {
                            expected_revision: p.revision,
                          }),
                        )
                      }
                    >
                      Начать участие
                    </Btn>
                  )}
                {p.owner_actor_id === actor.actor_id &&
                  [
                    "awaiting_employee",
                    "awaiting_manager",
                    "agreed",
                    "declined",
                  ].includes(p.status) && (
                    <form
                      className="space-y-2"
                      onSubmit={(e) => {
                        const v = values(e);
                        void op.run(() =>
                          command(
                            `/proposals/${p.id}`,
                            {
                              expected_revision: p.revision,
                              starts_on: v.starts,
                              ends_on: v.ends,
                              time_percent: Number(v.percent),
                              reason: v.reason,
                            },
                            "PATCH",
                          ),
                        );
                      }}
                    >
                      <details>
                        <summary className="cursor-pointer">
                          Изменить условия (согласование начнётся заново)
                        </summary>
                        <input
                          className={fieldClass}
                          name="starts"
                          aria-label="Новое начало"
                          type="date"
                          defaultValue={p.starts_on}
                          required
                        />
                        <input
                          className={fieldClass}
                          name="ends"
                          aria-label="Новое окончание"
                          type="date"
                          defaultValue={p.ends_on}
                          required
                        />
                        <input
                          className={fieldClass}
                          name="percent"
                          aria-label="Новая доля времени"
                          type="number"
                          min={1}
                          max={100}
                          defaultValue={p.time_percent}
                          required
                        />
                        <input
                          className={fieldClass}
                          name="reason"
                          aria-label="Причина изменения условий"
                          placeholder="Причина"
                          required
                        />
                        <Btn type="submit" disabled={op.busy}>
                          Изменить
                        </Btn>
                      </details>
                    </form>
                  )}
              </div>
            ))}
          </Card>
          <Card className="space-y-4">
            <h2 className="text-[22px] font-bold">Участие и результаты</h2>
            {!participations.length && <p>Начатого участия пока нет.</p>}
            {participations.map((p) => (
              <div key={p.id} className="border-t pt-4 space-y-3">
                <h3 className="font-bold">{p.opportunity_title}</h3>
                <Badge>{names[p.status]}</Badge>
                <p>
                  {p.starts_on} — {p.ends_on}, {p.time_percent}% времени
                </p>
                {p.result_note && <p>Результат владельца: {p.result_note}</p>}
                {p.employee_feedback && (
                  <p>
                    Ответ сотрудника:{" "}
                    {p.employee_feedback.accepted ? "Согласен" : "Не согласен"}{" "}
                    · {p.employee_feedback.note}
                  </p>
                )}
                {p.owner_actor_id === actor.actor_id &&
                  p.status === "active" && (
                    <form
                      className="space-y-2"
                      onSubmit={(e) => {
                        const v = values(e);
                        void op.run(() =>
                          command(`/participations/${p.id}/finish`, {
                            expected_revision: p.revision,
                            outcome: v.outcome,
                            result_note: v.note,
                          }),
                        );
                      }}
                    >
                      <select className={fieldClass} name="outcome">
                        <option value="completed">Завершено</option>
                        <option value="stopped">Остановлено</option>
                      </select>
                      <textarea
                        className={fieldClass}
                        name="note"
                        placeholder="Фактический результат"
                        aria-label="Результат участия"
                        required
                      />
                      <Btn type="submit" disabled={op.busy}>
                        Зафиксировать результат
                      </Btn>
                    </form>
                  )}
                {p.employee_actor_id === actor.actor_id &&
                  ["completed", "stopped"].includes(p.status) && (
                    <>
                      <form
                        className="space-y-2"
                        onSubmit={(e) => {
                          const v = values(e);
                          void op.run(() =>
                            command(
                              `/participations/${p.id}/employee-feedback`,
                              {
                                expected_revision: p.revision,
                                accepted: v.accepted === "yes",
                                note: v.note,
                              },
                            ),
                          );
                        }}
                      >
                        <select className={fieldClass} name="accepted">
                          <option value="yes">Согласен с результатом</option>
                          <option value="no">Не согласен</option>
                        </select>
                        <textarea
                          className={fieldClass}
                          name="note"
                          placeholder="Ваш комментарий"
                          aria-label="Обратная связь по результату"
                          required
                        />
                        <Btn type="submit" disabled={op.busy}>
                          Сохранить ответ
                        </Btn>
                      </form>
                      <form
                        className="space-y-2"
                        onSubmit={(e) => {
                          const v = values(e);
                          void op.run(async () => {
                            const result = await request<{ id: string }>(
                              token,
                              `/participations/${p.id}/result-package`,
                              {
                                purpose: v.purpose,
                                share_allowed: v.share === "on",
                              },
                            );
                            const blob = new Blob(
                              [JSON.stringify(result, null, 2)],
                              { type: "application/json" },
                            );
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = "Результат-участия.json";
                            a.click();
                            setTimeout(() => URL.revokeObjectURL(url), 1000);
                            setPackageNote(
                              "Пакет результата сохранён. Передача в другие модули не выполнялась.",
                            );
                          });
                        }}
                      >
                        <input
                          className={fieldClass}
                          name="purpose"
                          placeholder="Цель подготовки результата"
                          aria-label="Цель пакета"
                          required
                        />
                        <label className="flex gap-2">
                          <input type="checkbox" name="share" />
                          Разрешаю передачу выбранного результата
                        </label>
                        <Btn type="submit" disabled={op.busy}>
                          Подготовить и скачать результат
                        </Btn>
                      </form>
                    </>
                  )}
              </div>
            ))}
            {packageNote && <p role="status">{packageNote}</p>}
          </Card>
        </>
      )}
    </div>
  );
}
export default VacancyShowcase;
