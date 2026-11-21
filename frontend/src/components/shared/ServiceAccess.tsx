import { useEffect, type ReactNode } from 'react';
import { Card, Btn } from './ui';
import { selectDemoRole, useSession } from '../../api/session';

type DemoLogin = 'candidate' | 'hr' | 'department' | 'employee';

export default function ServiceAccess({ children, initialLogin = 'hr', allowedRoles }: {
  children: (token: string, role: string) => ReactNode;
  initialLogin?: DemoLogin;
  allowedRoles?: string[];
}) {
  const { session, loading, error: sessionError, refresh } = useSession();

  useEffect(() => {
    if (!loading && !session && !sessionError) {
      void selectDemoRole(initialLogin).catch(() => {});
    }
  }, [loading, session, sessionError, initialLogin]);

  if (loading) return <Card>Открываем выбранную роль…</Card>;
  if (session) {
    if (allowedRoles && !session.actor.grants.some(grant => allowedRoles.includes(grant.role))) {
      return <Card><p>У текущей роли нет доступа к этому разделу. Выберите нужную роль в верхней панели.</p></Card>;
    }
    return <>{children(session.access_token, session.actor.login)}</>;
  }
  return <div className="max-w-[1240px] mx-auto p-6"><Card className="max-w-[520px] space-y-3">
    <p>{sessionError || 'Открываем выбранную роль…'}</p>
    {sessionError && <Btn onClick={() => void selectDemoRole(initialLogin).catch(() => void refresh())}>Повторить</Btn>}
  </Card></div>;
}
