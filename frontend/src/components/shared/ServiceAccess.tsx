import { useEffect, useState, type ReactNode } from "react";
import { Card, Btn } from "./ui";
import {
  developmentRequest,
  type Actor,
  type Session,
} from "../../api/development";
import {
  endSession,
  restoreSession,
  saveSession,
  sessionChanged,
  sessionToken,
} from "../../api/session";

export default function ServiceAccess({
  children,
  initialLogin = "hr",
  requiredRoles,
}: {
  children: (token: string, role: string, actor: Actor) => ReactNode;
  initialLogin?: string;
  requiredRoles?: string[];
}) {
  const [session, setSession] = useState<Session | null>(null);
  const [login, setLogin] = useState(initialLogin);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [restoring, setRestoring] = useState(true);
  useEffect(() => {
    let active = true;
    let generation = 0;
    const changed = () => {
      const current = ++generation;
      if (!sessionToken()) {
        setSession(null);
        setRestoring(false);
        return;
      }
      setRestoring(true);
      restoreSession()
        .then((s) => {
          if (active && current === generation) setSession(s);
        })
        .catch((e) => {
          if (active && current === generation) {
            setSession(null);
            setError(
              e instanceof Error ? e.message : "Не удалось проверить вход.",
            );
          }
        })
        .finally(() => {
          if (active && current === generation) setRestoring(false);
        });
    };
    changed();
    window.addEventListener(sessionChanged, changed);
    return () => {
      active = false;
      window.removeEventListener(sessionChanged, changed);
    };
  }, []);
  if (restoring)
    return (
      <p role="status" className="max-w-[1240px] mx-auto p-6">
        Проверяем вход…
      </p>
    );
  if (session)
    return (
      <>
        <div className="max-w-[1240px] mx-auto px-6 pt-4 flex gap-4 items-center">
          <span>{session.actor.login}</span>
          <Btn
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                await endSession(session.access_token);
                setSession(null);
              } catch (e) {
                setError(
                  e instanceof Error
                    ? e.message
                    : "Не удалось завершить сеанс.",
                );
              } finally {
                setBusy(false);
              }
            }}
          >
            Сменить пользователя
          </Btn>
          {error && (
            <p role="alert" className="text-red-700">
              {error}
            </p>
          )}
        </div>
        {requiredRoles &&
        !session.actor.grants.some((grant) =>
          requiredRoles.includes(grant.role),
        ) ? (
          <div className="max-w-[1240px] mx-auto p-6">
            <Card>
              <p role="alert">
                У текущей учётной записи нет роли для этого раздела. Смените
                пользователя.
              </p>
            </Card>
          </div>
        ) : (
          children(session.access_token, session.actor.login, session.actor)
        )}
      </>
    );
  return (
    <div className="max-w-[1240px] mx-auto p-6">
      <Card className="max-w-[520px]">
        <h2 className="text-[20px] font-bold mb-3">Вход в рабочий раздел</h2>
        <p className="text-[#4A5363] mb-4">
          Используйте свою учётную запись. Доступ определяется назначенными
          правами.
        </p>
        <form
          className="space-y-3"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              const next = await developmentRequest<Session>(
                null,
                "/sessions",
                { login: login.trim(), password },
              );
              saveSession(next);
              setSession(next);
              setPassword("");
            } catch (e) {
              setError(e instanceof Error ? e.message : "Ошибка входа");
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="block">
            Логин
            <input
              required
              autoComplete="username"
              className="block w-full border rounded-lg p-2"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
            />
          </label>
          <label className="block">
            Пароль
            <input
              required
              autoComplete="current-password"
              className="block w-full border rounded-lg p-2"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <Btn type="submit" disabled={busy} variant="primary">
            {busy ? "Входим…" : "Войти"}
          </Btn>
          {error && (
            <p role="alert" className="text-red-700">
              {error}
            </p>
          )}
        </form>
      </Card>
    </div>
  );
}
