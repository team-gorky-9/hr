import React from 'react';

export type HRNavTab = 'database' | 'vacancies' | 'interview' | 'reserve' | 'archive' | 'analytics';

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
  managerName = 'HR-менеджер · Марина С.',
}) => {
  const tabs: { id: HRNavTab; label: string }[] = [
    { id: 'database', label: 'Единая база' },
    { id: 'vacancies', label: 'Отклики по вакансиям' },
    { id: 'interview', label: 'Интервью' },
    { id: 'archive', label: 'Архив резюме' },
    { id: 'reserve', label: 'Кадровый резерв' },
    { id: 'analytics', label: 'Аналитика' },
  ];

  return (
    <header className="w-full bg-white border-b border-[#E1E5EB] sticky top-0 z-40">
      <div className="max-w-[1240px] mx-auto px-4 sm:px-6 h-[72px] flex items-center justify-between">
        {/* Left: Brand + Navigation */}
        <div className="flex items-center gap-4 lg:gap-8">
          <button
            type="button"
            onClick={onLogoClick || (() => onTabChange('database'))}
            className="flex items-center gap-3 text-left hover:opacity-90 transition-opacity"
          >
            <img
              src="/images/Header/Mark.svg"
              alt="GorkyCode"
              className="w-9 h-9 shrink-0"
            />
            <span className="text-[16px] font-bold text-[#141A24] tracking-tight whitespace-nowrap">
              GorkyCode - team 9
            </span>
          </button>

          <nav className="hidden md:flex items-center gap-1.5">
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
        <div className="text-[14px] text-[#4A5363] font-medium whitespace-nowrap">
          {managerName}
        </div>
      </div>
    </header>
  );
};

export default HeaderHR;
