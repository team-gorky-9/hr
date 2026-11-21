import React, { useEffect, useState } from "react";
import { publicVacancies, type PublicVacancy } from "../../api/portal";
import type { PortalSearchFilters } from "./HeroSection";

interface NewVacanciesSectionProps {
  filters?: PortalSearchFilters;
  onResetFilters?: () => void;
  onSelectVacancy?: (vacancyId: string) => void;
}

export const NewVacanciesSection: React.FC<NewVacanciesSectionProps> = ({
  filters,
  onResetFilters,
  onSelectVacancy,
}) => {
  const [vacancies, setVacancies] = useState<PublicVacancy[]>([]);
  const [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    publicVacancies(controller.signal)
      .then(setVacancies)
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "Ошибка загрузки");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [refresh]);

  const q = (filters?.query || "").trim().toLowerCase();
  const filteredVacancies = vacancies.filter((v) => {
    if (filters?.department && v.department_id !== filters.department)
      return false;
    if (q) {
      const hay =
        `${v.title} ${v.description} ${v.position_code}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const hasActiveFilters = Boolean(
    q || filters?.department || filters?.district,
  );

  return (
    <section id="new-vacancies" className="scroll-mt-24">
      <div className="flex items-center justify-between gap-4 mb-4">
        <h2 className="text-[20px] font-bold text-[#141A24]">Новые вакансии</h2>
        {hasActiveFilters && onResetFilters && (
          <button
            type="button"
            onClick={onResetFilters}
            className="text-[13px] font-medium text-[#1F4FD1] hover:underline"
          >
            Сбросить фильтры
          </button>
        )}
      </div>

      {loading ? (
        <p className="text-[#616977] p-6" role="status">
          Загружаем вакансии…
        </p>
      ) : error ? (
        <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6">
          <p role="alert">{error}</p>
          <button
            className="text-[#1F4FD1] mt-3"
            onClick={() => setRefresh((x) => x + 1)}
          >
            Повторить
          </button>
        </div>
      ) : filteredVacancies.length === 0 ? (
        <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 text-center space-y-3">
          <p className="text-[14px] text-[#616977]">
            По выбранным параметрам вакансий не найдено.
          </p>
          {onResetFilters && (
            <button
              type="button"
              onClick={onResetFilters}
              className="px-4 py-2 text-[13px] font-medium text-[#1F4FD1] bg-[#EEF3FE] rounded-lg hover:bg-[#DCE7FD] transition-colors"
            >
              Показать все вакансии
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {filteredVacancies.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => onSelectVacancy?.(v.id)}
              className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm flex flex-col justify-between text-left hover:shadow-md transition-shadow cursor-pointer"
            >
              <div>
                {/* Badges */}
                <div className="flex flex-wrap items-center gap-2 mb-3">
                  <span className="px-2.5 py-1 rounded-md text-[12px] font-medium bg-[#EEF3FE] text-[#1F4FD1]">
                    {v.department_name || "Открытая вакансия"}
                  </span>
                </div>

                {/* Title */}
                <h3 className="text-[18px] font-bold text-[#141A24] mb-1.5">
                  {v.title}
                </h3>

                {/* Experience / Description */}
                <p className="text-[13px] text-[#616977] mb-6">
                  {v.description}
                </p>
              </div>

              {/* Salary */}
              <div className="text-[16px] font-bold text-[#141A24]">
                Опубликовано{" "}
                {new Date(v.published_at).toLocaleDateString("ru-RU")}
              </div>
            </button>
          ))}
        </div>
      )}
    </section>
  );
};

export default NewVacanciesSection;
