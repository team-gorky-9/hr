import React, { useState } from 'react';
import { Card, Btn, Badge } from '../shared/ui';

const options = ['Совещания и переписка', 'Работа с обращениями граждан', 'Отчётность и документы', 'Дорога на работу'];
const results = [['Не хватает тишины', 41], ['Старый компьютер', 33], ['Неудобное кресло', 18], ['Всё устраивает', 8]] as const;

export const Surveys: React.FC = () => {
  const [choice, setChoice] = useState<number | null>(1);
  const [step, setStep] = useState(1);
  const [done, setDone] = useState(false);

  const next = () => {
    if (step >= 3) { setDone(true); return; }
    setStep(step + 1);
    setChoice(null);
  };

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
      <div className="bg-[#F1EDFF] rounded-3xl p-8 flex items-center gap-5">
        <div className="w-[64px] h-[64px] bg-white rounded-2xl flex items-center justify-center text-[28px]">🛡</div>
        <div>
          <h1 className="text-[32px] font-bold">Опросы</h1>
          <p className="text-[18px] text-[#4A5363]">Все опросы анонимные: руководитель видит только общую сводку, а не ваши ответы.</p>
        </div>
      </div>

      <div className="grid lg:grid-cols-[2fr_1fr] gap-5 items-start">
        <Card className="space-y-4">
          {done ? (
            <div className="py-10 text-center space-y-2">
              <div className="text-[22px] font-bold text-[#1D7A40]">Спасибо! Ответы приняты анонимно</div>
              <Btn onClick={() => { setDone(false); setStep(1); setChoice(null); }}>Пройти заново</Btn>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3"><Badge tone="purple">Новый</Badge><span className="text-[15px] text-[#4A5363]">Вопрос {step} из 3 · около 2 минут</span></div>
              <h2 className="text-[24px] font-bold">Где вы устаёте больше всего?</h2>
              {options.map((o, i) => (
                <button key={o} type="button" onClick={() => setChoice(i)}
                  className={`w-full text-left rounded-xl border-2 px-5 py-5 text-[18px] transition-colors ${choice === i ? 'border-[#1F4FD1] bg-[#EEF3FE]' : 'border-[#E1E5EB] bg-white hover:bg-[#F8F9FB]'}`}>
                  {o}
                </button>
              ))}
              <div className="flex items-center gap-4">
                <Btn variant="primary" disabled={choice === null} onClick={next}>Дальше</Btn>
                <Btn variant="link" onClick={next}>Пропустить вопрос</Btn>
              </div>
            </>
          )}
        </Card>
        <Card className="space-y-3 min-h-[300px]">
          <h2 className="text-[22px] font-bold">Все опросы</h2>
          {[['Где вы устаёте больше всего?', 'Новый', 'purple'], ['Удобно ли рабочее место?', 'Пройден', 'green'], ['Оценка адаптации', 'С 1 декабря', 'gray']].map(([t, b, tone]) => (
            <div key={t} className="flex items-center justify-between gap-3 text-[16px]">
              {t}<Badge tone={tone as 'purple' | 'green' | 'gray'}>{b}</Badge>
            </div>
          ))}
        </Card>
      </div>

      <div className="grid lg:grid-cols-[2fr_1fr] gap-5 items-start">
        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Итоги опроса «Удобно ли рабочее место?»</h2>
          <p className="text-[15px] text-[#4A5363]">Ответили 212 сотрудников · октябрь 2026</p>
          {results.map(([l, v]) => (
            <div key={l} className="flex items-center gap-4 text-[17px]">
              <span className="w-[200px] shrink-0">{l}</span>
              <div className="flex-1 h-[30px] rounded-md bg-[#F0F2F6] overflow-hidden"><div className="h-full bg-[#7C5CDB] rounded-md" style={{ width: `${(v / 41) * 100}%` }} /></div>
              <span className="w-10 font-bold text-right">{v}</span><span className="text-[#4A5363]">%</span>
            </div>
          ))}
        </Card>
        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Что изменили по итогам</h2>
          {['Сделали 2 переговорные для тихой работы', 'Заменили 40 компьютеров в 3 департаментах', 'Закупку кресел включили в план на 2027 год'].map((t) => (
            <div key={t} className="flex items-center gap-3 text-[17px]">
              <span className="w-6 h-6 rounded bg-[#1F4FD1] text-white flex items-center justify-center text-[14px] shrink-0">✓</span>{t}
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
};

export default Surveys;
