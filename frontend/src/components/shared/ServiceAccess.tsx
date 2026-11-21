import { useState, type ReactNode } from 'react';
import { Card, Btn } from './ui';
import { loginSession, logoutSession, useSession } from '../../api/session';

export default function ServiceAccess({ children, initialLogin = 'hr', allowedRoles }: {
  children: (token: string, role: string) => ReactNode;
  initialLogin?: string;
  allowedRoles?: string[];
}) {
  const { session, loading, error: sessionError, refresh } = useSession();
  const [login, setLogin] = useState(initialLogin);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (loading) return <Card>Проверяем вход…</Card>;
  if (session) {
    if (allowedRoles && !session.actor.grants.some(grant => allowedRoles.includes(grant.role))) {
      return <Card><p>У текущей учётной записи нет доступа к этому разделу.</p><Btn onClick={async () => { try { await logoutSession(); } catch (e) { setError(String(e)); } }}>Сменить учётную запись</Btn>{error && <p role="alert">{error}</p>}</Card>;
    }
    return <>{children(session.access_token, session.actor.login)}</>;
  }
  return <div className="max-w-[1240px] mx-auto p-6"><Card className="max-w-[520px]">
    <h2 className="text-[20px] font-bold mb-3">Вход в личный кабинет</h2>
    <form className="space-y-3" onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError('');
      try { await loginSession(login, password); } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось войти.'); } finally { setBusy(false); }
    }}>
      <label className="block">Логин<select className="block w-full border rounded-lg p-2" value={login} onChange={event => setLogin(event.target.value)}>{['candidate', 'hr', 'department', 'employee', 'admin'].map(value => <option key={value}>{value}</option>)}</select></label>
      <label className="block">Пароль<input autoComplete="current-password" className="block w-full border rounded-lg p-2" type="password" value={password} onChange={event => setPassword(event.target.value)} required /></label>
      <Btn type="submit" variant="primary" disabled={busy}>{busy ? 'Входим…' : 'Войти'}</Btn>
      {(error || sessionError) && <p role="alert" className="text-red-700">{error || sessionError}</p>}
      {sessionError && <Btn onClick={() => void refresh()}>Повторить проверку входа</Btn>}
    </form>
  </Card></div>;
}
