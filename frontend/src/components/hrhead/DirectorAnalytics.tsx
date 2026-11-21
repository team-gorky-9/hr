import React, { useState } from 'react';
import { Card, Kpi, Badge, Bar, Btn, PageTitle } from '../shared/ui';

// Заглушка: данные макета «Дашборд аналитики» (бэкенд: GET /api/v1/analytics/dashboard)
const funnel = [['Отклики', 100], ['Разобраны', 92], ['Телефонное интервью', 65], ['Очное собеседование', 15], ['Приняты', 6]] as const;
const sources = [
  ['HH.ru', 45, '62%', 'green'], ['«Работа России»', 25, '48%', 'amber'],
  ['Сайт администрации', 15, '73%', 'green'], ['Загружено вручную', 10, '70%', 'green'],
  ['Обращения граждан', 5, '40%', 'red'],
] as const;
const depts = [
  ['Цифрового развития', 8, 5, 1, 1, 1], ['Строительства', 5, 2, 0, 1, 2],
  ['Экономики', 4, 4, 0, 0, 0], ['Общий отдел', 2, 1, 1, 0, 0],
] as const;
const reasons = [['Не выполнены требования закона', 34], ['Не хватает опыта', 22], ['Другая специализация', 15], ['Кандидат отказался', 9], ['Выбран другой кандидат', 6]] as const;
const months = [['Июн', 70, 6], ['Июл', 78, 7], ['Авг', 90, 8], ['Сен', 82, 8], ['Окт', 96, 10], ['Ноя', 100, 11]] as const;

