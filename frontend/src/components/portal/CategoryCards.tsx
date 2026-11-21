import React from 'react';

interface CategoryCardsProps {
  onSelectCategory?: (id: string) => void;
}

export const CategoryCards: React.FC<CategoryCardsProps> = ({ onSelectCategory }) => {
  const cards = [
    {
      id: 'vacancies',
      title: 'Вакансии',
      description: 'Должности в департаментах и районах города. Откликайтесь с резюме в PDF.',
      linkText: 'Смотреть вакансии →',
      iconSrc: '/icons/briefcase.svg',
      iconBg: 'bg-[#E8EEFC]',
    },
    {
      id: 'students',
      title: 'Студентам',
      description: 'Выбирайте место практики и следите за своей заявкой.',
      linkText: 'Найти практику →',
      iconSrc: '/icons/graduation-cap.svg',
      iconBg: 'bg-[#FFE5CC]',
    },
  ];

  return (
    <section className="grid grid-cols-1 md:grid-cols-2 gap-5">
      {cards.map((card) => (
        <div
          key={card.id}
          className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm flex flex-col justify-between hover:shadow-md transition-shadow"
        >
          <div>
            {/* Icon Badge */}
            <div
              className={`w-11 h-11 rounded-xl ${card.iconBg} flex items-center justify-center mb-4`}
            >
              <img src={card.iconSrc} alt="" className="w-5 h-5" />
            </div>

            {/* Title */}
            <h2 className="text-[18px] font-bold text-[#141A24] mb-2">
              {card.title}
            </h2>

            {/* Description */}
            <p className="text-[13px] text-[#616977] leading-relaxed mb-6">
              {card.description}
            </p>
          </div>

          {/* Action Link */}
          <button
            type="button"
            onClick={() => onSelectCategory?.(card.id)}
            className="text-[14px] font-semibold text-[#1F4FD1] hover:underline inline-flex items-center gap-1.5 text-left"
          >
            {card.linkText}
          </button>
        </div>
      ))}
    </section>
  );
};

export default CategoryCards;
