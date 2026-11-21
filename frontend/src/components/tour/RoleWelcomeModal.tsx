import React, { useEffect } from 'react';
import { TOUR_ROLES, TOUR_STEPS, type TourRole } from './tourSteps';

interface RoleWelcomeModalProps {
  open: boolean;
  onSelectRole: (role: TourRole) => void;
  onClose: () => void;
}

function formatStepCount(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return `${count} шаг`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} шага`;
  return `${count} шагов`;
}

function RoleIcon({ role }: { role: TourRole }) {
  switch (role) {
    case 'portal':
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className="w-5 h-5">
          <path
            d="M12 3 2 8l10 5 10-5-10-5Zm0 10v8m-6-5.5V19c0 1.2 2.7 2.5 6 2.5s6-1.3 6-2.5v-3.5"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case 'hr':
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className="w-5 h-5">
          <path
            d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2M9 5h6m-5 7 2 2 4-4"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case 'dept':
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className="w-5 h-5">
          <path
            d="M12 8v4l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case 'employee':
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className="w-5 h-5">
          <path
            d="M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 20a7 7 0 0 1 16 0"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
  }
}

export const RoleWelcomeModal: React.FC<RoleWelcomeModalProps> = ({
  open,
  onSelectRole,
  onClose,
}) => {
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-[#141A24]/60 backdrop-blur-[2px] p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="guided-tour-welcome-title"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-[820px] max-h-[calc(100vh-48px)] overflow-y-auto bg-white rounded-2xl border border-[#E1E5EB] shadow-2xl">
        {/* Header */}
        <div className="px-7 pt-7 pb-5 border-b border-[#E1E5EB] flex items-start justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-[#EEF3FE] text-[#1F4FD1] text-[12px] font-semibold mb-3">
              <svg aria-hidden="true" viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5">
                <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5" />
                <path
                  d="m10.8 5.2-1.8 4.4-4.4 1.8 1.8-4.4 4.4-1.8Z"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinejoin="round"
                />
              </svg>
              <span>Интерактивный гид по платформе</span>
            </div>
            <h2
              id="guided-tour-welcome-title"
              className="text-[24px] font-bold text-[#141A24] tracking-tight leading-snug"
            >
              Добро пожаловать в Кадровый ассистент
            </h2>
            <p className="mt-1.5 text-[14px] text-[#4A5363] leading-relaxed">
              Выберите роль — интерактивный гид проведёт вас по ключевым экранам и базовому сценарию за 2 минуты.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть окно выбора роли"
            className="shrink-0 w-9 h-9 rounded-xl text-[#616977] hover:text-[#141A24] hover:bg-[#F3F5F8] flex items-center justify-center transition-colors"
          >
            <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" className="w-5 h-5">
              <path
                d="M5.5 5.5 14.5 14.5M14.5 5.5 5.5 14.5"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>

        {/* 4 Role Cards */}
        <div className="p-7 bg-[#F3F5F8]/60">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {TOUR_ROLES.map((role) => {
              const stepCount = TOUR_STEPS[role.id].length;
              return (
                <button
                  key={role.id}
                  type="button"
                  onClick={() => onSelectRole(role.id)}
                  className="group text-left bg-white rounded-2xl border border-[#E1E5EB] hover:border-[#1F4FD1] p-5 shadow-sm hover:shadow-md transition-all flex flex-col justify-between gap-4 focus:outline-none focus:ring-2 focus:ring-[#1F4FD1]/40"
                >
                  <div>
                    <div className="flex items-center justify-between gap-3 mb-3">
                      <span
                        className={`w-10 h-10 rounded-xl ${role.accentBg} ${role.accentText} flex items-center justify-center shrink-0`}
                      >
                        <RoleIcon role={role.id} />
                      </span>
                      <span className="px-2.5 py-1 rounded-full bg-[#F3F5F8] text-[#4A5363] text-[12px] font-semibold whitespace-nowrap">
                        {formatStepCount(stepCount)}
                      </span>
                    </div>
                    <h3 className="text-[16px] font-bold text-[#141A24] group-hover:text-[#1F4FD1] transition-colors leading-snug">
                      {role.title}
                    </h3>
                    <p className="mt-1.5 text-[13px] text-[#4A5363] leading-relaxed">
                      {role.description}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 text-[13px] font-semibold text-[#1F4FD1]">
                    <span>Начать маршрут</span>
                    <span
                      aria-hidden="true"
                      className="transition-transform group-hover:translate-x-0.5"
                    >
                      →
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <div className="px-7 py-4 bg-white border-t border-[#E1E5EB] flex flex-wrap items-center justify-between gap-3">
          <p className="text-[12px] text-[#616977]">
            Вернуться к выбору роли можно в любой момент через кнопку «Гид по сайту» в верхней панели.
          </p>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-[13px] font-semibold text-[#4A5363] bg-white border border-[#C9D0DB] hover:bg-[#F3F5F8] hover:text-[#141A24] transition-colors whitespace-nowrap"
          >
            Пропустить и смотреть свободно
          </button>
        </div>
      </div>
    </div>
  );
};

export default RoleWelcomeModal;
