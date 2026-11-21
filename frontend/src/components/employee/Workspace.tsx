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
  const [later, setLater] = useState<'documents' | 'mentor' | null>(null);

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
    { title: 'Опросы', description: 'Открытые опросы и опубликованные итоги', tab: 'surveys', icon: '🛡', color: 'bg-[#F1EDFF]' },
    { title: 'Забота и мотивация', description: 'Поддержка, мероприятия и обучение', tab: 'care', icon: '🏅', color: 'bg-[#FFEFD9]' },
    { title: 'Витрина вакансий', description: 'Опубликованные вакансии', tab: 'vacancies', icon: '💼', color: 'bg-[#E3F2E7]' },
  ];

  return <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
    <div className="bg-[#1F4FD1] rounded-3xl p-8 text-white flex flex-wrap items-center justify-between gap-5">
      <div><h1 className="text-[32px] font-bold">Рабочее пространство</h1><p className="mt-2 text-[18px] text-[#DCE5FB]">Адаптация, документы и помощь сотруднику</p></div>
      {current[0] && <div className="bg-white/15 rounded-2xl px-5 py-4">
        <p className="text-[28px] font-bold">{current[0].completed_count} из {current[0].total_count}</p>
        <p className="text-[15px] text-[#DCE5FB]">Шаги адаптации</p>
      </div>}
    </div>
    <div className="grid md:grid-cols-3 gap-5">
      {sections.map(({ title, description, tab, icon, color }) => <Card key={tab} className="space-y-3">
        <div className="flex items-center gap-4">
          <div aria-hidden="true" className={color + ' w-[52px] h-[52px] shrink-0 rounded-xl grid place-items-center text-[22px]'}>{icon}</div>
          <div><h2 className="text-[18px] font-bold">{title}</h2><p className="text-[15px] text-[#4A5363]">{description}</p></div>
        </div>
        <Btn variant="link" onClick={() => onNavigate(tab)}>Открыть: {title}</Btn>
      </Card>)}
    </div>
    <div className="grid lg:grid-cols-[2fr_1fr] gap-5 items-start">
      <div className="space-y-5">
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
        <Card className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-[22px] font-bold">Единое окно: мои документы</h2>
            <Btn variant="primary" onClick={() => setLater('documents')}>Подать документ</Btn>
          </div>
          <Badge>Примеры документов</Badge>
          <div className="border-t border-[#E1E5EB] pt-3 flex flex-wrap items-center justify-between gap-3">
            <span>Справка с места работы</span><Btn variant="link" onClick={() => setLater('documents')}>Скачать</Btn>
          </div>
          <div className="border-t border-[#E1E5EB] pt-3 flex flex-wrap items-center justify-between gap-3">
            <span>Заявление на отпуск</span><Btn variant="link" onClick={() => setLater('documents')}>Подробнее</Btn>
          </div>
          {later === 'documents' && <p role="status" className="text-[14px] font-semibold text-[#4A5363]">Будет добавлено позже</p>}
        </Card>
      </div>
      <div className="space-y-5">
        <Card className="space-y-4">
          <h2 className="text-[22px] font-bold">Мой наставник</h2>
          <div className="flex items-center gap-3">
            <div aria-hidden="true" className="w-[52px] h-[52px] shrink-0 rounded-full bg-[#E8EEFC] text-[#1F4FD1] grid place-items-center font-bold">ОП</div>
            <div><p className="text-[18px] font-bold">Ольга Петрова</p><p className="text-[14px] text-[#4A5363]">Пример карточки наставника</p></div>
          </div>
          <Btn onClick={() => setLater('mentor')}>Написать наставнику</Btn>
          {later === 'mentor' && <p role="status" className="text-[14px] font-semibold text-[#4A5363]">Будет добавлено позже</p>}
        </Card>
        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Развитие</h2>
          <Btn variant="link" onClick={() => onNavigate('development')}>Открыть цели и планы</Btn>
        </Card>
      </div>
    </div>
  </div>;
}

