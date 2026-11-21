import { useEffect, useState } from "react";
import { Card, Btn, Badge } from "../shared/ui";
import { fieldClass, Status, useOperation } from "./ServiceAccess";
import { feedbackRequest as request } from "../../api/feedback";
import type { Actor, Page } from "./service";
import { values } from "./ServiceAccess";
type Publication = {
  id: string;
  cycle_id: string;
  groups: {
    key: string;
    label: string;
    status: string;
    response_count?: number;
    topics?: { key: string; status: string; count?: number }[];
    scales?: {
      question_key: string;
      categories: { value: number; status: string; count?: number }[];
    }[];
  }[];
  notice: string;
};
type Measure = {
  id: string;
  revision: number;
  publication_id: string;
  group_key: string;
  topic_key: string;
  text: string;
  owner_actor_id: string;
  due_on: string | null;
  status: string;
  outcome_note: string | null;
};
const labels: Record<string, string> = {
  planned: "Запланировано",
  in_progress: "В работе",
  completed: "Выполнено",
  cancelled: "Отменено",
};
export function FeedbackMeasures({
  token,
  actor,
}: {
  token: string;
  actor: Actor;
}) {
  const [publications, setPublications] = useState<Publication[]>([]),
    [measures, setMeasures] = useState<Measure[]>([]),
    [owners, setOwners] = useState<
      { id: string; name: string; group_key: string }[]
    >([]);
  const op = useOperation();
  async function load() {
    const [ps, ms, os] = await Promise.all([
      request<Page<Publication>>(token, "/publications"),
      request<Page<Measure>>(token, "/measures"),
      request<Page<{ id: string; name: string; group_key: string }>>(
        token,
        "/measure-owners",
      ),
    ]);
    setPublications(ps.items);
    setMeasures(ms.items);
    setOwners(os.items);
  }
  useEffect(() => {
    void op.run(load);
  }, [token]);
  return (
    <>
      <Status {...op} />
      <Card className="space-y-4">
        <div className="flex justify-between">
          <h2 className="text-[22px] font-bold">Сводки и меры</h2>
          <Btn disabled={op.busy} onClick={() => void op.run(load)}>
            Обновить сводки
          </Btn>
        </div>
        {publications.map((p) => (
          <div key={p.id} className="space-y-3 border-t pt-4">
            <p className="text-sm text-[#4A5363]">{p.notice}</p>
            {p.groups.map((g) => (
              <div
                key={g.key}
                className="bg-[#F6F7F9] rounded-xl p-4 space-y-3"
              >
                <h3 className="font-bold">{g.label}</h3>
                {g.status === "suppressed" ? (
                  <p>Данные скрыты политикой раскрытия. Числа недоступны.</p>
                ) : (
                  <>
                    <p>Ответов: {g.response_count}</p>
                    {g.scales?.map((s) => (
                      <div key={s.question_key}>
                        <strong>Шкала {s.question_key}</strong>
                        {s.categories.map((c) => (
                          <p key={c.value}>
                            {c.value}:{" "}
                            {c.status === "shown" ? c.count : "скрыто"}
                          </p>
                        ))}
                      </div>
                    ))}
                    {g.topics?.map((t) => (
                      <p key={t.key}>
                        Тема {t.key}:{" "}
                        {t.status === "shown" ? t.count : "скрыто"}
                      </p>
                    ))}
                    {owners.some((o) => o.group_key === g.key) &&
                      g.topics?.some((t) => t.status === "shown") && (
                        <form
                          className="space-y-2"
                          onSubmit={(e) => {
                            const v = values(e);
                            void op.run(async () => {
                              await request(token, "/measures", {
                                publication_id: p.id,
                                group_key: g.key,
                                topic_key: v.topic,
                                text: v.text,
                                owner_actor_id: v.owner,
                                due_on: v.due || null,
                              });
                              await load();
                            }, "Мера сохранена.");
                          }}
                        >
                          <select className={fieldClass} name="topic">
                            {g.topics
                              .filter((t) => t.status === "shown")
                              .map((t) => (
                                <option key={t.key}>{t.key}</option>
                              ))}
                          </select>
                          <textarea
                            className={fieldClass}
                            name="text"
                            placeholder="Что планируем изменить"
                            aria-label="Описание меры"
                            required
                          />
                          <select className={fieldClass} name="owner" required>
                            <option value="">Ответственный</option>
                            {owners
                              .filter((o) => o.group_key === g.key)
                              .map((o) => (
                                <option key={o.id} value={o.id}>
                                  {o.name}
                                </option>
                              ))}
                          </select>
                          <label>
                            Срок
                            <input
                              className={fieldClass}
                              name="due"
                              type="date"
                            />
                          </label>
                          <Btn type="submit" disabled={op.busy}>
                            Создать меру
                          </Btn>
                        </form>
                      )}
                  </>
                )}
                {actor.assignments?.includes("organizer") &&
                  measures.some(
                    (m) => m.publication_id === p.id && m.group_key === g.key,
                  ) && (
                    <form
                      className="space-y-2"
                      onSubmit={(e) => {
                        const v = values(e);
                        void op.run(async () => {
                          await request(
                            token,
                            `/publications/${p.id}/participant-message`,
                            {
                              text: v.text,
                              measure_ids: measures
                                .filter(
                                  (m) =>
                                    m.publication_id === p.id &&
                                    m.group_key === g.key,
                                )
                                .map((m) => m.id),
                            },
                          );
                        }, "Сообщение с текущим состоянием мер опубликовано для группы.");
                      }}
                    >
                      <textarea
                        name="text"
                        className={fieldClass}
                        placeholder="Что сообщить участникам о мерах"
                        aria-label="Сообщение участникам"
                        required
                      />
                      <Btn type="submit" disabled={op.busy}>
                        Опубликовать итоги для группы
                      </Btn>
                    </form>
                  )}
              </div>
            ))}
          </div>
        ))}
        {!publications.length && (
          <p>Доступных зафиксированных сводок пока нет.</p>
        )}
        {measures.map((m) => (
          <div key={m.id} className="border-t pt-4 space-y-2">
            <strong>{m.text}</strong>
            <Badge>{labels[m.status]}</Badge>
            {m.due_on && <p>Срок: {m.due_on}</p>}
            {m.outcome_note && <p>{m.outcome_note}</p>}
            {["planned", "in_progress"].includes(m.status) && (
              <form
                className="space-y-2"
                onSubmit={(e) => {
                  const v = values(e);
                  void op.run(async () => {
                    await request(
                      token,
                      `/measures/${m.id}`,
                      {
                        expected_revision: m.revision,
                        status: v.status,
                        outcome_note: v.note || null,
                      },
                      "PATCH",
                    );
                    await load();
                  });
                }}
              >
                <select className={fieldClass} name="status">
                  {m.status === "planned" && (
                    <option value="in_progress">В работе</option>
                  )}
                  <option value="completed">Выполнено</option>
                  <option value="cancelled">Отменено</option>
                </select>
                <textarea
                  name="note"
                  className={fieldClass}
                  placeholder="Результат или причина отмены"
                  aria-label="Пояснение к мере"
                  required
                />
                <Btn type="submit" disabled={op.busy}>
                  Обновить меру
                </Btn>
              </form>
            )}
          </div>
        ))}
      </Card>
    </>
  );
}
