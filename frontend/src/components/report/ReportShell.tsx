import React from 'react';
import { Btn } from '../shared/ui';

export type ReportTab = 'overview' | 'dynamics' | 'builder' | 'staff' | 'coverage';

export const REPORT_TABS: { id: ReportTab; label: string }[] = [
  { id: 'overview', label: 'Доклад за год' },
  { id: 'dynamics', label: 'Динамика и причины' },
  { id: 'builder', label: 'Конструктор среза' },
  { id: 'staff', label: 'Штат и ответы подразделений' },
  { id: 'coverage', label: 'Покрытие и состояния' },
];

interface Props {
  tab: ReportTab;
  onTab: (t: ReportTab) => void;
  onDownload: () => void;
  children: React.ReactNode;
}

export const ReportShell: React.FC<Props> = ({ tab, onTab, onDownload, children }) => (
  <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
    <div className="bg-white border border-[#E1E5EB] rounded-2xl px-6 pt-6 pb-0">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-[28px] font-bold text-[#141A24]">Годовой кадровый доклад · 2025</h1>
            <span className="bg-[#FFEFD9] text-[#8A4B0A] text-[13px] font-semibold px-3 py-1 rounded-md">Учебный</span>
          </div>
          <p className="text-[16px] text-[#4A5363] mt-1">
            Администрация г. Нижнего Новгорода · период наблюдения 01.01.2025 – 31.12.2025
          </p>
        </div>
        <div className="flex items-end gap-3">
          <div>
            <div className="text-[13px] font-semibold text-[#4A5363] mb-1">Версия доклада</div>
            <select className="border border-[#C9D0DB] rounded-xl px-4 py-3 text-[16px] bg-white min-w-[200px]">
              <option>v3 от 15.01.2026</option>
              <option>v2 от 20.12.2025 (отозвана)</option>
            </select>
          </div>
          <Btn onClick={onDownload}>Скачать годовой XLSX</Btn>
        </div>
      </div>
      <div className="flex flex-wrap gap-x-7 mt-6">
        {REPORT_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => onTab(t.id)}
            className={`pb-3 text-[16px] font-semibold border-b-[3px] transition-colors ${
              tab === t.id ? 'text-[#1F4FD1] border-[#1F4FD1]' : 'text-[#141A24] border-transparent hover:text-[#1F4FD1]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
    </div>
    {children}
  </div>
);

export default ReportShell;
