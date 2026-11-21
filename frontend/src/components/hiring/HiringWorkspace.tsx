import { useCallback, useState } from 'react';
import { PageTitle, Btn, Card } from '../shared/ui';
import { hiringToken, type Audience } from '../../api/hiring';
import { Requests } from './Requests';
import { Cases } from './Cases';
export function HiringWorkspace({ audience = 'staff', token, initialRequestId }: { audience?: Audience; token?: string; initialRequestId?: string }) {
  const [tab, setTab] = useState<'requests' | 'cases'>('requests'), [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const auth = hiringToken(audience, token);
  const run = useCallback(async (action: () => Promise<void>) => {
    setBusy(true); setError(null);
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось выполнить действие.'); throw e; }
    finally { setBusy(false); }
  }, []);
  return <div className={audience === 'staff' ? 'max-w-[1240px] mx-auto px-4 sm:px-6 py-6 w-full min-w-0 space-y-6' : 'min-w-0 space-y-6'}><PageTitle title={audience === 'candidate' ? 'Мои отклики' : 'Оформление и обращения'} subtitle={audience === 'candidate' ? 'Ваши обращения, документы и следующие шаги' : 'От обращения кандидата до подтверждённого начала работы'} />
    {auth.startsWith('fixture:') && <p className="text-sm text-[#616977]">Учебный вход Hiring: {audience === 'candidate' ? 'кандидат' : 'кадровик'}. Данные читаются и сохраняются в сервисе. Каталог вакансий — учебный снимок.</p>}
    <div className="flex gap-3"><Btn variant={tab === 'requests' ? 'primary' : 'secondary'} onClick={() => setTab('requests')}>Обращения</Btn><Btn variant={tab === 'cases' ? 'primary' : 'secondary'} onClick={() => setTab('cases')}>Оформление</Btn></div>
    {error && <Card className="!bg-[#FCE8E8] !border-[#F3B8B8]"><p role="alert" className="text-[#A3171B]">{error}</p><p className="text-sm mt-2">Введённые данные сохранены в форме. Обновите список для перечитывания серверного состояния.</p></Card>}
    {busy && <p role="status" className="text-sm text-[#616977]">Обращаемся к сервису…</p>}
    {tab === 'requests' ? <Requests key={auth} token={auth} audience={audience} busy={busy} run={run} initialRequestId={initialRequestId} /> : <Cases key={auth} token={auth} audience={audience} busy={busy} run={run} />}
  </div>;
}
export function CandidateCabinet({ token }: { token?: string }) { return <HiringWorkspace audience="candidate" token={token} />; }
export default HiringWorkspace;

