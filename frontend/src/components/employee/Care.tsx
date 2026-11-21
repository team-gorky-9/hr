import { useState } from 'react';
import { Badge, Btn, Card, Chip } from '../shared/ui';

const filters = ['Все', 'Психологическая поддержка', 'Творчество', 'Спорт', 'Семья', 'Обучение'];
const items = [
  { category: 'Психологическая поддержка', kind: 'Групповая сессия с психологом', title: 'Как не выгорать на работе с людьми', description: 'Обсуждение с психологом в небольшой группе', action: 'Записаться', color: 'bg-[#E8EEFC]', id: 'session' },
  { category: 'Творчество', kind: 'Арт-терапия', title: 'Вечер рисования для команды', description: 'Совместная творческая встреча', action: 'Записаться', color: 'bg-[#FFF2D6]', id: 'art' },
  { category: 'Психологическая поддержка', kind: 'Видеокурс психологов', title: 'Как найти общий язык с подростком', description: 'Короткие уроки о разговоре с подростками', action: 'Смотреть курс', color: 'bg-[#E3F2E7]', id: 'video' },
  { category: 'Семья', kind: 'Семейное мероприятие', title: 'Семейный выезд на базу отдыха', description: 'Мероприятие для сотрудников и их семей', action: 'Записать семью', color: 'bg-[#FFE4D6]', id: 'family' },
  { category: 'Спорт', kind: 'Спорт', title: 'Спартакиада администрации: волейбол', description: 'Командные тренировки и соревнования', action: 'Вступить в команду', color: 'bg-[#F1EDFF]', id: 'sport' },
  { category: 'Обучение', kind: 'Обучение', title: 'Тайм-менеджмент для госслужащих', description: 'Онлайн-курс по планированию работы', action: 'Начать курс', color: 'bg-[#EEF1F5]', id: 'course' },
];

export default function Care({ onNavigate }: { onNavigate?: (tab: string) => void }) {
  const [filter, setFilter] = useState('Все');
  const [noticeFor, setNoticeFor] = useState('');
  const list = items.filter((item) => filter === 'Все' || item.category === filter);

  return <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
    <div data-tour="employee-care-hero" className="bg-[#FFF2D6] rounded-3xl p-8 flex flex-wrap items-center justify-between gap-5">
      <div className="flex flex-wrap items-center gap-5">
        <div aria-hidden="true" className="w-16 h-16 shrink-0 bg-white rounded-2xl grid place-items-center text-[28px]">🏅</div>
        <div>
          <h1 className="text-[32px] font-bold">Забота и мотивация</h1>
          <p className="text-[18px] text-[#4A5363]">Поддержка, отдых и признание</p>
        </div>
      </div>
      {onNavigate && <Btn onClick={() => onNavigate('support')}>Открыть материальную помощь</Btn>}
    </div>

    <div data-tour="employee-care-filters" className="flex flex-wrap items-center gap-3">
      {filters.map((option) => <Chip key={option} active={option === filter} onClick={() => { setFilter(option); setNoticeFor(''); }}>{option}</Chip>)}
    </div>

    <div className="space-y-3">
      <Badge tone="amber">Примеры мероприятий и курсов</Badge>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
        {list.map((item) => <article key={item.id} className={item.color + ' rounded-2xl p-6 space-y-3'}>
          <p className="text-[15px] text-[#4A5363]">{item.kind}</p>
          <h2 className="text-[22px] font-bold leading-snug">{item.title}</h2>
          <p className="text-[16px] text-[#4A5363]">{item.description}</p>
          <Btn onClick={() => setNoticeFor(item.id)}>{item.action}</Btn>
          {noticeFor === item.id && <p role="status" className="text-[14px] font-semibold text-[#4A5363]">Будет добавлено позже</p>}
        </article>)}
      </div>
    </div>

    <div className="grid lg:grid-cols-[2fr_1fr] gap-5">
      <Card className="space-y-3">
        <h2 className="text-[22px] font-bold">Мои записи</h2>
        <p className="text-[#4A5363]">Здесь будут отображаться записи на мероприятия.</p>
      </Card>
      <Card className="space-y-4">
        <h2 className="text-[22px] font-bold">Примеры наград</h2>
        {[['🏅', 'Наставник года'], ['📈', 'Призовое место на спартакиаде']].map(([icon, title]) => <div key={title} className="flex items-center gap-4">
          <div aria-hidden="true" className="w-[52px] h-[52px] shrink-0 bg-[#FFEFD9] rounded-xl grid place-items-center text-[22px]">{icon}</div>
          <p className="text-[18px] font-bold">{title}</p>
        </div>)}
      </Card>
    </div>
  </div>;
}

