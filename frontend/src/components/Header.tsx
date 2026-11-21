import React from 'react';

interface HeaderProps {
  activeNav?: string;
  onLogoClick?: () => void;
  onNavClick?: (nav: string) => void;
  onLoginClick?: () => void;
  onRegisterClick?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeNav = '',
  onLogoClick,
  onNavClick,
  onLoginClick,
  onRegisterClick,
}) => {
  const navItems = [
    { id: 'vacancies', label: 'Вакансии', href: '#' },
    { id: 'students', label: 'Студентам', href: '#' },
    { id: 'practice', label: 'Моя практика', href: '#' },
    { id: 'reserve', label: 'Кадровый резерв', href: '#' },
    { id: 'administration', label: 'Работа в администрации', href: '#' },
  ];

  return (
    <header className="w-full bg-white border-b border-[#E1E5EB] sticky top-0 z-50">
      <div className="max-w-[1230px] mx-auto px-6 h-[72px] flex items-center justify-between">
        {/* Left Side: Logo & Navigation */}
        <div className="flex items-center gap-4 lg:gap-8">
          {/* Logo with Exact Vector SVG Emblem from _design-refs/Header 2/Mark.svg */}
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              onLogoClick?.();
            }}
            className="flex items-center gap-3 group cursor-pointer text-left focus:outline-none"
          >
            <img
              src="/images/Header/Mark.svg"
              alt="GorkyCode"
              className="w-9 h-9 shrink-0 transition-transform group-hover:scale-105"
            />
            <span className="text-[16px] font-bold text-[#141A24] tracking-tight whitespace-nowrap">
              GorkyCode - team 9
            </span>
          </button>

          {/* Navigation Links */}
          <nav className="hidden md:flex items-center gap-3.5 lg:gap-6">
            {navItems.map((item) => {
              const isActive = activeNav === item.id;
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
        </div>

        {/* Right Side: Auth Buttons */}
        <div className="flex items-center gap-3 shrink-0">
          <button
            type="button"
            onClick={onLoginClick}
            className="px-5 py-2 text-[14px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors whitespace-nowrap"
          >
            Войти
          </button>
          <button
            type="button"
            onClick={onRegisterClick}
            className="px-5 py-2 text-[14px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm whitespace-nowrap"
          >
            Регистрация
          </button>
        </div>
      </div>
    </header>
  );
};

export default Header;
