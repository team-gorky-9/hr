import { useEffect, useSyncExternalStore } from 'react';
import { developmentRequest, type Actor, type Session } from './development';
const key = 'workforce-access-token';
const env = (import.meta as ImportMeta & { env: Record<string, string> }).env;
export const demoRolesEnabled = env.VITE_DEMO_ROLES !== 'false';
const base = env.VITE_DEVELOPMENT_API_BASE || '/workforce-api';
type State = { session: Session | null; loading: boolean; error: string };
let state: State = { session: null, loading: Boolean(sessionStorage.getItem(key)), error: '' };
let initialized = false;
let pending: Promise<void> | null = null;
let generation = 0;
const listeners = new Set<() => void>();
function publish(next: State) { state = next; listeners.forEach(listener => listener()); }
function subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; }
export function refreshSession(): Promise<void> {
  if (pending) return pending;
  initialized = true;
  const token = sessionStorage.getItem(key);
  if (!token) { publish({ session: null, loading: false, error: '' }); return Promise.resolve(); }
  const revision = generation;
  publish({ ...state, loading: true, error: '' });
  pending = (async () => {
    try {
      const response = await fetch(base + '/session', { headers: { Authorization: `Bearer ${token}` } });
      if (revision !== generation) return;
      if (response.status === 401) {
        sessionStorage.removeItem(key);
        publish({ session: null, loading: false, error: 'Сессия завершилась. Войдите снова.' });
        return;
      }
      if (!response.ok) throw new Error('Не удалось проверить вход. Повторите запрос.');
      const actor: Actor = await response.json();
      if (revision === generation) publish({ session: { access_token: token, actor }, loading: false, error: '' });
    } catch (error) {
      if (revision === generation) publish({ session: null, loading: false, error: error instanceof Error ? error.message : 'Нет связи с сервисом входа.' });
    } finally { pending = null; }
  })();
  return pending;
}
export async function loginSession(login: string, password: string): Promise<Session> {
  const revision = ++generation;
  const session = await developmentRequest<Session>(null, '/sessions', { login, password });
  if (revision !== generation) return session;
  initialized = true;
  sessionStorage.setItem(key, session.access_token);
  publish({ session, loading: false, error: '' });
  return session;
}
export function selectDemoRole(login: 'candidate' | 'hr' | 'department' | 'employee') {
  if (!demoRolesEnabled) return Promise.reject(new Error('Учебное переключение ролей выключено.'));
  // These are the public, synthetic stand accounts from fixtures/wave-1/actors.json.
  // The backend still validates the session and every operation's scope.
  if (state.session?.actor.login === login) return Promise.resolve(state.session);
  return loginSession(login, '123');
}
export async function logoutSession(): Promise<void> {
  const token = sessionStorage.getItem(key);
  if (token) {
    const response = await fetch(base + '/session', { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok && response.status !== 401) throw new Error('Не удалось завершить сессию. Повторите выход.');
  }
  generation += 1;
  sessionStorage.removeItem(key);
  publish({ session: null, loading: false, error: '' });
}
export function useSession() {
  const snapshot = useSyncExternalStore(subscribe, () => state);
  useEffect(() => { if (!initialized) void refreshSession(); }, []);
  return { ...snapshot, refresh: refreshSession };
}
