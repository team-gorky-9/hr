import React, { useState } from 'react';

export const ReserveCtaBanner: React.FC = () => {
  const [notice, setNotice] = useState(false);
  return (
    <section className="bg-[#FFF8E8] border border-[#F3E2B5] rounded-2xl p-6 lg:p-8 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-6">
      {/* Left Text */}
      <div>
        <span className="inline-block bg-[#FFEFD9] text-[#9A3412] text-[12px] font-medium px-2.5 py-1 rounded-md mb-3">
          Возможности развития
        </span>
        <h2 className="text-[20px] font-bold text-[#141A24] mb-1.5">
          Кадровый резерв 2026
        </h2>
        <p className="text-[14px] text-[#4A5363] leading-relaxed max-w-2xl">
          Конкурс с защитой проекта перед комиссией города. Приём заявок будет добавлен позже.
        </p>
      </div>

      {/* Right Button */}
      <div className="shrink-0">
        <button
          type="button"
          onClick={() => setNotice(true)}
          className="px-6 py-3 bg-[#1F4FD1] hover:bg-[#1841B2] text-white text-[14px] font-medium rounded-lg transition-colors whitespace-nowrap shadow-sm"
        >
          Подробнее о конкурсе
        </button>
        {notice && <p role="status" className="mt-3 text-sm text-[#9A3412]">Будет добавлено позже</p>}
      </div>
    </section>
  );
};

export default ReserveCtaBanner;
