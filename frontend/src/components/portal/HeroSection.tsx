import React from 'react';

export const HeroSection: React.FC = () => {
  return (
    <section className="bg-[#1F4FD1] rounded-2xl p-8 lg:p-12 text-white shadow-sm">
      {/* Title */}
      <h1 className="text-[32px] sm:text-[38px] font-bold tracking-tight mb-3">
        Работа, которая меняет город
      </h1>

      {/* Subtitle */}
      <p className="text-[15px] sm:text-[16px] text-white/90 max-w-3xl mb-8 leading-relaxed">
        Вакансии администрации, практика для студентов и кадровый резерв в одном месте. Откликнуться можно за пару минут.
      </p>

      {/* Search Bar Card */}
      <div className="bg-white rounded-xl p-2.5 shadow-md flex flex-col md:flex-row items-stretch md:items-center gap-2.5 text-[#141A24]">
        {/* Job Title / Skill Input */}
        <div className="flex-1">
          <input
            type="text"
            placeholder="Должность или навык"
            className="w-full h-11 px-4 text-[14px] bg-white border border-[#E1E5EB] rounded-lg text-[#141A24] placeholder-[#8E939D] focus:outline-none focus:border-[#1F4FD1]"
          />
        </div>

        {/* Departments Select */}
        <div className="relative md:w-56">
          <div className="w-full h-11 px-4 text-[14px] bg-white border border-[#E1E5EB] rounded-lg text-[#141A24] flex items-center justify-between cursor-pointer select-none">
            <span>Все департаменты</span>
            <img src="/icons/chevron-down.svg" alt="" className="w-4 h-4 opacity-70" />
          </div>
        </div>

        {/* Districts Select */}
        <div className="relative md:w-48">
          <div className="w-full h-11 px-4 text-[14px] bg-white border border-[#E1E5EB] rounded-lg text-[#141A24] flex items-center justify-between cursor-pointer select-none">
            <span>Все районы</span>
            <img src="/icons/chevron-down.svg" alt="" className="w-4 h-4 opacity-70" />
          </div>
        </div>

        {/* Search Button */}
        <button
          type="button"
          className="h-11 px-7 bg-[#1F4FD1] hover:bg-[#1841B2] text-white text-[14px] font-medium rounded-lg transition-colors whitespace-nowrap shadow-sm"
        >
          Найти вакансии
        </button>
      </div>
    </section>
  );
};

export default HeroSection;
