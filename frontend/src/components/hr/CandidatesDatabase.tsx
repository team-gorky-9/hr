import { CandidateUpload } from "./CandidateUpload";
import React, { useEffect, useState } from "react";
import {
  databaseCandidates,
  errorMessage,
  resultLabel,
} from "../../api/recruitment";

export interface CandidateRecord {
  id: string;
  name: string;
  type: string;
  source: string;
  vacancy: string;
  match: "Нужно уточнить" | "Выполнено" | "Не выполнено" | "Не оценено";
  status: string;
  stageDays: number | null;
  isOverdue?: boolean;
}

interface CandidatesDatabaseProps {
  onSelectCandidate?: (candidate: CandidateRecord) => void;
  onUploadResume?: () => void;
}

export const CandidatesDatabase: React.FC<CandidatesDatabaseProps> = ({
  onSelectCandidate,
  onUploadResume: _onUploadResume,
}) => {
  const [activeTypeFilter, setActiveTypeFilter] = useState<string>("Все");
  const [isSourcesOpen, setIsSourcesOpen] = useState(false);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [candidates, setCandidates] = useState<CandidateRecord[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0),
    [total, setTotal] = useState(0);
  const [showUpload, setShowUpload] = useState(false),
    [notice, setNotice] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const timer = setTimeout(() => {
      databaseCandidates(search, offset, controller.signal)
        .then((page) => {
          if (controller.signal.aborted) return;
          const rows = page.items.map((row) => ({
            id: row.application_id,
            name:
              row.candidate_code + (row.headline ? " · " + row.headline : ""),
            type:
              (
                {
                  response: "Внешний отклик",
                  history: "Прежнее рассмотрение",
                  manual: "Добавлен кадровиком",
                } as Record<string, string>
              )[row.source] || row.source,
            source:
              (
                {
                  hh_ru: "HH.ru",
                  internal: "Внутренний",
                  rabota_rossii: "Работа России",
                  city_site: "Сайт администрации",
                  email: "Электронная почта",
                  citizen_appeal: "Обращение гражданина",
                  internship: "Практика",
                  other: "Другой источник",
                } as Record<string, string>
              )[row.channel] || row.channel,
            vacancy: row.vacancy_title,
            match: resultLabel(row.formal_result) as CandidateRecord["match"],
            status: row.stage_title,
            stageDays: row.stage_days,
          }));
          setCandidates(rows);
          setTotal(page.total);
          setSelectedSources([...new Set(rows.map((row) => row.source))]);
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(errorMessage(e));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [reload, search, offset]);
  const allSources = [...new Set(candidates.map((row) => row.source))];
  const typeTabs = [
    { label: "Все", count: candidates.length },
    ...[...new Set(candidates.map((row) => row.type))].map((type) => ({
      label: type,
      count: candidates.filter((row) => row.type === type).length,
    })),
  ];

  const toggleSource = (source: string) => {
    setSelectedSources((prev) =>
      prev.includes(source)
        ? prev.filter((s) => s !== source)
        : [...prev, source],
    );
  };

  const filteredCandidates = candidates.filter((c) => {
    if (activeTypeFilter !== "Все" && c.type !== activeTypeFilter) return false;
    return selectedSources.includes(c.source);
  });

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8">
      {/* Page Title & Action */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-[26px] font-bold text-[#141A24] tracking-tight mb-1">
            Единая база кандидатов
          </h1>
          <p className="text-[14px] text-[#616977]">
            Все сохранённые рассмотрения: отклики, прежняя история и записи
            кадровика. Одна строка — одно рассмотрение.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowUpload(true)}
          className="shrink-0 px-5 py-2.5 text-[14px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm whitespace-nowrap"
        >
          Загрузить резюме
        </button>
      </div>

      <div className="flex gap-3 mb-4">
        <input
          aria-label="Поиск кандидатов"
          placeholder="Код, заголовок резюме или вакансия"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
          className="border border-[#E1E5EB] rounded-lg px-4 py-2 flex-1"
        />
        <button
          className="text-[#1F4FD1]"
          onClick={() => setReload((value) => value + 1)}
        >
          Обновить
        </button>
      </div>
      {loading && (
        <p role="status" className="mb-4">
          Загружаем кандидатов…
        </p>
      )}
      {error && (
        <p role="alert" className="mb-4 text-red-700">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="mb-4 text-green-800">
          {notice}
        </p>
      )}
      <p className="text-sm text-[#616977] mb-3">
        Найдено рассмотрений: {total}. Фильтры типа и источника относятся к
        текущей странице.
      </p>
      {/* Type Filter Pills (Row 1) */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {typeTabs.map((tab) => {
          const isActive = activeTypeFilter === tab.label;
          return (
            <button
              key={tab.label}
              type="button"
              onClick={() => setActiveTypeFilter(tab.label)}
              className={`px-4 py-1.5 rounded-full text-[13px] font-medium transition-colors whitespace-nowrap ${
                isActive
                  ? "bg-[#1F4FD1] text-white shadow-sm"
                  : "bg-white text-[#141A24] border border-[#E1E5EB] hover:bg-[#F3F5F8]"
              }`}
            >
              {tab.label} · {tab.count}
            </button>
          );
        })}
      </div>

      {/* Source Sub-filters (Row 2, matches Screen 1 and 1a) */}
      <div className="mb-6">
        <div className="flex flex-wrap items-center gap-3 text-[13px]">
          <button
            type="button"
            onClick={() => setIsSourcesOpen(!isSourcesOpen)}
            className="px-3.5 py-1.5 bg-white border border-[#E1E5EB] rounded-lg text-[#141A24] font-medium hover:bg-[#F3F5F8] transition-colors flex items-center gap-2 whitespace-nowrap shadow-xs"
          >
            <span>
              Источники:{" "}
              {selectedSources.length === allSources.length
                ? `все (${allSources.length})`
                : `${selectedSources.length} из ${allSources.length}`}
            </span>
            <span className="text-[10px] text-[#616977]">
              {isSourcesOpen ? "▲" : "▼"}
            </span>
          </button>
          <span className="text-[13px] text-[#616977]">
            Каналы вакансий, доступные в текущем наборе откликов
          </span>
        </div>

        {/* Expandable Sources Panel (Screen 1a) */}
        {isSourcesOpen && (
          <div className="mt-3 bg-white border border-[#1F4FD1] rounded-2xl p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[14px] font-bold text-[#141A24]">
                Источники откликов
              </h2>
              <div className="flex items-center gap-3 text-[13px]">
                <button
                  type="button"
                  onClick={() => setSelectedSources([...allSources])}
                  className="text-[#1F4FD1] hover:underline font-medium cursor-pointer"
                >
                  Выбрать все
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedSources([])}
                  className="text-[#1F4FD1] hover:underline font-medium cursor-pointer"
                >
                  Сбросить
                </button>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2.5 mb-4">
              {allSources.map((source) => {
                const isSelected = selectedSources.includes(source);
                return (
                  <button
                    key={source}
                    type="button"
                    onClick={() => toggleSource(source)}
                    className={`px-3.5 py-2 rounded-xl text-[13px] font-medium transition-colors flex items-center gap-2 border whitespace-nowrap cursor-pointer ${
                      isSelected
                        ? "bg-[#EEF3FE] text-[#1F4FD1] border-[#1F4FD1]"
                        : "bg-white text-[#4A5363] border-[#E1E5EB] hover:bg-[#F3F5F8]"
                    }`}
                  >
                    <span
                      className={`w-4 h-4 rounded flex items-center justify-center text-[10px] ${
                        isSelected
                          ? "bg-[#1F4FD1] text-white"
                          : "border border-[#D2D4D8]"
                      }`}
                    >
                      {isSelected ? "✓" : ""}
                    </span>
                    <span>{source}</span>
                    <span className="text-[11px] opacity-70">
                      {candidates.filter((c) => c.source === source).length}
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={() => setIsSourcesOpen(false)}
                className="px-5 py-2 text-[13px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm cursor-pointer"
              >
                Применить
              </button>
              <button
                type="button"
                onClick={() => setIsSourcesOpen(false)}
                className="px-5 py-2 text-[13px] font-medium text-[#4A5363] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors cursor-pointer"
              >
                Свернуть
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Candidates Table */}
      <div className="bg-white border border-[#E1E5EB] rounded-2xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[14px]">
            <thead className="bg-[#FAFBFD] border-b border-[#E1E5EB] text-[13px] text-[#616977] font-medium">
              <tr>
                <th className="py-3.5 pl-5 pr-3 whitespace-nowrap">Кандидат</th>
                <th className="py-3.5 px-3 whitespace-nowrap">Тип</th>
                <th className="py-3.5 px-3 whitespace-nowrap">Источник</th>
                <th className="py-3.5 px-3 whitespace-nowrap">Вакансия</th>
                <th className="py-3.5 px-3 whitespace-nowrap">Совпадение</th>
                <th className="py-3.5 px-3 whitespace-nowrap">Статус</th>
                <th className="py-3.5 pl-3 pr-5 text-right whitespace-nowrap">
                  На этапе
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E1E5EB]">
              {filteredCandidates.map((c) => (
                <tr key={c.id} className="hover:bg-[#F8FAFC] transition-colors">
                  <td className="py-3.5 pl-5 pr-3 font-medium whitespace-nowrap">
                    <button
                      type="button"
                      onClick={() => onSelectCandidate?.(c)}
                      className="text-[#1F4FD1] hover:underline text-left font-medium whitespace-nowrap"
                    >
                      {c.name}
                    </button>
                  </td>
                  <td className="py-3.5 px-3 whitespace-nowrap">
                    <span className="inline-block px-2.5 py-0.5 rounded-full text-[12px] font-medium bg-[#EEF3FE] text-[#1F4FD1] whitespace-nowrap">
                      {c.type}
                    </span>
                  </td>
                  <td className="py-3.5 px-3 text-[#4A5363] whitespace-nowrap">
                    {c.source}
                  </td>
                  <td className="py-3.5 px-3 text-[#141A24] font-medium whitespace-nowrap">
                    {c.vacancy}
                  </td>
                  <td className="py-3.5 px-3 whitespace-nowrap">
                    <span
                      className={`inline-block px-2.5 py-0.5 rounded-full text-[12px] font-medium whitespace-nowrap ${
                        c.match === "Выполнено"
                          ? "bg-[#E6F4EA] text-[#15803D]"
                          : c.match === "Нужно уточнить"
                            ? "bg-[#FEF3E6] text-[#B45309]"
                            : c.match === "Не оценено"
                              ? "bg-[#F1F3F5] text-[#616977]"
                              : "bg-[#FDE8E8] text-[#C5221F]"
                      }`}
                    >
                      {c.match}
                    </span>
                  </td>
                  <td className="py-3.5 px-3 text-[#4A5363] whitespace-nowrap">
                    {c.status}
                  </td>
                  <td className="py-3.5 pl-3 pr-5 text-right whitespace-nowrap">
                    {c.stageDays == null ? (
                      <span className="text-[#616977]">—</span>
                    ) : c.stageDays >= 6 ? (
                      <span className="inline-block px-2 py-0.5 rounded text-[12px] font-semibold bg-[#FDE8E8] text-[#C5221F] whitespace-nowrap">
                        {c.stageDays} дн.
                      </span>
                    ) : c.stageDays >= 4 ? (
                      <span className="inline-block px-2 py-0.5 rounded text-[12px] font-semibold bg-[#FEF3E6] text-[#B45309] whitespace-nowrap">
                        {c.stageDays} дн.
                      </span>
                    ) : (
                      <span className="text-[#4A5363] font-medium whitespace-nowrap">
                        {c.stageDays} дн.
                      </span>
                    )}
                  </td>
                </tr>
              ))}
              {!loading && !error && !filteredCandidates.length && (
                <tr>
                  <td colSpan={7} className="p-6 text-[#616977]">
                    По выбранным условиям кандидатов нет.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex items-center justify-between mt-4 text-sm">
        <button
          disabled={loading || offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 50))}
          className="text-[#1F4FD1] disabled:opacity-40"
        >
          Назад
        </button>
        <span>
          {total ? offset + 1 : 0}–{Math.min(offset + 50, total)} из {total}
        </span>
        <button
          disabled={loading || offset + 50 >= total}
          onClick={() => setOffset(offset + 50)}
          className="text-[#1F4FD1] disabled:opacity-40"
        >
          Далее
        </button>
      </div>
      {showUpload && (
        <CandidateUpload
          onClose={() => setShowUpload(false)}
          onSaved={(message) => {
            setShowUpload(false);
            setNotice(message);
            setOffset(0);
            setSearch("");
            setReload((value) => value + 1);
          }}
        />
      )}
    </div>
  );
};

export default CandidatesDatabase;
