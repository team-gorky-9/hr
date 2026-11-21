import React, { useState } from 'react';
import { Card, Btn, Badge } from '../shared/ui';

const states = [
  { cls: 'bg-white border-[#E1E5EB]', val: '0', valSize: 'text-[26px]', valCls: 'text-[#141A24]', unit: 'откликов', note: 'Данные есть, откликов не было' },
  { cls: 'bg-[#FFEFD9] border-[#F3C98B]', val: 'не менее 242', valSize: 'text-[19px] sm:text-[20px]', valCls: 'text-[#8A4B0A]', unit: 'откликов', note: '45 откликов без даты не учтены' },
  { cls: 'bg-[#EEF1F5] border-dashed border-[#C9D0DB]', val: 'нет данных', valSize: 'text-[19px] sm:text-[20px]', valCls: 'text-[#3B4352]', unit: '', note: 'Источник не передал этот показатель' },
  { cls: 'bg-[#EEF1F5] border-dashed border-[#C9D0DB]', val: '—', valSize: 'text-[26px]', valCls: 'text-[#3B4352]', unit: 'за пределами периода', note: 'Вакансия открыта после 31.12.2025' },
  { cls: 'bg-[#F1EDFF] border-[#D5C9F5]', val: 'несопоставимо', valSize: 'text-[17px] sm:text-[18px] tracking-tight', valCls: 'text-[#5B3FC4]', unit: 'с 2024 годом', note: 'В 2024 году не вели журнал собеседований' },
];

const cards = [
  { t: 'Каталог версий пуст', d: 'Ещё нет ни одного доклада. Загрузите выгрузку за год.', b: 'Загрузить данные', ic: '📘' },
  { t: 'Загрузка раздела', skeleton: true },
  { t: 'Не удалось загрузить', d: 'Данные не потеряны. Повторите через минуту.', b: 'Повторить', ic: '🛡' },
  { t: 'Версия недоступна', d: 'Версия v2 отозвана. Откройте актуальную v3 от 15.01.2026.', b: 'Открыть v3', ic: '🏢' },
  { t: 'Нет кадрового реестра', d: 'Раздел «Штат» строится по реестру. Подбор доступен.', b: 'Как подключить', ic: '💼' },
  { t: 'Конструктор недоступен', d: 'Версия создана до появления конструктора. Доступен только доклад.', b: 'Скачать годовой XLSX', ic: '📈' },
];

export const Coverage: React.FC<{ onNotify: (m: string) => void }> = ({ onNotify }) => {
  const [example, setExample] = useState(false);

  if (example)
    return (
      <div className="space-y-5">
        <Card className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-[24px] font-bold">Ведущий специалист (юрист) · архивный отчёт консультанта</h2>
            <p className="text-[16px] text-[#4A5363]">Одна вакансия · источник: consultant-2026.xlsx</p>
          </div>
          <Badge>Внешний источник</Badge>
        </Card>
        <div className="grid lg:grid-cols-[2fr_1fr] gap-5">
          <Card className="space-y-4 min-h-[300px]">
            <h2 className="text-[22px] font-bold">Почему «не менее 242»</h2>
            <div className="flex flex-wrap items-end gap-10">
              <div><div className="text-[38px] font-bold">287</div><div className="text-[15px] text-[#4A5363]">строк в архиве</div></div>
              <div className="text-[30px]">–</div>
              <div><div className="text-[38px] font-bold text-[#8A4B0A]">45</div><div className="text-[15px] text-[#4A5363]">без даты отклика</div></div>
              <div className="text-[30px]">=</div>
              <div><div className="text-[38px] font-bold">242</div><div className="text-[15px] text-[#4A5363]">точно в периоде</div></div>
            </div>
            <p className="text-[17px]">45 откликов могли прийти в любой год: без даты мы не знаем, попадают ли они в 2025. Поэтому показываем нижнюю границу, а не «287».</p>
            <Btn variant="link" onClick={() => setExample(false)}>← Назад к состояниям</Btn>
          </Card>
          <div className="space-y-5">
            <div className="rounded-2xl border border-[#F3C98B] bg-[#FFEFD9] p-5">
              <div className="text-[15px] font-semibold">Отклики</div>
              <div className="text-[34px] font-bold text-[#8A4B0A]">не менее 242</div>
              <div className="text-[15px] text-[#4A5363]">45 без даты не учтены</div>
            </div>
            <div className="rounded-2xl border border-dashed border-[#C9D0DB] bg-[#EEF1F5] p-5">
              <div className="text-[15px] font-semibold">Разговоры</div>
              <div className="text-[34px] font-bold text-[#3B4352]">нет данных</div>
              <div className="text-[15px] text-[#4A5363]">Журнал собеседований не передан консультантом</div>
            </div>
          </div>
        </div>
      </div>
    );

  return (
    <div className="space-y-5">
      <Card className="space-y-4">
        <div>
          <h2 className="text-[22px] font-bold">Один показатель — пять состояний</h2>
          <p className="text-[16px] text-[#4A5363]">Цвет всегда дублируется подписью</p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
          {states.map((s) => (
            <div key={s.val} className={`rounded-2xl border p-4 ${s.cls} flex flex-col justify-between min-h-[160px] overflow-hidden`}>
              <div>
                <div className="text-[13px] font-semibold text-[#616977] mb-1">Отклики · 2025</div>
                <div className={`font-bold leading-tight ${s.valSize} ${s.valCls}`}>{s.val}</div>
                {s.unit && <div className="text-[14px] font-bold text-[#141A24] mt-0.5">{s.unit}</div>}
              </div>
              <div className="text-[13px] text-[#4A5363] mt-2 leading-snug">{s.note}</div>
            </div>
          ))}
        </div>
        <Btn variant="link" onClick={() => setExample(true)}>Пример «не менее 242»: архив консультанта</Btn>
      </Card>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {cards.map((c) =>
          c.skeleton ? (
            <Card key={c.t} className="space-y-3">
              <div className="text-[20px] font-bold">{c.t}</div>
              <div className="h-4 rounded bg-[#E8ECF2]" />
              <div className="h-20 rounded bg-[#E8ECF2]" />
              <div className="h-4 rounded bg-[#E8ECF2]" />
            </Card>
          ) : (
            <Card key={c.t} className="space-y-2">
              <div className="w-[48px] h-[48px] rounded-xl bg-[#F6F7F9] flex items-center justify-center text-[22px]">{c.ic}</div>
              <div className="text-[20px] font-bold">{c.t}</div>
              <p className="text-[16px] text-[#4A5363]">{c.d}</p>
              <Btn onClick={() => onNotify(`${c.b}: заглушка`)}>{c.b}</Btn>
            </Card>
          ),
        )}
      </div>
    </div>
  );
};

export default Coverage;
