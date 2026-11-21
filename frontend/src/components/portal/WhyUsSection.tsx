import React from 'react';

export const WhyUsSection: React.FC = () => {
  const benefits = [
    {
      id: 'stability',
      title: 'Стабильность',
      description: 'Официальное трудоустройство и гарантии муниципальной службы.',
      iconSrc: '/icons/shield-check.svg',
    },
    {
      id: 'projects',
      title: 'Проекты для города',
      description: 'Цифровые сервисы, благоустройство, работа с жителями.',
      iconSrc: '/icons/building.svg',
    },
    {
      id: 'adaptation',
      title: 'Адаптация и обучение',
      description: 'Вводный курс, наставник, повышение квалификации.',
      iconSrc: '/icons/book.svg',
    },
    {
      id: 'growth',
      title: 'Карьерный рост',
      description: 'Кадровый резерв и переход между департаментами.',
      iconSrc: '/icons/trending-up.svg',
    },
  ];

  return (
    <section>
      <h2 className="text-[20px] font-bold text-[#141A24] mb-4">
        Почему у нас
      </h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {benefits.map((b) => (
          <div
            key={b.id}
            className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow"
          >
            {/* Icon Badge */}
            <div className="w-10 h-10 rounded-xl bg-[#EEF3FE] flex items-center justify-center mb-4">
              <img src={b.iconSrc} alt="" className="w-5 h-5" />
            </div>

            {/* Title */}
            <h3 className="text-[16px] font-bold text-[#141A24] mb-2">
              {b.title}
            </h3>

            {/* Description */}
            <p className="text-[13px] text-[#616977] leading-relaxed">
              {b.description}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
};

export default WhyUsSection;
