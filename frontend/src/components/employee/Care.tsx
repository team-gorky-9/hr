import { useEffect, useState } from "react";
import { Card, Btn, Badge } from "../shared/ui";
import {
  EmployeeServiceAccess,
  fieldClass,
  Status,
  useOperation,
  values,
} from "./ServiceAccess";
import {
  recognitionRequest as request,
  recognitionList as list,
  type RecognitionEvent,
  type Registration,
  type Material,
} from "../../api/recognition";
import type { Actor } from "./service";
import { RecognitionPanel } from "./RecognitionPanel";
const statusLabels: Record<string, string> = {
  confirmed: "Вы записаны",
  waiting: "Лист ожидания",
  awaiting_reconfirmation: "Нужно подтвердить новые условия",
  cancelled: "Запись отменена",
  open: "Запись открыта",
  draft: "Черновик",
  completed: "Завершено",
};
export function Care() {
  return (
    <EmployeeServiceAccess service="recognition">
      {(token, actor) => (
        <CareContent key={actor.id} token={token} actor={actor} />
      )}
    </EmployeeServiceAccess>
  );
}
function CareContent({ token, actor }: { token: string; actor: Actor }) {
  const [events, setEvents] = useState<RecognitionEvent[]>([]),
    [registrations, setRegistrations] = useState<Registration[]>([]),
    [materials, setMaterials] = useState<Material[]>([]),
    [filter, setFilter] = useState("Все"),
    [selected, setSelected] = useState<string | null>(null);
  const op = useOperation();
  const organizer = actor.assignments?.includes("organizer");
  async function load() {
    const [es, ms] = await Promise.all([
      list<RecognitionEvent>(token, "/events"),
      list<Material>(token, "/materials"),
    ]);
    const rs = await Promise.all(
      es.map((e) => list<Registration>(token, `/events/${e.id}/registrations`)),
    );
    setEvents(es);
    setMaterials(ms);
    setRegistrations(rs.flat());
  }
  async function command(path: string, body: unknown, method?: string) {
    await request(token, path, body, method);
    await load();
  }
  useEffect(() => {
    void op.run(load);
  }, [token]);
  const mine = registrations.filter((r) => r.actor_id === actor.id);
  const display = events.filter(
    (e) =>
      filter === "Все" ||
      (filter === "Встречи со специалистом"
        ? e.type === "confidential_session"
        : e.type === "general"),
  );
  return (
    <div className="max-w-[1240px] mx-auto px-6 py-8 space-y-5">
      <div className="bg-[#FFF2D6] rounded-3xl p-8 flex items-center justify-between gap-5">
        <div className="flex gap-5 items-center">
          <div className="w-16 h-16 rounded-2xl bg-white flex items-center justify-center text-[28px]">
            🏅
          </div>
          <div>
            <h1 className="text-[32px] font-bold">Забота и мотивация</h1>
            <p className="text-[18px] text-[#4A5363]">
              Мероприятия, материалы и признание коллег.
            </p>
          </div>
        </div>
        <div className="bg-white rounded-2xl px-6 py-4 border">
          <div className="text-[28px] font-bold">
            {mine.filter((r) => r.status !== "cancelled").length}
          </div>
          <div>моих записей</div>
        </div>
      </div>
      <Status {...op} />
      <div className="flex gap-3">
        {["Все", "Мероприятия", "Встречи со специалистом"].map((f) => (
          <Btn
            key={f}
            variant={filter === f ? "primary" : "secondary"}
            onClick={() => setFilter(f)}
          >
            {f}
          </Btn>
        ))}
        <Btn disabled={op.busy} onClick={() => void op.run(load)}>
          Обновить
        </Btn>
      </div>
      <div className="grid lg:grid-cols-3 gap-5">
        {display.map((e) => {
          const active = mine.find(
            (r) => r.event_id === e.id && r.status !== "cancelled",
          );
          return (
            <div
              key={e.id}
              className={`${e.type === "confidential_session" ? "bg-[#E8EEFC]" : "bg-[#FFF2D6]"} rounded-2xl p-6 space-y-3`}
            >
              <Badge>{statusLabels[e.status] || e.status}</Badge>
              <h2 className="text-[22px] font-bold">{e.title}</h2>
              <p>{e.description}</p>
              <p className="text-[#4A5363]">
                {new Date(e.starts_at).toLocaleString("ru-RU")} · {e.location}
              </p>
              <p>Свободных мест: {e.available_places}</p>
              {e.change_reason && <p>Условия изменились: {e.change_reason}</p>}
              {e.finish_reason && <p>{e.finish_reason}</p>}
              {active ? (
                <Badge tone="blue">{statusLabels[active.status]}</Badge>
              ) : (
                e.status === "open" && (
                  <Btn
                    disabled={op.busy}
                    onClick={() => setSelected(selected === e.id ? null : e.id)}
                  >
                    Записаться
                  </Btn>
                )
              )}
              {selected === e.id && !active && e.status === "open" && (
                <form
                  className="space-y-2"
                  onSubmit={(event) => {
                    const v = values(event);
                    void op.run(async () => {
                      await command(`/events/${e.id}/registrations`, {
                        participants_count: Number(v.count),
                        child_age_bands:
                          e.type === "confidential_session"
                            ? []
                            : (v.children || "")
                                .split(",")
                                .map((x) => x.trim())
                                .filter(Boolean),
                      });
                      setSelected(null);
                    }, "Состояние записи получено от сервера.");
                  }}
                >
                  <label>
                    Количество участников
                    <input
                      className={fieldClass}
                      type="number"
                      name="count"
                      min={1}
                      max={e.type === "confidential_session" ? 1 : 100}
                      defaultValue={1}
                      required
                    />
                  </label>
                  {e.type !== "confidential_session" && (
                    <label>
                      Возрастные группы детей через запятую
                      <input
                        className={fieldClass}
                        name="children"
                        placeholder="0-3, 4-6, 7-12, 13-17"
                      />
                    </label>
                  )}
                  <Btn type="submit" disabled={op.busy}>
                    Подтвердить запись
                  </Btn>
                </form>
              )}
              {organizer && e.organizer_id === actor.id && (
                <div className="border-t pt-3 space-y-2">
                  {e.status === "draft" && (
                    <Btn
                      disabled={op.busy}
                      onClick={() =>
                        void op.run(() =>
                          command(`/events/${e.id}/open`, {
                            expected_revision: e.revision,
                          }),
                        )
                      }
                    >
                      Открыть запись
                    </Btn>
                  )}
                  {e.status === "open" && (
                    <>
                      <form
                        className="space-y-2"
                        onSubmit={(event) => {
                          const v = values(event);
                          void op.run(() =>
                            command(
                              `/events/${e.id}`,
                              {
                                expected_revision: e.revision,
                                starts_at: new Date(v.starts).toISOString(),
                                ends_at: new Date(v.ends).toISOString(),
                                location: v.location,
                                reason: v.reason,
                              },
                              "PATCH",
                            ),
                          );
                        }}
                      >
                        <details>
                          <summary className="cursor-pointer">
                            Изменить условия
                          </summary>
                          <label>
                            Начало
                            <input
                              name="starts"
                              type="datetime-local"
                              className={fieldClass}
                              required
                            />
                          </label>
                          <label>
                            Окончание
                            <input
                              name="ends"
                              type="datetime-local"
                              className={fieldClass}
                              required
                            />
                          </label>
                          <input
                            name="location"
                            aria-label="Место"
                            className={fieldClass}
                            defaultValue={e.location}
                            required
                          />
                          <input
                            name="reason"
                            aria-label="Причина изменения"
                            placeholder="Причина изменения"
                            className={fieldClass}
                            required
                          />
                          <Btn type="submit" disabled={op.busy}>
                            Обновить условия
                          </Btn>
                        </details>
                      </form>
                      <form
                        className="space-y-2"
                        onSubmit={(event) => {
                          const v = values(event);
                          void op.run(() =>
                            command(`/events/${e.id}/finish`, {
                              expected_revision: e.revision,
                              outcome: v.outcome,
                              reason: v.reason,
                            }),
                          );
                        }}
                      >
                        <details>
                          <summary className="cursor-pointer">
                            Завершить мероприятие
                          </summary>
                          <select name="outcome" className={fieldClass}>
                            <option value="completed">Проведено</option>
                            <option value="cancelled">Отменено</option>
                          </select>
                          <input
                            name="reason"
                            aria-label="Основание завершения"
                            className={fieldClass}
                            placeholder="Основание"
                            required
                          />
                          <Btn type="submit" disabled={op.busy}>
                            Сохранить
                          </Btn>
                        </details>
                      </form>
                    </>
                  )}
                  {registrations
                    .filter((r) => r.event_id === e.id)
                    .map((r) => (
                      <div key={r.id} className="text-sm border-t pt-2">
                        Участников: {r.participants_count} ·{" "}
                        {statusLabels[r.status]}
                        {r.status === "waiting" && e.status === "open" && (
                          <Btn
                            disabled={op.busy}
                            onClick={() =>
                              void op.run(() =>
                                command(`/registrations/${r.id}/offer`, {
                                  expected_revision: r.revision,
                                }),
                              )
                            }
                          >
                            Предложить место
                          </Btn>
                        )}
                      </div>
                    ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {!events.length && <Card>Опубликованных мероприятий пока нет.</Card>}
      <div className="grid lg:grid-cols-[2fr_1fr] gap-5">
        <Card className="space-y-4">
          <h2 className="text-[22px] font-bold">Мои записи</h2>
          {!mine.length && <p>Записей пока нет.</p>}
          {mine.map((r) => {
            const e = events.find((e) => e.id === r.event_id);
            return (
              <div key={r.id} className="border-t pt-3 space-y-2">
                <strong>{e?.title}</strong>
                <p>
                  {statusLabels[r.status]} · участников: {r.participants_count}
                </p>
                {r.status === "awaiting_reconfirmation" && (
                  <div className="flex gap-2">
                    <Btn
                      disabled={op.busy}
                      onClick={() =>
                        void op.run(() =>
                          command(`/registrations/${r.id}/reconfirm`, {
                            expected_revision: r.revision,
                            accepted: true,
                          }),
                        )
                      }
                    >
                      Подтвердить новые условия
                    </Btn>
                    <Btn
                      disabled={op.busy}
                      onClick={() =>
                        void op.run(() =>
                          command(`/registrations/${r.id}/reconfirm`, {
                            expected_revision: r.revision,
                            accepted: false,
                          }),
                        )
                      }
                    >
                      Отказаться
                    </Btn>
                  </div>
                )}
                {r.status !== "cancelled" && e?.status === "open" && (
                  <Btn
                    disabled={op.busy}
                    variant="link"
                    onClick={() =>
                      void op.run(() =>
                        command(`/registrations/${r.id}/cancel`, {
                          expected_revision: r.revision,
                        }),
                      )
                    }
                  >
                    Отменить запись
                  </Btn>
                )}
              </div>
            );
          })}
        </Card>
        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Материалы</h2>
          {!materials.length && <p>Материалов пока нет.</p>}
          {materials.map((m) => (
            <div key={m.id} className="border-t pt-3">
              <strong>{m.title}</strong>
              <p>{m.description}</p>
              <p className="text-sm">Версия {m.version}</p>
              {m.url &&
                m.status === "published" &&
                /^https?:\/\//i.test(m.url) && (
                  <a
                    className="text-[#1F4FD1]"
                    href={m.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Открыть материал
                  </a>
                )}
              {organizer && m.status === "draft" && (
                <Btn
                  disabled={op.busy}
                  onClick={() =>
                    void op.run(() =>
                      command(`/materials/${m.id}/publish`, {
                        expected_revision: m.revision,
                      }),
                    )
                  }
                >
                  Опубликовать
                </Btn>
              )}
            </div>
          ))}
        </Card>
      </div>
      {organizer && (
        <div className="grid lg:grid-cols-2 gap-5">
          <Card>
            <h2 className="text-xl font-bold mb-3">Новое мероприятие</h2>
            <form
              className="space-y-3"
              onSubmit={(e) => {
                const v = values(e);
                const element = e.currentTarget;
                void op.run(async () => {
                  await command("/events", {
                    title: v.title,
                    description: v.description,
                    type: v.type,
                    starts_at: new Date(v.starts).toISOString(),
                    ends_at: new Date(v.ends).toISOString(),
                    location: v.location,
                    capacity: Number(v.capacity),
                  });
                  element.reset();
                });
              }}
            >
              <input
                name="title"
                placeholder="Название"
                aria-label="Название"
                className={fieldClass}
                required
              />
              <textarea
                name="description"
                placeholder="Описание"
                aria-label="Описание"
                className={fieldClass}
                required
              />
              <select name="type" className={fieldClass}>
                <option value="general">Общее мероприятие</option>
                <option value="confidential_session">
                  Встреча со специалистом
                </option>
              </select>
              <label>
                Начало
                <input
                  name="starts"
                  type="datetime-local"
                  className={fieldClass}
                  required
                />
              </label>
              <label>
                Окончание
                <input
                  name="ends"
                  type="datetime-local"
                  className={fieldClass}
                  required
                />
              </label>
              <input
                name="location"
                placeholder="Место"
                aria-label="Место"
                className={fieldClass}
                required
              />
              <input
                name="capacity"
                type="number"
                min={1}
                defaultValue={10}
                aria-label="Вместимость"
                className={fieldClass}
                required
              />
              <Btn type="submit" disabled={op.busy}>
                Создать черновик
              </Btn>
            </form>
          </Card>
          <Card>
            <h2 className="text-xl font-bold mb-3">Новый материал</h2>
            <form
              className="space-y-3"
              onSubmit={(e) => {
                const v = values(e);
                void op.run(() =>
                  command("/materials", {
                    title: v.title,
                    description: v.description,
                    url: v.url,
                    version: 1,
                    audience_scope: { kind: "organization", actor_ids: [] },
                    distribution_basis: v.basis,
                  }),
                );
              }}
            >
              <input
                className={fieldClass}
                name="title"
                placeholder="Название"
                aria-label="Название материала"
                required
              />
              <textarea
                className={fieldClass}
                name="description"
                placeholder="Описание"
                aria-label="Описание материала"
                required
              />
              <input
                className={fieldClass}
                name="url"
                type="url"
                placeholder="https://"
                aria-label="Ссылка на материал"
                required
              />
              <textarea
                className={fieldClass}
                name="basis"
                placeholder="Основание распространения всей организации"
                aria-label="Основание распространения"
                required
              />
              <Btn type="submit" disabled={op.busy}>
                Сохранить материал
              </Btn>
            </form>
          </Card>
        </div>
      )}
      <RecognitionPanel token={token} actor={actor} />
    </div>
  );
}
export default Care;
