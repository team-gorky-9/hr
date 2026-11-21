import { useEffect, useState, type FormEvent } from "react";
import { Card, Btn, Badge } from "../shared/ui";
import {
  EmployeeServiceAccess,
  fieldClass,
  Status,
  useOperation,
} from "./ServiceAccess";
import {
  feedbackApi,
  feedbackRequest,
  type Cycle,
  type SurveyForm,
  type Outcome,
  type ConfidentialCase,
} from "../../api/feedback";
import type { Actor, Page } from "./service";
import { FeedbackMeasures } from "./FeedbackMeasures";
const labels: Record<string, string> = {
  draft: "Черновик",
  open: "Открыт",
  closed: "Завершён",
  submitted: "Отправлено",
  answered: "Есть ответ",
  planned: "Запланировано",
  in_progress: "В работе",
  completed: "Выполнено",
  cancelled: "Отменено",
};
function formValues(e: FormEvent<HTMLFormElement>) {
  e.preventDefault();
  return Object.fromEntries(new FormData(e.currentTarget)) as Record<
    string,
    string
  >;
}
export function Surveys() {
  return (
    <EmployeeServiceAccess service="feedback">
      {(token, actor) => (
        <SurveysContent key={actor.id} token={token} actor={actor} />
      )}
    </EmployeeServiceAccess>
  );
}
function SurveysContent({ token, actor }: { token: string; actor: Actor }) {
  const [cycles, setCycles] = useState<Cycle[]>([]),
    [selected, setSelected] = useState<Cycle | null>(null),
    [form, setForm] = useState<SurveyForm | null>(null),
    [outcome, setOutcome] = useState<Outcome | null>(null),
    [answers, setAnswers] = useState<Record<string, string>>({}),
    [codes, setCodes] = useState<string[]>([]),
    [recipients, setRecipients] = useState<{ id: string; name: string }[]>([]),
    [cases, setCases] = useState<ConfidentialCase[]>([]),
    [done, setDone] = useState(false);
  const op = useOperation();
  const organizer = actor.assignments?.includes("organizer");
  async function load() {
    const [list, people, caseList] = await Promise.all([
      feedbackApi.cycles(token),
      feedbackRequest<{ items: { id: string; name: string }[] }>(
        token,
        "/confidential-recipients",
      ),
      feedbackRequest<Page<ConfidentialCase>>(token, "/confidential-cases"),
    ]);
    setCycles(list.items);
    setRecipients(people.items);
    setCases(caseList.items);
  }
  async function open(c: Cycle) {
    setSelected(c);
    setAnswers({});
    setDone(false);
    setCodes([]);
    setForm(null);
    setOutcome(null);
    if (c.status !== "draft") {
      const [f, o] = await Promise.all([
        feedbackApi.form(c.id),
        feedbackApi.outcome(token, c.id),
      ]);
      setForm(f);
      setOutcome(o);
    }
  }
  async function transition(c: Cycle, action: string, body: unknown) {
    const updated = await feedbackRequest<Cycle>(
      token,
      `/cycles/${c.id}/${action}`,
      body,
    );
    await load();
    if (action !== "publication") await open({ ...c, ...updated });
  }
  useEffect(() => {
    void op.run(load);
  }, [token]);
  return (
    <div className="max-w-[1240px] mx-auto px-6 py-8 space-y-5">
      <div className="bg-[#F1EDFF] rounded-3xl p-8 flex gap-5 items-center">
        <div className="w-16 h-16 rounded-2xl bg-white flex items-center justify-center text-[28px]">
          🛡
        </div>
        <div>
          <h1 className="text-[32px] font-bold">Опросы</h1>
          <p className="text-[18px] text-[#4A5363]">
            Добровольные опросы и обратная связь по принятым мерам.
          </p>
        </div>
      </div>
      <Status {...op} />
      <Btn disabled={op.busy} onClick={() => void op.run(load)}>
        Обновить
      </Btn>
      <div className="grid lg:grid-cols-[2fr_1fr] gap-5 items-start">
        <Card className="space-y-4">
          {!selected ? (
            <p>Выберите доступный опрос.</p>
          ) : (
            <>
              <div className="flex justify-between">
                <h2 className="text-[24px] font-bold">{selected.title}</h2>
                <Badge tone="purple">{labels[selected.status]}</Badge>
              </div>
              {form && (
                <>
                  <p className="text-sm text-[#4A5363]">
                    {form.privacy_notice}
                  </p>
                  {done ? (
                    <p role="status" className="text-green-800 font-bold">
                      Сервер принял ответы. Повторная отправка по этому коду
                      невозможна.
                    </p>
                  ) : form.status === "open" ? (
                    <form
                      className="space-y-4"
                      onSubmit={(e) => {
                        const v = formValues(e);
                        void op.run(async () => {
                          await feedbackRequest(
                            null,
                            `/cycles/${form.id}/responses`,
                            {
                              access_code: v.access_code,
                              answers: form.questions.map((q) => ({
                                question_key: q.key,
                                value: Number(answers[q.key]),
                              })),
                              topic_key: v.topic,
                            },
                          );
                          setDone(true);
                          setAnswers({});
                        }, "Ответы сохранены.");
                      }}
                    >
                      {form.questions.map((q) => (
                        <label className="block" key={q.key}>
                          <span className="font-semibold">{q.text}</span>
                          <span className="block text-sm text-[#4A5363]">
                            Шкала от {q.min} до {q.max}
                          </span>
                          <input
                            type="number"
                            min={q.min}
                            max={q.max}
                            required
                            className={fieldClass}
                            value={answers[q.key] ?? ""}
                            onChange={(e) =>
                              setAnswers({
                                ...answers,
                                [q.key]: e.target.value,
                              })
                            }
                          />
                        </label>
                      ))}
                      <label className="block">
                        Какая тема важнее сейчас?
                        <select
                          required
                          name="topic"
                          className={fieldClass}
                          defaultValue=""
                        >
                          <option value="" disabled>
                            Выберите тему
                          </option>
                          {form.topic_options.map((t) => (
                            <option key={t.key} value={t.key}>
                              {t.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="block">
                        Одноразовый код приглашения
                        <input
                          name="access_code"
                          autoComplete="off"
                          type="password"
                          className={fieldClass}
                          required
                          minLength={20}
                        />
                      </label>
                      <Btn type="submit" variant="primary" disabled={op.busy}>
                        Отправить ответы
                      </Btn>
                    </form>
                  ) : (
                    <p>Приём ответов завершён.</p>
                  )}
                </>
              )}
              {organizer && (
                <div className="border-t pt-4 space-y-3">
                  {selected.status === "draft" && (
                    <Btn
                      disabled={op.busy}
                      onClick={() =>
                        void op.run(() =>
                          transition(selected, "open", {
                            expected_revision: selected.revision,
                          }),
                        )
                      }
                    >
                      Открыть опрос
                    </Btn>
                  )}
                  {selected.status === "open" && (
                    <>
                      <form
                        className="space-y-3"
                        onSubmit={(e) => {
                          const v = formValues(e);
                          void op.run(async () => {
                            const response = await feedbackRequest<{
                              codes: string[];
                            }>(token, `/cycles/${selected.id}/access-codes`, {
                              group_key: v.group,
                              count: Number(v.count),
                            });
                            setCodes(response.codes);
                          });
                        }}
                      >
                        <h3 className="font-bold">Выпустить приглашения</h3>
                        <select name="group" className={fieldClass}>
                          {selected.groups?.map((g) => (
                            <option key={g.key} value={g.key}>
                              {g.label}
                            </option>
                          ))}
                        </select>
                        <input
                          className={fieldClass}
                          name="count"
                          aria-label="Количество кодов"
                          type="number"
                          min={1}
                          max={1000}
                          defaultValue={1}
                        />
                        <Btn disabled={op.busy} type="submit">
                          Получить коды
                        </Btn>
                      </form>
                      {!!codes.length && (
                        <div className="rounded-xl bg-[#FFF8E8] p-4">
                          <p>
                            Коды показываются один раз. Передайте их участникам
                            вне этого кабинета.
                          </p>
                          <textarea
                            readOnly
                            className={fieldClass}
                            value={codes.join("\n")}
                            rows={Math.min(6, codes.length)}
                          />
                        </div>
                      )}
                      <Btn
                        disabled={op.busy}
                        onClick={() =>
                          void op.run(() =>
                            transition(selected, "close", {
                              expected_revision: selected.revision,
                            }),
                          )
                        }
                      >
                        Завершить приём ответов
                      </Btn>
                    </>
                  )}
                  {selected.status === "closed" && (
                    <form
                      className="space-y-3"
                      onSubmit={(e) => {
                        const v = formValues(e);
                        void op.run(async () => {
                          await transition(selected, "publication", {
                            expected_revision: selected.revision,
                            policy: { k: Number(v.k) },
                            policy_basis: v.basis,
                          });
                        }, "Сводка зафиксирована на сервере.");
                      }}
                    >
                      <h3 className="font-bold">Зафиксировать сводку</h3>
                      <label>
                        Порог раскрытия
                        <input
                          className={fieldClass}
                          name="k"
                          type="number"
                          min={2}
                          defaultValue={5}
                          required
                        />
                      </label>
                      <label>
                        Основание политики
                        <textarea
                          className={fieldClass}
                          name="basis"
                          required
                        />
                      </label>
                      <Btn type="submit" disabled={op.busy}>
                        Зафиксировать
                      </Btn>
                    </form>
                  )}
                </div>
              )}
            </>
          )}
        </Card>
        <div className="space-y-5">
          <Card className="space-y-3">
            <h2 className="text-[22px] font-bold">Все опросы</h2>
            {cycles.length === 0 && <p>Доступных опросов пока нет.</p>}
            {cycles.map((c) => (
              <button
                key={c.id}
                className="block w-full text-left border-b py-3"
                disabled={op.busy}
                onClick={() => void op.run(() => open(c))}
              >
                <span>{c.title}</span>
                <span className="block text-sm text-[#4A5363]">
                  {labels[c.status]}
                </span>
              </button>
            ))}
          </Card>
          {organizer && (
            <Card>
              <h2 className="text-xl font-bold mb-3">Новый опрос</h2>
              <form
                className="space-y-3"
                onSubmit={(e) => {
                  const v = formValues(e);
                  void op.run(async () => {
                    const c = await feedbackRequest<Cycle>(token, "/cycles", {
                      title: v.title,
                      question_version: "1",
                      questions: [
                        { key: "pulse", text: v.question, min: 1, max: 5 },
                      ],
                      topic_options: v.topics
                        .split("\n")
                        .filter((x) => x.trim())
                        .map((label, i) => ({
                          key: "topic_" + i,
                          label: label.trim(),
                        })),
                      groups: [
                        {
                          key: v.group,
                          label: v.group_label,
                          eligible_count: Number(v.count),
                        },
                      ],
                    });
                    await load();
                    await open(c);
                  });
                }}
              >
                <input
                  className={fieldClass}
                  name="title"
                  placeholder="Название"
                  aria-label="Название опроса"
                  required
                />
                <textarea
                  className={fieldClass}
                  name="question"
                  placeholder="Вопрос по шкале 1–5"
                  aria-label="Вопрос"
                  required
                />
                <textarea
                  className={fieldClass}
                  name="topics"
                  placeholder="Темы, каждая с новой строки"
                  aria-label="Темы"
                  required
                />
                <input
                  className={fieldClass}
                  name="group"
                  defaultValue="large"
                  aria-label="Код группы"
                  required
                  pattern="[a-z][a-z0-9_-]{0,49}"
                />
                <input
                  className={fieldClass}
                  name="group_label"
                  placeholder="Название группы"
                  aria-label="Название группы"
                  required
                />
                <input
                  className={fieldClass}
                  name="count"
                  type="number"
                  min={1}
                  defaultValue={10}
                  aria-label="Численность группы"
                  required
                />
                <Btn type="submit" disabled={op.busy}>
                  Создать черновик
                </Btn>
              </form>
            </Card>
          )}
        </div>
      </div>
      <Card className="space-y-3">
        <h2 className="text-[22px] font-bold">Что изменили по итогам</h2>
        {!outcome?.messages.length && (
          <p>Опубликованных сообщений о мерах пока нет.</p>
        )}
        {outcome?.messages.map((m) => (
          <div key={m.id}>
            <p className="font-semibold">{m.text}</p>
            {m.measures.map((measure) => (
              <p key={measure.id} className="mt-2">
                {measure.text} · {labels[measure.status] || measure.status}
                {measure.outcome_note ? " — " + measure.outcome_note : ""}
              </p>
            ))}
          </div>
        ))}
      </Card>
      <FeedbackMeasures token={token} actor={actor} />
      <div className="grid lg:grid-cols-[1fr_1fr] gap-5">
        <Card>
          <h2 className="text-[22px] font-bold mb-3">Личное обращение</h2>
          <p className="text-sm text-[#4A5363] mb-3">
            Обращение именное: его видят автор и выбранный адресат. Оно не
            связано с ответами на опрос.
          </p>
          <form
            className="space-y-3"
            onSubmit={(e) => {
              const v = formValues(e);
              const element = e.currentTarget;
              void op.run(async () => {
                await feedbackRequest(token, "/confidential-cases", {
                  recipient_actor_id: v.recipient,
                  subject: v.subject,
                  text: v.text,
                });
                element.reset();
                await load();
              }, "Обращение отправлено.");
            }}
          >
            <select className={fieldClass} name="recipient" required>
              <option value="">Выберите адресата</option>
              {recipients
                .filter((r) => r.id !== actor.id)
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
            </select>
            <input
              className={fieldClass}
              name="subject"
              placeholder="Тема"
              aria-label="Тема обращения"
              required
            />
            <textarea
              className={fieldClass}
              name="text"
              placeholder="Ваш вопрос"
              aria-label="Текст обращения"
              required
            />
            <Btn
              type="submit"
              variant="primary"
              disabled={op.busy || !recipients.length}
            >
              Отправить
            </Btn>
          </form>
        </Card>
        <Card className="space-y-4">
          <h2 className="text-[22px] font-bold">Мои обращения</h2>
          {!cases.length && <p>Обращений пока нет.</p>}
          {cases.map((c) => (
            <div key={c.id} className="border-t pt-3 space-y-2">
              <h3 className="font-bold">
                {c.subject} · {labels[c.status]}
              </h3>
              <p>{c.text}</p>
              {c.reply && <p className="text-[#1F4FD1]">Ответ: {c.reply}</p>}
              {c.close_reason && <p>Причина закрытия: {c.close_reason}</p>}
              {c.status !== "closed" && (
                <form
                  className="space-y-2"
                  onSubmit={(e) => {
                    const v = formValues(e);
                    void op.run(async () => {
                      await feedbackRequest(
                        token,
                        `/confidential-cases/${c.id}/${v.action}`,
                        {
                          expected_revision: c.revision,
                          ...(v.action === "reply"
                            ? { text: v.text }
                            : { reason: v.text }),
                        },
                      );
                      await load();
                    });
                  }}
                >
                  <textarea
                    className={fieldClass}
                    name="text"
                    aria-label="Ответ или причина закрытия"
                    required
                  />
                  <select name="action" className={fieldClass}>
                    {c.recipient_actor_id === actor.id && (
                      <option value="reply">Ответить</option>
                    )}
                    <option value="close">Закрыть обращение</option>
                  </select>
                  <Btn type="submit" disabled={op.busy}>
                    Сохранить
                  </Btn>
                </form>
              )}
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}
export default Surveys;
