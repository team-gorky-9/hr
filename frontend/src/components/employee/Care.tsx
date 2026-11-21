import React, { useState } from 'react';
import { Card, Btn, Badge, Toast } from '../shared/ui';

const filters = ['Все', 'Психологическая поддержка', 'Творчество', 'Спорт', 'Семья', 'Обучение'];
const items = [
  { cat: 'Психологическая поддержка', kind: 'Групповая сессия с психологом', title: 'Как не выгорать на работе с людьми', meta: 'Четверг, 18:00 · осталось 4 места', btn: 'Записаться', bg: 'bg-[#E8EEFC]', id: 'session' },
  { cat: 'Творчество', kind: 'Арт-терапия', title: 'Вечер рисования для команды', meta: 'Пятница, 17:30 · кабинет 214', btn: 'Записаться', bg: 'bg-[#FFF2D6]', id: 'art' },
  { cat: 'Психологическая поддержка', kind: 'Видеокурс психологов', title: 'Как найти общий язык с подростком', meta: '6 уроков по 15 минут', btn: 'Смотреть курс', bg: 'bg-[#E3F2E7]', id: 'video' },
  { cat: 'Семья', kind: 'Семейное мероприятие', title: 'Семейный выезд на базу отдыха', meta: '13 декабря · для сотрудников и семей', btn: 'Записать семью', bg: 'bg-[#FFE4D6]', id: 'family' },
  { cat: 'Спорт', kind: 'Спорт', title: 'Спартакиада администрации: волейбол', meta: 'Тренировки по средам, 19:00', btn: 'Вступить в команду', bg: 'bg-[#F1EDFF]', id: 'sport' },
  { cat: 'Обучение', kind: 'Обучение', title: 'Тайм-менеджмент для госслужащих', meta: 'Онлайн-курс, 2 недели', btn: 'Начать курс', bg: 'bg-[#EEF1F5]', id: 'course' },
];

export const Care: React.FC = () => {
  const [filter, setFilter] = useState('Все');
  const [booked, setBooked] = useState(true);
  const [toast, setToast] = useState<string | null>(null);
  const notify = (m: string) => { setToast(m); setTimeout(() => setToast(null), 3000); };
  const list = items.filter((i) => filter === 'Все' || i.cat === filter);

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
      <div className="bg-[#FFF2D6] rounded-3xl p-8 flex flex-wrap items-center justify-between gap-5">
        <div className="flex items-center gap-5">
          <div className="w-[64px] h-[64px] bg-white rounded-2xl flex items-center justify-center text-[28px]">🏅</div>
          <div>
            <h1 className="text-[32px] font-bold">Забота и мотивация</h1>
            <p className="text-[18px] text-[#4A5363]">Поддержка, отдых и признание. Записаться можно в один клик, участие бесплатное.</p>
          </div>
        </div>
        <div className="flex gap-4">
          <div className="bg-white rounded-2xl px-6 py-4 border border-[#E1E5EB]"><div className="text-[28px] font-bold">{booked ? 1 : 0}</div><div className="text-[14px] text-[#4A5363]">моя запись</div></div>
          <div className="bg-white rounded-2xl px-6 py-4 border border-[#E1E5EB]"><div className="text-[28px] font-bold">2</div><div className="text-[14px] text-[#4A5363]">награды</div></div>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        {filters.map((f) => (
          <button key={f} type="button" onClick={() => setFilter(f)}
            className={`px-5 py-2.5 rounded-full border text-[16px] font-semibold ${filter === f ? 'bg-[#1F4FD1] text-white border-[#1F4FD1]' : 'bg-white border-[#C9D0DB] text-[#141A24]'}`}>
            {f}
          </button>
        ))}
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
        {list.map((i) => (
          <div key={i.id} className={`${i.bg} rounded-2xl p-6 space-y-3`}>
            <div className="text-[15px] text-[#4A5363]">{i.kind}</div>
            <div className="text-[22px] font-bold leading-snug">{i.title}</div>
            <div className="text-[16px] text-[#4A5363]">{i.meta}</div>
            <Btn onClick={() => { if (i.id === 'session') setBooked(true); notify(`${i.btn}: ${i.title}`); }}>{i.btn}</Btn>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-[2fr_1fr] gap-5">
        <Card className="space-y-3 min-h-[200px]">
          <h2 className="text-[22px] font-bold">Мои записи</h2>
          {booked ? (
            <>
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-4 text-[17px]"><Badge tone="green">Вы записаны</Badge>Групповая сессия с психологом · четверг, 18:00</div>
                <Btn variant="link" onClick={() => setBooked(false)}>Отменить</Btn>
              </div>
              <p className="text-[15px] text-[#4A5363]">Напомним за 2 часа до начала</p>
            </>
          ) : <p className="text-[16px] text-[#4A5363]">Записей пока нет</p>}
        </Card>
        <Card className="space-y-4">
          <h2 className="text-[22px] font-bold">Мои награды</h2>
          {[['🏅', 'Наставник года', '2025'], ['📈', 'Спартакиада 2026', '2 место, волейбол']].map(([ic, t, s]) => (
            <div key={t} className="flex items-center gap-4">
              <div className="w-[52px] h-[52px] bg-[#FFEFD9] rounded-xl flex items-center justify-center text-[22px]">{ic}</div>
              <div><div className="text-[18px] font-bold">{t}</div><div className="text-[15px] text-[#4A5363]">{s}</div></div>
            </div>
          ))}
        </Card>
      </div>
      <Toast message={toast} />
    </div>
  );
};

export default Care;
