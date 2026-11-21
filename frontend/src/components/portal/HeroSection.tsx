import { useState } from 'react';

export function HeroSection({ onSearch }: { onSearch?: (query: string) => void }) {
  const [query, setQuery] = useState('');

  return (
    <section data-tour="portal-hero" className="bg-[#1F4FD1] rounded-2xl p-8 lg:p-12 text-white shadow-sm">
      <h1 className="text-[32px] sm:text-[38px] font-bold tracking-tight mb-3">
        Работа, которая меняет город
      </h1>
      <p className="text-[15px] sm:text-[16px] text-white/90 max-w-3xl mb-8 leading-relaxed">
        Вакансии администрации и практика для студентов.
      </p>
      <form className="bg-white rounded-xl p-2.5 shadow-md flex flex-col md:flex-row items-stretch md:items-center gap-2.5 text-[#141A24]" onSubmit={(event) => {
        event.preventDefault();
        onSearch?.(query.trim());
      }}>
        <input
          type="search"
          aria-label="Должность или навык"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Должность или навык"
          className="flex-1 min-w-0 h-11 px-4 text-[14px] bg-white border border-[#E1E5EB] rounded-lg text-[#141A24] placeholder-[#8E939D] focus:outline-none focus:border-[#1F4FD1]"
        />
        <button type="submit" className="h-11 px-7 bg-[#1F4FD1] hover:bg-[#1841B2] text-white text-[14px] font-medium rounded-lg transition-colors whitespace-nowrap shadow-sm">
          Найти вакансии
        </button>
      </form>
    </section>
  );
}

export default HeroSection;
