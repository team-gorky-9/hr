import { useEffect, useState } from 'react';
import { developmentRequest } from '../../api/development';
import { useSession } from '../../api/session';
import { Card, Badge, Btn } from '../shared/ui';

type Program = {
  id: string;
  completed_count: number;
  total_count: number;
  status: 'active' | 'intro_completed' | 'cancelled';
  steps: { key: string; title: string; acknowledged_at: string | null }[];
};

export default function Workspace({ onNavigate }: { onNavigate: (tab: string) => void }) {
  const { session, loading, error: sessionError } = useSession();
  const token = session?.access_token;
  const [programs, setPrograms] = useState<Program[] | null>(null);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);

  useEffect(() => {
    setPrograms(null);
    setError('');
    if (!token) return;
    const controller = new AbortController();
    developmentRequest<{ items: Program[] }>(token, '/onboarding/programs', undefined, 'GET', controller.signal)
      .then(({ items }) => { if (!controller.signal.aborted) setPrograms(items); })
      .catch((failure) => { if (!controller.signal.aborted) setError(failure.message); });
    return () => controller.abort();
  }, [token, reload]);

  const current = programs?.filter((program) => program.status !== 'cancelled') ?? [];
  const sections = [
    { title: 'Опросы', tab: 'surveys', color: 'bg-[#F1EDFF]' },
    { title: 'Витрина вакансий', tab: 'vacancies', color: 'bg-[#E3F2E7]' },
    { title: 'Развитие', tab: 'development', color: 'bg-[#FFEFD9]' },
  ];

  return <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
    <div className="bg-[#1F4FD1] rounded-3xl p-8 text-white">
      <h1 className="text-[32px] font-bold">Рабочее пространство</h1>
    </div>
    <div className="grid md:grid-cols-3 gap-5">
      {sections.map(({ title, tab, color }) => <Card key={tab} className={color}>
        <Btn variant="link" onClick={() => onNavigate(tab)}>{title}</Btn>
      </Card>)}
    </div>
    <Card className="space-y-4">
      <h2 className="text-[22px] font-bold">Адаптация</h2>
      {(error || sessionError) && <p role="alert" className="text-[#A3171B]">{error || sessionError}</p>}
      {error && <Btn variant="link" onClick={() => setReload((value) => value + 1)}>Повторить</Btn>}
      {loading && <p>Проверяем вход…</p>}
      {!loading && !session && !sessionError && <p>Войдите в кабинет сотрудника, чтобы увидеть свои назначения.</p>}
      {session && !programs && !error && <p>Загружаем программы…</p>}
      {programs && !current.length && <p>Доступных программ адаптации пока нет.</p>}
      {current.map((program) => <div key={program.id} className="space-y-3 border-b border-[#E1E5EB] pb-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Badge tone={program.status === 'intro_completed' ? 'green' : 'blue'}>{program.completed_count} из {program.total_count}</Badge>
          <Btn variant="link" onClick={() => onNavigate('onboarding')}>Открыть программу</Btn>
        </div>
        <div role="progressbar" aria-label="Завершённые шаги" aria-valuenow={program.completed_count} aria-valuemin={0} aria-valuemax={program.total_count}
          className="h-2.5 rounded-full bg-[#E8ECF2]">
          <div className="h-full rounded-full bg-[#1F4FD1]" style={{ width: program.total_count ? 100 * program.completed_count / program.total_count + '%' : '0%' }} />
        </div>
        <ul className="space-y-2">
          {program.steps.map((step) => <li key={step.key} className="flex flex-wrap gap-2 items-center">
            <Badge tone={step.acknowledged_at ? 'green' : 'gray'}>{step.acknowledged_at ? 'Ознакомление подтверждено' : 'Ожидает подтверждения'}</Badge>
            {step.title}
          </li>)}
        </ul>
      </div>)}
    </Card>
  </div>;
}

