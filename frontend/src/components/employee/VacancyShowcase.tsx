import { useEffect, useState } from 'react';
import { listPublicVacancies, type PublicVacancy } from '../../api/publicVacancies';
import { Badge, Btn, Card, PageTitle } from '../shared/ui';

export default function VacancyShowcase() {
  const [vacancies, setVacancies] = useState<PublicVacancy[] | null>(null);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError('');
    setVacancies(null);
    listPublicVacancies(controller.signal)
      .then((items) => { if (!controller.signal.aborted) setVacancies(items); })
      .catch((failure) => { if (!controller.signal.aborted) setError(failure.message); });
    return () => controller.abort();
  }, [reload]);

  return <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
    <PageTitle title="Витрина вакансий" subtitle="Опубликованные вакансии. Запрос на внутренний переход здесь пока недоступен." />
    {error && <Card><p role="alert" className="text-[#A3171B]">{error}</p><Btn variant="link" onClick={() => setReload((value) => value + 1)}>Повторить</Btn></Card>}
    {!vacancies && !error && <Card>Загружаем вакансии…</Card>}
    {vacancies?.length === 0 && <Card>Опубликованных вакансий пока нет.</Card>}
    {vacancies?.map((vacancy) => <Card key={vacancy.id}>
      <details>
        <summary className="cursor-pointer text-[20px] font-bold">{vacancy.title}</summary>
        <div className="space-y-3 pt-3">
          <div className="flex flex-wrap items-center gap-2">
            {vacancy.is_synthetic && <Badge tone="amber">Учебная вакансия</Badge>}
            {vacancy.published_at && <Badge tone="blue">Опубликовано {new Date(vacancy.published_at).toLocaleDateString('ru-RU')}</Badge>}
          </div>
          {vacancy.employer && <p className="text-[#4A5363]">{vacancy.employer}</p>}
          {vacancy.description && <p className="whitespace-pre-wrap break-words">{vacancy.description}</p>}
        </div>
      </details>
    </Card>)}
  </div>;
}

