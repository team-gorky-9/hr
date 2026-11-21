import React from 'react';

export interface RoleTab {
  id: string;
  label: string;
}

interface RoleHeaderProps {
  tabs: RoleTab[];
  activeTab: string;
  onTabChange: (id: string) => void;
  roleLabel: string;
  onLogoClick?: () => void;
}

/** Общий хедер для ролей: начальник ОК, директор, руководитель департамента, сотрудник. */
export const RoleHeader: React.FC<RoleHeaderProps> = ({
  tabs,
  activeTab,
  onTabChange,
  roleLabel,
  onLogoClick,
}) => (
  <header className="w-full bg-white border-b border-[#E1E5EB] sticky top-0 z-40">
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 min-h-[72px] py-3 flex flex-wrap gap-y-2 items-center justify-between">
      <div className="flex flex-wrap items-center gap-4 lg:gap-6">
        <button
          type="button"
          onClick={onLogoClick}
          className="flex items-center gap-3 text-left hover:opacity-90 transition-opacity"
        >
          <img src="/images/Header/Mark.svg" alt="GorkyCode" className="w-9 h-9 shrink-0" />
          <span className="text-[16px] font-bold text-[#141A24] tracking-tight whitespace-nowrap">
            GorkyCode - team 9
          </span>
        </button>
        <nav className="hidden md:flex flex-wrap items-center gap-1.5">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              className={`px-3.5 py-1.5 rounded-lg text-[14px] transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'bg-[#EEF3FE] text-[#1F4FD1] font-semibold'
                  : 'text-[#4A5363] hover:text-[#141A24] hover:bg-[#F3F5F8] font-medium'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>
      <div className="text-[14px] text-[#4A5363] font-medium whitespace-nowrap hidden lg:block">
        {roleLabel}
      </div>
    </div>
  </header>
);

export default RoleHeader;
