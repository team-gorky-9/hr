import { useEffect, useState } from 'react';
import { listPublicVacancies, type PublicVacancy } from '../../api/publicVacancies';

interface NewVacanciesSectionProps {
  onSelectVacancy?: (vacancyId: string) => void;
  catalog?: boolean;
  query?: string;
}

export function NewVacanciesSection({ onSelectVacancy, catalog = false, query = '' }: NewVacanciesSectionProps) {
  const [vacancies, setVacancies] = useState<PublicVacancy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [search, setSearch] = useState(query);

  useEffect(() => setSearch(query), [query]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    listPublicVacancies(controller.signal)
      .then((rows) => setVacancies(rows.slice().reverse()))
      .catch(() => { if (!controller.signal.aborted) setError('Каталог вакансий недоступен.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [reload]);

  const term = search.trim().toLocaleLowerCase('ru');
  const filtered = catalog
    ? vacancies.filter((vacancy) => [vacancy.title, vacancy.description, vacancy.employer || ''].some((value) => value.toLocaleLowerCase('ru').includes(term)))
    : vacancies.slice(0, 3);

  return (
    <section>
      <h2 className="text-[20px] font-bold text-[#141A24] mb-4">{catalog ? 'Вакансии' : 'Новые вакансии'}</h2>
      {catalog && (
        <div className="flex flex-wrap gap-3 mb-4">
          <input type="search" aria-label="Поиск по вакансиям" placeholder="Должность или навык" value={search} onChange={(event) => setSearch(event.target.value)} className="max-w-[28rem] flex-1 min-w-0 h-11 px-4 border border-[#E1E5EB] rounded-lg text-[14px]" />
          {search && <button type="button" className="text-[14px] font-semibold text-[#1F4FD1]" onClick={() => setSearch('')}>Сбросить поиск</button>}
        </div>
      )}
      {loading ? <p role="status">Загружаем вакансии…</p> : error ? (
        <div role="alert" className="bg-white border border-[#E1E5EB] rounded-2xl p-6">
          <p className="mb-3">{error}</p>
          <button type="button" className="text-[#1F4FD1] font-semibold" onClick={() => setReload((current) => current + 1)}>Повторить</button>
        </div>
      ) : !filtered.length ? (
        <p className="bg-white border border-[#E1E5EB] rounded-2xl p-6 text-[#616977]">
          {term && vacancies.length ? 'По этому запросу вакансий нет.' : 'Сейчас нет опубликованных вакансий.'}
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {filtered.map((vacancy) => (
            <button key={vacancy.id} type="button" onClick={() => onSelectVacancy?.(vacancy.id)} className="text-left bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm flex flex-col justify-between hover:shadow-md transition-shadow">
              <div className="min-w-0">
                {vacancy.is_synthetic && <span className="inline-block mb-2 px-2.5 py-1 rounded-md text-[12px] font-medium bg-[#EEF3FE] text-[#1F4FD1]">Учебная вакансия</span>}
                <h3 className="text-[18px] font-bold text-[#141A24] mb-1.5 break-words">{vacancy.title}</h3>
                <p className="text-[13px] text-[#616977] mb-6 line-clamp-3 break-words">{vacancy.description || vacancy.employer}</p>
              </div>
              <span className="text-[14px] font-semibold text-[#1F4FD1]">Подробнее →</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

export default NewVacanciesSection;
