import React, { useState } from 'react';
import { Card, Badge, Btn, Toast } from '../shared/ui';

type Step = { name: string; min: number; done: boolean };

export const Workspace: React.FC<{ onNavigate: (tab: string) => void }> = ({ onNavigate }) => {
  const [steps, setSteps] = useState<Step[]>([
    { name: 'Знакомство с администрацией', min: 12, done: true },
    { name: 'Структура и департаменты', min: 15, done: true },
    { name: 'Документооборот и СЭД', min: 20, done: false },
    { name: 'Антикоррупционные требования', min: 18, done: false },
    { name: 'Работа с обращениями граждан', min: 25, done: false },
  ]);
  const [question, setQuestion] = useState('');
  const [toast, setToast] = useState<string | null>(null);
  const notify = (m: string) => { setToast(m); setTimeout(() => setToast(null), 3000); };
  const done = steps.filter((s) => s.done).length;

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
      <div className="bg-[#1F4FD1] rounded-3xl p-8 flex flex-wrap items-center justify-between gap-6 text-white">
        <div>
          <h1 className="text-[32px] font-bold">Добрый день, Кирилл!</h1>
          <p className="text-[18px] mt-2 text-[#DCE5FB]">24-й день в администрации. Осталось 3 модуля адаптации: примерно 1 час.</p>
        </div>
        <div className="flex gap-4">
          {[[`${Math.round((done / steps.length) * 100)}%`, 'адаптации пройдено'], ['1', 'документ в работе'], ['2', 'события на неделе']].map(([n, l]) => (
            <div key={l} className="bg-white/15 rounded-2xl px-5 py-4 min-w-[170px]">
              <div className="text-[28px] font-bold">{n}</div>
              <div className="text-[15px] text-[#DCE5FB]">{l}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-5">
        {[
          ['🛡', 'bg-[#F1EDFF]', 'Новый опрос ждёт вас', '2 минуты, анонимно', 'Открыть: Опросы', 'surveys'],
          ['🏅', 'bg-[#FFEFD9]', 'Психолог в четверг', 'Осталось 4 места', 'Открыть: Забота и мотивация', 'care'],
          ['💼', 'bg-[#E3F2E7]', '2 вакансии вам подходят', 'Совпадение до 81%', 'Открыть: Витрина вакансий', 'vacancies'],
        ].map(([ic, bg, t, s, l, tab]) => (
          <Card key={t} className="space-y-3">
            <div className="flex items-center gap-4">
              <div className={`w-[52px] h-[52px] rounded-xl flex items-center justify-center text-[22px] ${bg}`}>{ic}</div>
              <div><div className="text-[18px] font-bold">{t}</div><div className="text-[15px] text-[#4A5363]">{s}</div></div>
            </div>
            <Btn variant="link" onClick={() => onNavigate(tab)}>{l}</Btn>
          </Card>
        ))}
      </div>

      <div className="grid lg:grid-cols-[2fr_1fr] gap-5 items-start">
        <div className="space-y-5">
          <Card className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-[22px] font-bold">Адаптация</h2>
              <span className="text-[16px] font-semibold text-[#1F4FD1]">Пройдено {done} из {steps.length}</span>
            </div>
            <div className="h-[10px] rounded-full bg-[#E8ECF2]">
              <div className="h-full rounded-full bg-[#1F4FD1] transition-all" style={{ width: `${(done / steps.length) * 100}%` }} />
            </div>
            {steps.map((s, i) => (
              <div key={s.name} className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-4 text-[17px]">
                  <Badge tone={s.done ? 'green' : 'gray'}>{s.done ? 'Пройдено' : 'Не начато'}</Badge>
                  {s.name} · {s.min} мин
                </div>
                {s.done ? (
                  <Btn variant="link" onClick={() => notify(`Повтор модуля: ${s.name}`)}>Повторить</Btn>
                ) : (
                  <Btn onClick={() => setSteps(steps.map((x, j) => (j === i ? { ...x, done: true } : x)))}>Начать</Btn>
                )}
              </div>
            ))}
          </Card>
          <Card className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-[22px] font-bold">Единое окно: мои документы</h2>
              <Btn variant="primary" onClick={() => notify('Подача документа: заглушка')}>Подать документ</Btn>
            </div>
            <p className="text-[16px] text-[#4A5363]">Документы отправляются онлайн, привозить их в администрацию не нужно</p>
            <div className="flex justify-between items-center text-[17px]">
              Справка с места работы
              <span className="flex items-center gap-3"><Badge tone="green">Готово</Badge><Btn variant="link" onClick={() => notify('Скачивание: заглушка')}>Скачать</Btn></span>
            </div>
            <div className="flex justify-between items-center text-[17px]">
              Заявление на отпуск, 15–28 декабря
              <span className="flex items-center gap-3"><Badge tone="amber">На согласовании</Badge><Btn variant="link" onClick={() => notify('Подробнее: заглушка')}>Подробнее</Btn></span>
            </div>
          </Card>
        </div>

        <div className="space-y-5">
          <Card className="space-y-4">
            <h2 className="text-[22px] font-bold">Мой наставник</h2>
            <div className="flex items-center gap-3">
              <div className="w-[52px] h-[52px] rounded-full bg-[#E8EEFC] text-[#1F4FD1] font-bold flex items-center justify-center">ОП</div>
              <div><div className="text-[18px] font-bold">Ольга Петрова</div><div className="text-[14px] text-[#4A5363]">Главный специалист, департамент экономики</div></div>
            </div>
            <Btn className="w-full text-left" onClick={() => notify('Чат с наставником: заглушка')}>Написать наставнику</Btn>
          </Card>
          <Card className="space-y-4">
            <h2 className="text-[22px] font-bold">Ближайшие события</h2>
            {[['25', 'Встреча новых сотрудников с главой города'], ['27', 'Тест по антикоррупционным требованиям']].map(([d, t]) => (
              <div key={d} className="flex items-center gap-4">
                <div className="w-[52px] h-[52px] rounded-xl bg-[#FFEFD9] flex flex-col items-center justify-center shrink-0">
                  <span className="text-[20px] font-bold leading-none">{d}</span><span className="text-[11px] font-bold">НОЯ</span>
                </div>
                <div className="text-[16px]">{t}</div>
              </div>
            ))}
          </Card>
          <Card className="space-y-3">
            <h2 className="text-[22px] font-bold">Вопрос HR-менеджеру</h2>
            <p className="text-[15px] text-[#4A5363]">Ответ придёт в кабинет в течение рабочего дня</p>
            <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Например: как оформить отгул?"
              className="w-full border border-[#C9D0DB] rounded-xl px-4 py-3 text-[16px] outline-none focus:border-[#1F4FD1]" />
            <Btn onClick={() => { notify(question ? 'Вопрос отправлен HR-менеджеру' : 'Введите вопрос'); if (question) setQuestion(''); }}>Отправить</Btn>
          </Card>
        </div>
      </div>
      <Toast message={toast} />
    </div>
  );
};

export default Workspace;
