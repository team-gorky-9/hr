import React, { useEffect, useState } from "react";
import { publicVacancies } from "../../api/portal";

export interface PortalSearchFilters {
  query: string;
  department: string;
  district: string;
}

interface HeroSectionProps {
  filters?: PortalSearchFilters;
  onFiltersChange?: (next: PortalSearchFilters) => void;
  onSearch?: () => void;
}

export const HeroSection: React.FC<HeroSectionProps> = ({
  filters = { query: "", department: "", district: "" },
  onFiltersChange,
  onSearch,
}) => {
  const [departments, setDepartments] = useState<[string, string][]>([]);
  useEffect(() => {
    const controller = new AbortController();
    publicVacancies(controller.signal)
      .then((items) =>
        setDepartments([
          ...new Map(
            items
              .filter((v) => v.department_name)
              .map(
                (v) =>
                  [v.department_id, v.department_name!] as [string, string],
              ),
          ).entries(),
        ]),
      )
      .catch(() => {
        /* Catalog displays its load error and retry. */
      });
    return () => controller.abort();
  }, []);
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch?.();
  };

  return (
    <section className="bg-[#1F4FD1] rounded-2xl p-8 lg:p-12 text-white shadow-sm">
      {/* Title */}
      <h1 className="text-[32px] sm:text-[38px] font-bold tracking-tight mb-3">
        Работа, которая меняет город
      </h1>

      {/* Subtitle */}
      <p className="text-[15px] sm:text-[16px] text-white/90 max-w-3xl mb-8 leading-relaxed">
        Вакансии администрации, практика для студентов и кадровый резерв в одном
        месте. Откликнуться можно за пару минут.
      </p>

      {/* Search Bar Card */}
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-xl p-2.5 shadow-md flex flex-col md:flex-row items-stretch md:items-center gap-2.5 text-[#141A24]"
      >
        {/* Job Title / Skill Input */}
        <div className="flex-1">
          <input
            type="text"
            value={filters.query}
            onChange={(e) =>
              onFiltersChange?.({ ...filters, query: e.target.value })
            }
            placeholder="Должность или навык"
            className="w-full h-11 px-4 text-[14px] bg-white border border-[#E1E5EB] rounded-lg text-[#141A24] placeholder-[#8E939D] focus:outline-none focus:border-[#1F4FD1]"
          />
        </div>

        {/* Departments Select */}
        <div className="relative md:w-56">
          <select
            aria-label="Департамент"
            disabled={!departments.length}
            value={filters.department}
            onChange={(e) =>
              onFiltersChange?.({ ...filters, department: e.target.value })
            }
            className="w-full h-11 pl-4 pr-10 text-[14px] bg-white border border-[#E1E5EB] rounded-lg text-[#141A24] appearance-none cursor-pointer focus:outline-none focus:border-[#1F4FD1]"
          >
            <option value="">Все департаменты</option>
            {departments.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
          <img
            src="/icons/chevron-down.svg"
            alt=""
            className="w-4 h-4 opacity-70 pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2"
          />
        </div>

        {/* Districts Select */}
        <div className="relative md:w-48">
          <select
            aria-label="Район"
            disabled
            title="Районы не указаны в опубликованных вакансиях"
            value={filters.district}
            onChange={(e) =>
              onFiltersChange?.({ ...filters, district: e.target.value })
            }
            className="w-full h-11 pl-4 pr-10 text-[14px] bg-white border border-[#E1E5EB] rounded-lg text-[#141A24] appearance-none cursor-pointer focus:outline-none focus:border-[#1F4FD1]"
          >
            <option value="">Все районы</option>
          </select>
          <img
            src="/icons/chevron-down.svg"
            alt=""
            className="w-4 h-4 opacity-70 pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2"
          />
        </div>

        {/* Search Button */}
        <button
          type="submit"
          className="h-11 px-7 bg-[#1F4FD1] hover:bg-[#1841B2] text-white text-[14px] font-medium rounded-lg transition-colors whitespace-nowrap shadow-sm"
        >
          Найти вакансии
        </button>
      </form>
    </section>
  );
};

export default HeroSection;
