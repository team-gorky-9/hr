import { useEffect, useState, type ReactNode, type FormEvent } from "react";
import { Btn, Card } from "../shared/ui";
import { serviceRequest, type Actor, type ServiceName } from "./service";
export const fieldClass =
  "block w-full rounded-xl border border-[#C9D0DB] bg-white px-4 py-3 text-[16px]";
export function EmployeeServiceAccess({
  service,
  children,
}: {
  service: ServiceName;
  children: (token: string, actor: Actor) => ReactNode;
}) {
  const key = "employee-session-" + service;
  const [token, setToken] = useState(() => sessionStorage.getItem(key) || "");
  const [actor, setActor] = useState<Actor | null>(null);
  const [login, setLogin] = useState(
    service === "mobility" ? "employee" : "alice",
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function enter(candidate: string) {
    setBusy(true);
    setError("");
    try {
      const a = await serviceRequest<Actor>(service, candidate, "/session");
      setActor(a);
      setToken(candidate);
      sessionStorage.setItem(key, candidate);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка входа");
      sessionStorage.removeItem(key);
      setToken("");
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (token) void enter(token);
  }, []);
  if (actor)
    return (
      <>
        <div className="max-w-[1240px] mx-auto px-6 pt-4 flex items-center justify-between">
          <span>Учебная учётная запись: {actor.name || actor.login}</span>
          <Btn
            onClick={() => {
              sessionStorage.removeItem(key);
              setActor(null);
              setToken("");
            }}
          >
            Сменить пользователя
          </Btn>
        </div>
        {children(token, actor)}
      </>
    );
  return (
    <div className="max-w-[1240px] mx-auto p-6">
      <Card className="max-w-[520px] space-y-4">
        <h2 className="text-[22px] font-bold">Вход в раздел сотрудника</h2>
        <p className="text-[#4A5363]">
          Этот сервис пока использует отдельные учебные учётные записи. Действия
          сохраняются на сервере.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void enter(
              service === "mobility" ? "fixture:" + login : "demo-" + login,
            );
          }}
          className="space-y-3"
        >
          <label>
            Учётная запись
            <select
              className={fieldClass}
              value={login}
              onChange={(e) => setLogin(e.target.value)}
            >
              {(service === "mobility"
                ? ["employee", "owner", "manager", "hr"]
                : service === "recognition"
                  ? ["alice", "bob", "organizer", "moderator", "reviewer"]
                  : ["alice", "bob", "organizer", "manager", "recipient"]
              ).map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
          <Btn type="submit" variant="primary" disabled={busy}>
            Войти
          </Btn>
        </form>
        {error && (
          <p role="alert" className="text-red-700">
            {error}
          </p>
        )}
      </Card>
    </div>
  );
}
export function useOperation() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  async function run(action: () => Promise<void>, success = "") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(success);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Не удалось выполнить действие",
      );
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, notice, run };
}
export function Status({ error, notice }: { error: string; notice: string }) {
  return (
    <>
      {error && (
        <Card>
          <p role="alert" className="text-red-700">
            {error}
          </p>
        </Card>
      )}
      {notice && (
        <Card>
          <p role="status" className="text-green-800">
            {notice}
          </p>
        </Card>
      )}
    </>
  );
}

export function values(e: FormEvent<HTMLFormElement>) {
  e.preventDefault();
  return Object.fromEntries(new FormData(e.currentTarget)) as Record<
    string,
    string
  >;
}
