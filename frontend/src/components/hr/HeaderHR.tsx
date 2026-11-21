import React from 'react';

export type HRNavTab = 'database' | 'vacancies' | 'interview' | 'archive' | 'hiring' | 'requirements' | 'analytics';

interface HeaderHRProps {
  activeTab: HRNavTab;
  onTabChange: (tab: HRNavTab) => void;
  onLogoClick?: () => void;
  managerName?: string;
}

export const HeaderHR: React.FC<HeaderHRProps> = ({
  activeTab,
  onTabChange,
  onLogoClick,
  managerName = 'Кабинет HR',
}) => {
  const tabs: { id: HRNavTab; label: string }[] = [
    { id: 'database', label: 'Единая база' },
    { id: 'vacancies', label: 'Отклики по вакансиям' },
    { id: 'archive', label: 'Архив кадров' },
    { id: 'hiring', label: 'Оформление' },
    { id: 'requirements', label: 'Требования и вакансии' },
    { id: 'analytics', label: 'Аналитика' },
  ];

  return (
    <header className="w-full bg-white border-b border-[#E1E5EB] sticky top-0 z-40">
      <div className="max-w-[1240px] mx-auto px-4 sm:px-6 min-h-[72px] py-3 grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 sm:gap-x-4 gap-y-3">
        {/* Brand and navigation occupy separate rows. */}
        <div className="contents">
          <button
            type="button"
            onClick={onLogoClick || (() => onTabChange('database'))}
            className="flex items-center gap-3 min-w-0 justify-self-start text-left hover:opacity-90 transition-opacity"
          >
            <img
              src="/images/Header/Mark.svg"
              alt="Кадровый ассистент"
              className="w-9 h-9 shrink-0"
            />
            <span className="hidden sm:inline text-[16px] font-bold text-[#141A24] tracking-tight whitespace-nowrap">
              Кадровый ассистент
            </span>
          </button>

          <nav aria-label="Кабинет кадров" className="col-span-2 row-start-2 flex min-w-0 overflow-x-auto pb-1 md:overflow-visible md:flex-wrap items-center gap-1.5">
            {tabs.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => onTabChange(tab.id)}
                  className={`px-3.5 py-1.5 rounded-lg text-[14px] transition-colors whitespace-nowrap ${
                    isActive
                      ? 'bg-[#EEF3FE] text-[#1F4FD1] font-semibold'
                      : 'text-[#4A5363] hover:text-[#141A24] hover:bg-[#F3F5F8] font-medium'
                  }`}
                >
                  {tab.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Right: Manager Profile */}
        <div title={managerName} aria-label="Текущая учётная запись" className="col-start-2 row-start-1 justify-self-end max-w-full truncate text-right text-[14px] leading-5 text-[#4A5363] font-medium">
          {managerName}
        </div>
      </div>
    </header>
  );
};

export default HeaderHR;
