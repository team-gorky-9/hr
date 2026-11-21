import React from 'react';

export const Card: React.FC<{ className?: string; children: React.ReactNode }> = ({
  className = '',
  children,
}) => (
  <div className={`bg-white border border-[#E1E5EB] rounded-2xl p-5 sm:p-6 ${className}`}>
    {children}
  </div>
);

export const Kpi: React.FC<{
  label?: string;
  value: React.ReactNode;
  caption?: string;
  tone?: 'default' | 'danger' | 'success';
}> = ({ label, value, caption, tone = 'default' }) => {
  const toneCls =
    tone === 'danger'
      ? 'bg-[#FCE8E8] border-[#F3B8B8]'
      : tone === 'success'
        ? 'bg-[#E3F2E7] border-[#9FD0AC]'
        : 'bg-white border-[#E1E5EB]';
  return (
    <div className={`rounded-2xl border p-5 ${toneCls}`}>
      {label && <div className="text-[14px] text-[#4A5363]">{label}</div>}
      <div className="text-[34px] leading-tight font-bold text-[#141A24] mt-1">{value}</div>
      {caption && <div className="text-[13px] text-[#4A5363] mt-1">{caption}</div>}
    </div>
  );
};

type BadgeTone = 'gray' | 'red' | 'green' | 'amber' | 'blue' | 'purple';
const badgeTones: Record<BadgeTone, string> = {
  gray: 'bg-[#EEF1F5] text-[#4A5363]',
  red: 'bg-[#FCE8E8] text-[#A3171B]',
  green: 'bg-[#E3F2E7] text-[#1D7A40]',
  amber: 'bg-[#FFEFD9] text-[#8A4B0A]',
  blue: 'bg-[#EEF3FE] text-[#1F4FD1]',
  purple: 'bg-[#F1EDFF] text-[#5B3FC4]',
};
export const Badge: React.FC<{ tone?: BadgeTone; children: React.ReactNode; className?: string }> = ({
  tone = 'gray',
  children,
  className = '',
}) => (
  <span
    className={`inline-flex items-center px-2.5 py-1 rounded-md text-[13px] font-semibold ${badgeTones[tone]} ${className}`}
  >
    {children}
  </span>
);

export const Btn: React.FC<
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'link' }
> = ({ variant = 'secondary', className = '', ...rest }) => {
  const v =
    variant === 'primary'
      ? 'bg-[#1F4FD1] text-white hover:bg-[#1841B2] disabled:bg-[#E1E5EB] disabled:text-[#8E939D] px-5 py-3 rounded-xl'
      : variant === 'link'
        ? 'text-[#1F4FD1] hover:underline px-0 py-0'
        : 'bg-white border border-[#C9D0DB] text-[#141A24] hover:bg-[#F3F5F8] px-5 py-3 rounded-xl';
  return (
    <button
      type="button"
      {...rest}
      className={`text-[15px] font-semibold transition-colors disabled:cursor-not-allowed ${v} ${className}`}
    />
  );
};

export const Chip: React.FC<{
  active?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}> = ({ active, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    className={`px-4 py-2 rounded-full border text-[15px] font-semibold transition-colors ${
      active
        ? 'border-[#1F4FD1] text-[#1F4FD1] bg-[#EEF3FE]'
        : 'border-[#C9D0DB] text-[#141A24] bg-white hover:bg-[#F3F5F8]'
    }`}
  >
    {children}
  </button>
);

export const Bar: React.FC<{ pct: number; color?: string }> = ({ pct, color = '#1F4FD1' }) => (
  <div className="h-[22px] rounded-md bg-[#EEF1F5] overflow-hidden flex-1">
    <div className="h-full rounded-md" style={{ width: `${pct}%`, background: color }} />
  </div>
);

export const PageTitle: React.FC<{ title: string; subtitle?: string; right?: React.ReactNode }> = ({
  title,
  subtitle,
  right,
}) => (
  <div className="flex flex-wrap items-end justify-between gap-4">
    <div>
      <h1 className="text-[28px] font-bold text-[#141A24] leading-tight">{title}</h1>
      {subtitle && <p className="text-[16px] text-[#4A5363] mt-1">{subtitle}</p>}
    </div>
    {right}
  </div>
);

export const Toast: React.FC<{ message: string | null }> = ({ message }) =>
  message ? (
    <div className="fixed bottom-6 right-6 z-50 bg-[#141A24] text-white text-[14px] px-4 py-3 rounded-xl shadow-lg">
      {message}
    </div>
  ) : null;
