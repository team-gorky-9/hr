import { useEffect, useState } from "react";
import { Card, Btn, Badge } from "../shared/ui";
import { fieldClass, Status, useOperation } from "./ServiceAccess";
import {
  recognitionRequest as request,
  recognitionList as list,
  type Thanks,
  type Campaign,
  type Nomination,
} from "../../api/recognition";
import type { Actor, Page } from "./service";
import { values } from "./ServiceAccess";
const names: Record<string, string> = {
  pending: "Ожидает согласия или проверки",
  private: "Личная благодарность",
  published: "Опубликовано",
  withdrawn: "Отозвано",
  awaiting_consent: "Ожидает согласия",
  submitted: "На рассмотрении",
  declined: "Участие отклонено",
  selected: "Выбран",
  not_selected: "Не выбран",
  draft: "Черновик",
  open: "Открыт",
  closed: "Завершён",
};
export function RecognitionPanel({
  token,
  actor,
}: {
  token: string;
  actor: Actor;
}) {
  const [peers, setPeers] = useState<{ id: string; name: string }[]>([]),
    [thanks, setThanks] = useState<Thanks[]>([]),
    [view, setView] = useState("received"),
    [campaigns, setCampaigns] = useState<Campaign[]>([]),
    [nominations, setNominations] = useState<Nomination[]>([]);
  const op = useOperation();
  const organizer = actor.assignments?.includes("organizer");
  const person = (id: string) =>
    peers.find((p) => p.id === id)?.name || "Сотрудник";
  async function load() {
    const [ps, ts, cs, ns] = await Promise.all([
      request<Page<{ id: string; name: string }>>(token, "/colleagues"),
      list<Thanks>(token, "/thanks?view=" + view),
      list<Campaign>(token, "/campaigns"),
      list<Nomination>(token, "/nominations"),
    ]);
    setPeers(ps.items);
    setThanks(ts);
    setCampaigns(cs);
    setNominations(ns);
  }
  async function command(path: string, body: unknown, method?: string) {
    await request(token, path, body, method);
    await load();
  }
  useEffect(() => {
    void op.run(load);
  }, [token, view]);
  const options = peers
    .filter((p) => p.id !== actor.id)
    .map((p) => (
      <option key={p.id} value={p.id}>
        {p.name}
      </option>
    ));
  return (
    <>
      <Status {...op} />
      <div className="grid lg:grid-cols-[2fr_1fr] gap-5">
        <Card className="space-y-4">
          <h2 className="text-[22px] font-bold">Благодарности</h2>
          <div className="flex gap-2 flex-wrap">
            {[
              ["received", "Мне"],
              ["mine", "От меня"],
              ["wall", "Стена признания"],
              ...(actor.assignments?.includes("moderator")
                ? [["moderation", "На проверке"]]
                : []),
            ].map(([key, label]) => (
              <Btn
                key={key}
                variant={view === key ? "primary" : "secondary"}
                onClick={() => setView(key)}
              >
                {label}
              </Btn>
            ))}
          </div>
          {!thanks.length && <p>Благодарностей пока нет.</p>}
          {thanks.map((t) => (
            <div key={t.id} className="border-t pt-4 space-y-3">
              <p className="font-semibold">
                {person(t.author_id)} → {person(t.recipient_id)}
              </p>
              <p>{t.text}</p>
              <Badge>{names[t.status]}</Badge>
              {t.moderation_reason && <p>{t.moderation_reason}</p>}
              {actor.id === t.recipient_id && t.status !== "withdrawn" && (
                <div className="flex gap-2 flex-wrap">
                  {[
                    ["private", "Оставить личной"],
                    ["organization", "Разрешить публикацию"],
                    ["declined", "Не принимать"],
                  ].map(([choice, label]) => (
                    <Btn
                      key={choice}
                      disabled={op.busy}
                      onClick={() =>
                        void op.run(() =>
                          command(`/thanks/${t.id}/visibility`, {
                            expected_revision: t.revision,
                            choice,
                          }),
                        )
                      }
                    >
                      {label}
                    </Btn>
                  ))}
                </div>
              )}
              {view === "moderation" &&
                t.status === "pending" &&
                t.moderation_status === "pending" && (
                  <form
                    className="space-y-2"
                    onSubmit={(e) => {
                      const v = values(e);
                      void op.run(() =>
                        command(`/thanks/${t.id}/moderation`, {
                          expected_revision: t.revision,
                          result: v.result,
                          reason: v.reason,
                        }),
                      );
                    }}
                  >
                    <select className={fieldClass} name="result">
                      <option value="approved">Одобрить</option>
                      <option value="returned">Вернуть</option>
                    </select>
                    <input
                      className={fieldClass}
                      name="reason"
                      aria-label="Основание модерации"
                      placeholder="Основание"
                      required
                    />
                    <Btn type="submit" disabled={op.busy}>
                      Сохранить решение
                    </Btn>
                  </form>
                )}
              {t.status !== "withdrawn" &&
                [t.author_id, t.recipient_id].includes(actor.id || "") && (
                  <form
                    className="space-y-2"
                    onSubmit={(e) => {
                      const v = values(e);
                      void op.run(() =>
                        command(`/thanks/${t.id}/withdraw`, {
                          expected_revision: t.revision,
                          reason: v.reason,
                        }),
                      );
                    }}
                  >
                    <details>
                      <summary className="cursor-pointer">
                        Отозвать благодарность
                      </summary>
                      <input
                        name="reason"
                        className={fieldClass}
                        aria-label="Причина отзыва"
                        required
                      />
                      <Btn type="submit" disabled={op.busy}>
                        Подтвердить отзыв
                      </Btn>
                    </details>
                  </form>
                )}
            </div>
          ))}
        </Card>
        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Поблагодарить коллегу</h2>
          <form
            className="space-y-3"
            onSubmit={(e) => {
              const v = values(e);
              const element = e.currentTarget;
              void op.run(async () => {
                await command("/thanks", {
                  recipient_id: v.recipient,
                  text: v.text,
                  requested_visibility: v.visibility,
                });
                element.reset();
              }, "Благодарность сохранена. Получатель выберет видимость.");
            }}
          >
            <select name="recipient" className={fieldClass} required>
              <option value="">Выберите коллегу</option>
              {options}
            </select>
            <textarea
              className={fieldClass}
              name="text"
              placeholder="За какой вклад вы благодарите?"
              aria-label="Текст благодарности"
              required
            />
            <select name="visibility" className={fieldClass}>
              <option value="private">Личная благодарность</option>
              <option value="organization">Предложить публикацию</option>
            </select>
            <Btn type="submit" variant="primary" disabled={op.busy}>
              Отправить
            </Btn>
          </form>
        </Card>
      </div>
      <Card className="space-y-4">
        <h2 className="text-[22px] font-bold">Программы признания</h2>
        {!campaigns.length && <p>Открытых программ пока нет.</p>}
        {campaigns.map((c) => (
          <div key={c.id} className="border-t pt-4 space-y-3">
            <div className="flex justify-between">
              <h3 className="text-xl font-bold">{c.title}</h3>
              <Badge>{names[c.status]}</Badge>
            </div>
            <p>{c.criteria}</p>
            <p>
              {c.starts_on} — {c.ends_on}
            </p>
            {c.status === "draft" && c.organizer_id === actor.id && (
              <Btn
                disabled={op.busy}
                onClick={() =>
                  void op.run(() =>
                    command(`/campaigns/${c.id}/open`, {
                      expected_revision: c.revision,
                    }),
                  )
                }
              >
                Открыть выдвижение
              </Btn>
            )}
            {c.status === "open" && (
              <form
                className="space-y-2"
                onSubmit={(e) => {
                  const v = values(e);
                  void op.run(
                    () =>
                      command(`/campaigns/${c.id}/nominations`, {
                        nominee_id: v.nominee,
                        statement: v.statement,
                      }),
                    "Коллега выдвинут. Для рассмотрения нужно его согласие.",
                  );
                }}
              >
                <select name="nominee" className={fieldClass} required>
                  <option value="">Кого выдвигаете?</option>
                  {options}
                </select>
                <textarea
                  name="statement"
                  className={fieldClass}
                  required
                  placeholder="Основание по критериям программы"
                  aria-label="Основание выдвижения"
                />
                <Btn type="submit" disabled={op.busy}>
                  Выдвинуть коллегу
                </Btn>
              </form>
            )}
          </div>
        ))}
      </Card>
      <Card className="space-y-4">
        <h2 className="text-[22px] font-bold">Мои номинации и решения</h2>
        {!nominations.length && <p>Номинаций пока нет.</p>}
        {nominations.map((n) => {
          const c = campaigns.find((c) => c.id === n.campaign_id);
          return (
            <div key={n.id} className="border-t pt-4 space-y-3">
              <strong>
                {c?.title} · {person(n.nominee_id)}
              </strong>
              <p>{n.statement}</p>
              <Badge>{names[n.status]}</Badge>
              {n.decision_reason && <p>{n.decision_reason}</p>}
              {n.nominee_id === actor.id && n.status === "awaiting_consent" && (
                <div className="flex gap-2">
                  {[true, false].map((accepted) => (
                    <Btn
                      key={String(accepted)}
                      disabled={op.busy}
                      onClick={() =>
                        void op.run(() =>
                          command(`/nominations/${n.id}/consent`, {
                            expected_revision: n.revision,
                            accepted,
                          }),
                        )
                      }
                    >
                      {accepted ? "Согласиться на участие" : "Отказаться"}
                    </Btn>
                  ))}
                </div>
              )}
              {c?.reviewer_actor_id === actor.id &&
                n.status === "submitted" && (
                  <form
                    className="space-y-2"
                    onSubmit={(e) => {
                      const v = values(e);
                      void op.run(() =>
                        command(`/nominations/${n.id}/decision`, {
                          expected_revision: n.revision,
                          result: v.result,
                          reason: v.reason,
                        }),
                      );
                    }}
                  >
                    <select name="result" className={fieldClass}>
                      <option value="selected">Выбрать</option>
                      <option value="not_selected">Не выбрать</option>
                    </select>
                    <textarea
                      name="reason"
                      className={fieldClass}
                      placeholder="Обоснование решения"
                      aria-label="Обоснование решения"
                      required
                    />
                    <Btn type="submit" disabled={op.busy}>
                      Подтвердить решение
                    </Btn>
                  </form>
                )}
              {n.nominee_id === actor.id && n.status === "selected" && (
                <div>
                  <p>
                    Публикация результата:{" "}
                    {n.publication_choice === "allowed"
                      ? "разрешена"
                      : n.publication_choice === "denied"
                        ? "запрещена"
                        : "ожидает вашего решения"}
                  </p>
                  <div className="flex gap-2 mt-2">
                    {[true, false].map((allowed) => (
                      <Btn
                        key={String(allowed)}
                        disabled={op.busy}
                        onClick={() =>
                          void op.run(() =>
                            command(`/nominations/${n.id}/publication`, {
                              expected_revision: n.revision,
                              allowed,
                            }),
                          )
                        }
                      >
                        {allowed ? "Разрешить публикацию" : "Не публиковать"}
                      </Btn>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </Card>
      {organizer && (
        <Card>
          <h2 className="text-xl font-bold mb-3">
            Создать программу признания
          </h2>
          <form
            className="grid grid-cols-2 gap-3"
            onSubmit={(e) => {
              const v = values(e);
              void op.run(() =>
                command("/campaigns", {
                  title: v.title,
                  criteria: v.criteria,
                  starts_on: v.starts,
                  ends_on: v.ends,
                  reviewer_actor_id: v.reviewer,
                }),
              );
            }}
          >
            <input
              className={fieldClass}
              name="title"
              placeholder="Название"
              aria-label="Название программы"
              required
            />
            <select className={fieldClass} name="reviewer" required>
              <option value="">Рассматривающий</option>
              {options}
            </select>
            <textarea
              className={fieldClass}
              name="criteria"
              placeholder="Критерии"
              aria-label="Критерии"
              required
            />
            <div>
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
            </div>
            <Btn type="submit" disabled={op.busy}>
              Создать черновик
            </Btn>
          </form>
        </Card>
      )}
    </>
  );
}
