import React from 'react';

export const ReserveCtaBanner: React.FC = () => {
  return (
    <section className="bg-[#FFF8E8] border border-[#F3E2B5] rounded-2xl p-6 lg:p-8 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-6">
      {/* Left Text */}
      <div>
        <span className="inline-block bg-[#FFEFD9] text-[#9A3412] text-[12px] font-medium px-2.5 py-1 rounded-md mb-3">
          Конкурс открыт
        </span>
        <h2 className="text-[20px] font-bold text-[#141A24] mb-1.5">
          Кадровый резерв 2026
        </h2>
        <p className="text-[14px] text-[#4A5363] leading-relaxed max-w-2xl">
          Подготовьте проект и защитите его перед комиссией города. Заявки принимаются до 15 декабря.
        </p>
      </div>

      {/* Right Button */}
      <div className="shrink-0">
        <button
          type="button"
          className="px-6 py-3 bg-[#1F4FD1] hover:bg-[#1841B2] text-white text-[14px] font-medium rounded-lg transition-colors whitespace-nowrap shadow-sm"
        >
          Подробнее о конкурсе
        </button>
      </div>
    </section>
  );
};

export default ReserveCtaBanner;
