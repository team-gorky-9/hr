import React, { useState } from 'react';

export interface CandidateRecord {
  id: string;
  name: string;
  type: 'Внешний отклик' | 'Ротация' | 'Студент' | 'Архив кадров' | 'Кадровый резерв';
  source: string;
  vacancy: string;
  match: 'Нужно уточнить' | 'Выполнено' | 'Не выполнено';
  status: string;
  stageDays: number;
  isOverdue?: boolean;
}

const mockCandidates: CandidateRecord[] = [
  {
    id: 'c1',
    name: 'Фролов Денис',
    type: 'Внешний отклик',
    source: 'HH.ru',
    vacancy: 'Python-разработчик',
    match: 'Нужно уточнить',
    status: 'Нужно уточнить данные',
    stageDays: 1,
  },
  {
    id: 'c2',
    name: 'Ковалёва Анна',
    type: 'Внешний отклик',
    source: '«Работа России»',
    vacancy: 'Python-разработчик',
    match: 'Выполнено',
    status: 'Ждёт решения департамента',
    stageDays: 2,
  },
  {
    id: 'c3',
    name: 'Морозов Илья',
    type: 'Внешний отклик',
    source: 'Сайт администрации',
    vacancy: 'Python-разработчик',
    match: 'Не выполнено',
    status: 'Не подходит · есть другая вакансия',
    stageDays: 1,
  },
  {
    id: 'c4',
    name: 'Орлов Павел',
    type: 'Ротация',
    source: 'Внутренний',
    vacancy: 'Аналитик данных',
    match: 'Выполнено',
    status: 'Ждёт решения департамента',
    stageDays: 4,
  },
  {
    id: 'c5',
    name: 'Никитина Полина',
    type: 'Студент',
    source: 'Студент',
    vacancy: 'Специалист правового управления',
    match: 'Выполнено',
    status: 'Телефонное интервью',
    stageDays: 1,
  },
  {
    id: 'c6',
    name: 'Тихонов Роман',
    type: 'Архив кадров',
    source: 'Архив кадров',
    vacancy: 'Начальник отдела цифровизации',
    match: 'Выполнено',
    status: 'Направлен в департамент',
    stageDays: 6,
    isOverdue: true,
  },
  {
    id: 'c7',
    name: 'Лебедев Сергей',
    type: 'Внешний отклик',
    source: 'Обращение гражданина',
    vacancy: 'Инженер ПТО',
    match: 'Нужно уточнить',
    status: 'Нужно уточнить данные',
    stageDays: 3,
  },
  {
    id: 'c8',
    name: 'Захарова Екатерина',
    type: 'Внешний отклик',
    source: 'Загружено вручную',
    vacancy: 'Инженер ПТО',
    match: 'Не выполнено',
    status: 'Не подходит · есть другая вакансия',
    stageDays: 0,
  },
];

interface CandidatesDatabaseProps {
  onSelectCandidate?: (candidate: CandidateRecord) => void;
  onUploadResume?: () => void;
}

