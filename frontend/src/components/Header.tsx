import React from 'react';

interface HeaderProps {
  activeNav?: string;
  onLogoClick?: () => void;
  onNavClick?: (nav: string) => void;
  onLoginClick?: () => void;
  authenticated?: boolean;
  onLogoutClick?: () => void;
  demoMode?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  activeNav = '',
  onLogoClick,
  onNavClick,
  onLoginClick,
  authenticated = false,
  onLogoutClick,
  demoMode = false,
}) => {
  const navItems = [
    { id: 'vacancies', label: 'Вакансии', href: '#' },
    { id: 'students', label: 'Студентам', href: '#' },
    ...(demoMode ? [{ id: 'cabinet', label: 'Мои отклики', href: '#' }] : []),
  ];

  return (
    <header className="w-full bg-white border-b border-[#E1E5EB] sticky top-0 z-50">
      <div className="max-w-[1230px] mx-auto px-4 sm:px-6 min-h-[72px] py-2.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          {/* Logo with Exact Vector SVG Emblem from _design-refs/Header 2/Mark.svg */}
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              onLogoClick?.();
            }}
            className="min-w-0 flex items-center gap-2 sm:gap-3 group cursor-pointer text-left"
          >
            <img
              src="/images/Header/Mark.svg"
              alt="GorkyCode"
              className="w-9 h-9 shrink-0 transition-transform group-hover:scale-105"
            />
            <span className="text-[16px] font-bold text-[#141A24] tracking-tight">
              GorkyCode · команда 9
            </span>
          </button>

          {/* Navigation Links */}
          <nav aria-label="Разделы портала" className="order-last sm:order-none w-full sm:w-auto sm:mr-auto flex flex-wrap items-center gap-3.5 lg:gap-6">
            {navItems.map((item) => {
              const isActive = activeNav === item.id || item.id === 'students' && activeNav === 'practice';
              return (
                <a
                  key={item.id}
                  href={item.href}
                  onClick={(e) => {
                    e.preventDefault();
                    onNavClick?.(item.id);
                  }}
                  className={`text-[14px] lg:text-[15px] whitespace-nowrap transition-colors ${
                    isActive
                      ? 'text-[#1F4FD1] font-semibold'
                      : 'text-[#4A5363] hover:text-[#1F4FD1] font-medium'
                  }`}
                >
                  {item.label}
                </a>
              );
            })}
          </nav>
        <div className={demoMode ? "hidden" : "flex items-center gap-2 sm:gap-3"}>
          {authenticated ? <>
            <button type="button" onClick={() => onNavClick?.('cabinet')} className="px-2.5 sm:px-5 py-2 text-[14px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm">Кабинет</button>
            <button type="button" onClick={onLogoutClick} className="px-2.5 sm:px-5 py-2 text-[14px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors">Выйти</button>
          </> : (
            <button type="button" onClick={onLoginClick} className="px-5 py-2 text-[14px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm">Войти</button>
          )}
        </div>
      </div>
    </header>
  );
};

export default Header;
