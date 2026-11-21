import React, { useState } from 'react';
import { Card, Btn, Badge, Toast } from '../shared/ui';

const vacancies = [
  { id: 'a', title: 'Аналитик данных', place: 'Департамент цифрового развития · Нижегородский район', salary: '55 000 – 80 000 ₽', match: 81, why: 'работаете с Excel и отчётностью, прошли курс SQL', min: 55000, remote: false },
  { id: 'b', title: 'Главный специалист', place: 'Финансовое управление · Нижегородский район', salary: '50 000 – 70 000 ₽', match: 64, why: 'опыт в департаменте экономики; не хватает опыта с бюджетом', min: 50000, remote: false },
  { id: 'c', title: 'Специалист по закупкам', place: 'Управление муниципального заказа · Советский район', salary: '45 000 – 65 000 ₽', match: 58, why: 'знаете документооборот; нужен курс по 44-ФЗ', min: 45000, remote: true },
];

export const VacancyShowcase: React.FC = () => {
  const [suitable, setSuitable] = useState(true);
  const [noRelocation, setNoRelocation] = useState(false);
  const [dept, setDept] = useState('Все департаменты');
  const [district, setDistrict] = useState('Все районы');
  const [salary, setSalary] = useState('60 000 ₽');
  const [applied, setApplied] = useState<string[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const notify = (m: string) => { setToast(m); setTimeout(() => setToast(null), 3000); };

  const list = vacancies.filter((v) => (!suitable || v.match >= 50) && (!noRelocation || v.place.includes('Нижегородский')));

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
      <div className="bg-[#E3F2E7] rounded-3xl p-8 flex items-center gap-5">
        <div className="w-[64px] h-[64px] bg-white rounded-2xl flex items-center justify-center text-[28px]">💼</div>
        <div>
          <h1 className="text-[32px] font-bold">Витрина вакансий</h1>
          <p className="text-[18px] text-[#4A5363]">Переход внутри администрации: ваш профиль уже в системе, резюме заново писать не нужно.</p>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-4">
        <div>
          <div className="text-[14px] font-semibold text-[#4A5363] mb-1">Департамент</div>
          <select value={dept} onChange={(e) => setDept(e.target.value)} className="border border-[#C9D0DB] rounded-xl px-4 py-3 text-[17px] bg-white w-[260px]">
            <option>Все департаменты</option><option>Цифрового развития</option><option>Экономики</option>
          </select>
        </div>
        <div>
          <div className="text-[14px] font-semibold text-[#4A5363] mb-1">Район</div>
          <select value={district} onChange={(e) => setDistrict(e.target.value)} className="border border-[#C9D0DB] rounded-xl px-4 py-3 text-[17px] bg-white w-[200px]">
            <option>Все районы</option><option>Нижегородский</option><option>Советский</option>
          </select>
        </div>
        <div>
          <div className="text-[14px] font-semibold text-[#4A5363] mb-1">Зарплата от</div>
          <input value={salary} onChange={(e) => setSalary(e.target.value)} className="border border-[#C9D0DB] rounded-xl px-4 py-3 text-[17px] w-[160px]" />
        </div>
        <button type="button" onClick={() => setSuitable(!suitable)}
          className={`px-5 py-3 rounded-full text-[16px] font-semibold border ${suitable ? 'bg-[#1F4FD1] text-white border-[#1F4FD1]' : 'bg-white border-[#C9D0DB]'}`}>Подходят мне</button>
        <button type="button" onClick={() => setNoRelocation(!noRelocation)}
          className={`px-5 py-3 rounded-full text-[16px] font-semibold border ${noRelocation ? 'bg-[#1F4FD1] text-white border-[#1F4FD1]' : 'bg-white border-[#C9D0DB]'}`}>Без переезда</button>
      </div>

      <div className="grid lg:grid-cols-[2fr_1fr] gap-5 items-start">
        <div className="space-y-5">
          {list.map((v) => (
            <Card key={v.id} className="space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-[24px] font-bold">{v.title}</h2>
                  <p className="text-[16px] text-[#4A5363]">{v.place}</p>
                </div>
                <Badge tone={v.match >= 70 ? 'green' : 'amber'}>Совпадение {v.match}%</Badge>
              </div>
              <div className="text-[20px] font-bold">{v.salary}</div>
              <div className="bg-[#F6F7F9] rounded-xl px-5 py-4 text-[16px] text-[#4A5363]">Почему подходит: {v.why}</div>
              <div className="flex gap-3">
                <Btn variant="primary" disabled={applied.includes(v.id)}
                  onClick={() => { setApplied([...applied, v.id]); notify('Отклик отправлен HR-менеджеру'); }}>
                  {applied.includes(v.id) ? 'Отклик отправлен' : 'Откликнуться'}
                </Btn>
                <Btn onClick={() => notify('Подробнее: заглушка')}>Подробнее</Btn>
              </div>
            </Card>
          ))}
          {list.length === 0 && <Card><p className="text-[16px] text-[#4A5363]">По фильтрам вакансий нет</p></Card>}
        </div>
        <div className="space-y-5">
          <Card className="space-y-3">
            <h2 className="text-[22px] font-bold">Мой профиль для перехода</h2>
            <div className="text-[16px] font-semibold text-[#1F4FD1]">Заполнен на 70%</div>
            <div className="h-[10px] rounded-full bg-[#E8ECF2]"><div className="h-full w-[70%] rounded-full bg-[#1F4FD1]" /></div>
            <div className="flex gap-2">{['Excel', 'Отчётность', 'SQL'].map((t) => <Badge key={t} tone="blue">{t}</Badge>)}</div>
            <Btn className="w-full text-left" onClick={() => notify('Профиль: заглушка')}>Дополнить профиль</Btn>
          </Card>
          <Card className="space-y-3">
            <h2 className="text-[22px] font-bold">Мои отклики</h2>
            <div className="flex items-center justify-between">
              <div><div className="text-[17px] font-bold">Аналитик данных</div><div className="text-[14px] text-[#4A5363]">отправлен 18.11</div></div>
              <Badge tone="blue">У HR-менеджера</Badge>
            </div>
          </Card>
          <div className="rounded-2xl border-2 border-[#B7C7F2] bg-[#E8EEFC] p-5">
            <div className="text-[18px] font-bold text-[#1F4FD1]">Ваш руководитель не узнает раньше времени</div>
            <p className="text-[16px] text-[#1F4FD1] mt-1">Отклик видит только HR-менеджер, пока вас не пригласят на собеседование.</p>
          </div>
        </div>
      </div>
      <Toast message={toast} />
    </div>
  );
};

export default VacancyShowcase;