export const DirectorAnalytics: React.FC<{ onExportReport: () => void }> = ({ onExportReport }) => {
  const [period, setPeriod] = useState('Квартал');
  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
      <PageTitle
        title="Аналитика подбора"
        subtitle="Вся администрация · синтетические данные для демонстрации"
        right={
          <div className="flex flex-wrap items-center gap-3">
            <div className="inline-flex bg-[#E8ECF2] rounded-xl p-1">
              {['Месяц', 'Квартал', 'Год'].map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPeriod(p)}
                  className={`px-4 py-2 rounded-lg text-[15px] font-semibold ${period === p ? 'bg-white text-[#141A24] shadow-sm' : 'text-[#4A5363]'}`}
                >
                  {p}
                </button>
              ))}
            </div>
            <Btn variant="primary" onClick={onExportReport}>Выгрузить в годовой отчёт</Btn>
          </div>
        }
      />

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi label="Откликов за ноябрь" value="100" caption="+6% к октябрю" />
        <Kpi label="Дошли до очного" value="15%" caption="на уровне прошлого месяца" />
        <Kpi label="Средний срок ответа департамента" value="6,4 дн." caption="норма — 10 дней" />
        <Kpi label="Ответы без причины" value="0" caption="причина обязательна" />
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Воронка подбора</h2>
          <p className="text-[15px] text-[#4A5363]">Из 100 откликов до очного собеседования доходят 15</p>
          {funnel.map(([l, v]) => (
            <div key={l} className="flex items-center gap-4 text-[16px]">
              <span className="w-[170px] shrink-0">{l}</span>
              <Bar pct={v} />
              <span className="w-10 font-bold text-right">{v}</span>
            </div>
          ))}
        </Card>

        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Источники откликов</h2>
          <p className="text-[15px] text-[#4A5363]">Количество и доля, дошедшая до интервью</p>
          {sources.map(([l, v, p, t]) => (
            <div key={l} className="flex items-center gap-4 text-[16px]">
              <span className="w-[170px] shrink-0">{l}</span>
              <Bar pct={(v / 45) * 100} color="#5B80E0" />
              <span className="w-8 font-bold text-right">{v}</span>
              <Badge tone={t}>{p}</Badge>
            </div>
          ))}
        </Card>

        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Ответы департаментов по направленным кандидатам</h2>
          <p className="text-[15px] text-[#4A5363]">Светофор: в срок до 7 дней, срок подходит 8–10 дней, просрочено больше 10</p>
          <table className="w-full text-left text-[16px]">
            <thead>
              <tr className="text-[14px] text-[#4A5363] border-b border-[#E1E5EB]">
                {['Департамент', 'Передано', 'Ответили', 'В срок', 'Срок подходит', 'Просрочено'].map((h) => (
                  <th key={h} className="py-3 pr-2 font-semibold">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {depts.map(([n, a, b, c, d, e]) => (
                <tr key={n} className="border-b border-[#E1E5EB] last:border-0">
                  <td className="py-3 pr-2">{n}</td><td>{a}</td><td>{b}</td>
                  <td><Badge tone={c ? 'green' : 'gray'}>{c}</Badge></td>
                  <td><Badge tone={d ? 'amber' : 'gray'}>{d}</Badge></td>
                  <td><Badge tone={e ? 'red' : 'gray'}>{e}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Причины отказов</h2>
          <p className="text-[15px] text-[#4A5363]">От HR-менеджеров и департаментов, за период</p>
          {reasons.map(([l, v]) => (
            <div key={l} className="flex items-center gap-4 text-[16px]">
              <span className="w-[200px] shrink-0">{l}</span>
              <Bar pct={(v / 34) * 100} color="#C2410C" />
              <span className="w-8 font-bold text-right">{v}</span>
            </div>
          ))}
        </Card>

        <Card className="space-y-3">
          <h2 className="text-[22px] font-bold">Динамика по месяцам</h2>
          <p className="text-[15px] text-[#4A5363]">Отклики растут, доля дошедших до очного стабильна: около 15%</p>
          <div className="flex items-end gap-5 h-[200px] pt-4">
            {months.map(([m, a, b]) => (
              <div key={m} className="flex flex-col items-center gap-2 flex-1">
                <div className="flex items-end gap-1 h-[160px]">
                  <div className="w-[22px] rounded-t bg-[#1F4FD1]" style={{ height: `${a * 1.5}px` }} />
                  <div className="w-[22px] rounded-t bg-[#C2410C]" style={{ height: `${b * 1.5}px` }} />
                </div>
                <span className="text-[13px] text-[#4A5363]">{m}</span>
              </div>
            ))}
          </div>
          <div className="flex gap-5 text-[14px] text-[#4A5363]">
            <span><span className="inline-block w-3 h-3 rounded-sm bg-[#1F4FD1] mr-1" />Отклики</span>
            <span><span className="inline-block w-3 h-3 rounded-sm bg-[#C2410C] mr-1" />Очное собеседование</span>
          </div>
        </Card>

        <Card className="space-y-4">
          <h2 className="text-[22px] font-bold">Работа HR-менеджеров</h2>
          <table className="w-full text-left text-[16px]">
            <thead>
              <tr className="text-[14px] text-[#4A5363] border-b border-[#E1E5EB]">
                {['HR-менеджер', 'Разобрано', 'Интервью', 'Ср. звонок'].map((h) => <th key={h} className="py-3 font-semibold">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {[['Марина С.', 58, 34, '24 мин'], ['Ольга К.', 42, 31, '27 мин']].map((r) => (
                <tr key={r[0]} className="border-b border-[#E1E5EB] last:border-0">
                  {r.map((c, i) => <td key={i} className="py-3">{c}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
          <h3 className="text-[18px] font-bold">Архив кадров</h3>
          <div className="grid grid-cols-3 gap-3">
            {[['24', 'резюме в архиве'], ['5', 'принято из архива за год'], ['18', 'студентов']].map(([n, t]) => (
              <div key={t} className="bg-[#F6F7F9] rounded-xl p-4">
                <div className="text-[28px] font-bold">{n}</div>
                <div className="text-[14px] text-[#4A5363]">{t}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
};

export default DirectorAnalytics;