export const CandidatesDatabase: React.FC<CandidatesDatabaseProps> = ({
  onSelectCandidate,
  onUploadResume,
}) => {
  const [activeTypeFilter, setActiveTypeFilter] = useState<string>('Все');
  const [isSourcesOpen, setIsSourcesOpen] = useState<boolean>(false);
  const [selectedSources, setSelectedSources] = useState<string[]>([
    'HH.ru',
    '«Работа России»',
    'Сайт администрации',
    'Обращение гражданина',
    'Загружено вручную',
    'Внутренний',
    'Студент',
    'Архив кадров',
  ]);
  const [showUploadModal, setShowUploadModal] = useState<boolean>(false);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);

  const typeTabs = [
    { label: 'Все', count: 8 },
    { label: 'Внешний отклик', count: 5 },
    { label: 'Студент', count: 1 },
    { label: 'Архив кадров', count: 1 },
    { label: 'Ротация', count: 1 },
  ];

  const allSources = [
    'HH.ru',
    '«Работа России»',
    'Сайт администрации',
    'Обращение гражданина',
    'Загружено вручную',
    'Внутренний',
    'Студент',
    'Архив кадров',
  ];

  const toggleSource = (source: string) => {
    setSelectedSources((prev) =>
      prev.includes(source) ? prev.filter((s) => s !== source) : [...prev, source]
    );
  };

  const filteredCandidates = mockCandidates.filter((c) => {
    if (activeTypeFilter !== 'Все' && c.type !== activeTypeFilter) return false;
    return selectedSources.includes(c.source);
  });

  const handleOpenUpload = () => {
    if (onUploadResume) {
      onUploadResume();
    } else {
      setShowUploadModal(true);
    }
  };

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8">
      {/* Page Title & Action */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-[26px] font-bold text-[#141A24] tracking-tight mb-1">
            Единая база кандидатов
          </h1>
          <p className="text-[14px] text-[#616977]">
            Внешние отклики, студенты, архив кадров и внутренняя ротация в одном месте
          </p>
        </div>
        <button
          type="button"
          onClick={handleOpenUpload}
          className="shrink-0 px-5 py-2.5 text-[14px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm whitespace-nowrap"
        >
          Загрузить резюме
        </button>
      </div>

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
                  ? 'bg-[#1F4FD1] text-white shadow-sm'
                  : 'bg-white text-[#141A24] border border-[#E1E5EB] hover:bg-[#F3F5F8]'
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
            <span>Источники: {selectedSources.length === allSources.length ? `все (${allSources.length})` : `${selectedSources.length} из ${allSources.length}`}</span>
            <span className="text-[10px] text-[#616977]">{isSourcesOpen ? '▲' : '▼'}</span>
          </button>
          <span className="text-[13px] text-[#616977]">
            Нажмите, чтобы выбрать HH.ru, «Работа России», сайт, обращения или загруженные вручную
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
                        ? 'bg-[#EEF3FE] text-[#1F4FD1] border-[#1F4FD1]'
                        : 'bg-white text-[#4A5363] border-[#E1E5EB] hover:bg-[#F3F5F8]'
                    }`}
                  >
                    <span
                      className={`w-4 h-4 rounded flex items-center justify-center text-[10px] ${
                        isSelected ? 'bg-[#1F4FD1] text-white' : 'border border-[#D2D4D8]'
                      }`}
                    >
                      {isSelected ? '✓' : ''}
                    </span>
                    <span>{source}</span>
                    <span className="text-[11px] opacity-70">
                      {mockCandidates.filter((c) => c.source === source).length}
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
                <th className="py-3.5 pl-3 pr-5 text-right whitespace-nowrap">На этапе</th>
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
                  <td className="py-3.5 px-3 text-[#4A5363] whitespace-nowrap">{c.source}</td>
                  <td className="py-3.5 px-3 text-[#141A24] font-medium whitespace-nowrap">{c.vacancy}</td>
                  <td className="py-3.5 px-3 whitespace-nowrap">
                    <span
                      className={`inline-block px-2.5 py-0.5 rounded-full text-[12px] font-medium whitespace-nowrap ${
                        c.match === 'Выполнено'
                          ? 'bg-[#E6F4EA] text-[#15803D]'
                          : c.match === 'Нужно уточнить'
                          ? 'bg-[#FEF3E6] text-[#B45309]'
                          : 'bg-[#FDE8E8] text-[#C5221F]'
                      }`}
                    >
                      {c.match}
                    </span>
                  </td>
                  <td className="py-3.5 px-3 text-[#4A5363] whitespace-nowrap">{c.status}</td>
                  <td className="py-3.5 pl-3 pr-5 text-right whitespace-nowrap">
                    {c.stageDays >= 6 ? (
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
            </tbody>
          </table>
        </div>
      </div>

      {/* Upload Modal (Mockup Action) */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border border-[#E1E5EB]">
            <h2 className="text-[18px] font-bold text-[#141A24] mb-2">
              Загрузить резюме в единую базу
            </h2>
            <p className="text-[13px] text-[#616977] mb-4">
              Поддерживаются файлы PDF и DOCX до 10 МБ. Персональные данные будут обезличены до оценки ИИ.
            </p>
            <div className="border-2 border-dashed border-[#D2D4D8] rounded-xl p-6 text-center mb-4 bg-[#F8FAFC]">
              <div className="text-[14px] text-[#141A24] font-medium mb-1">
                Перетащите файл резюме сюда
              </div>
              <div className="text-[12px] text-[#616977]">
                или нажмите для выбора с устройства
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowUploadModal(false)}
                className="px-4 py-2 text-[13px] font-medium text-[#4A5363] hover:bg-gray-100 rounded-lg transition-colors"
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowUploadModal(false);
                  setUploadSuccess('Резюме успешно загружено и отправлено на обработку');
                  setTimeout(() => setUploadSuccess(null), 3000);
                }}
                className="px-4 py-2 text-[13px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors"
              >
                Загрузить
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast notification */}
      {uploadSuccess && (
        <div className="fixed bottom-6 right-6 bg-[#141A24] text-white text-[13px] px-4 py-2.5 rounded-lg shadow-lg z-50 animate-fade-in flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[#15803D]"></span>
          {uploadSuccess}
        </div>
      )}
    </div>
  );
};

export default CandidatesDatabase;
