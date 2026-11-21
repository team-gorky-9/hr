import React, { useState } from 'react';
import { Card, Kpi, Badge, Btn, PageTitle, Toast } from '../shared/ui';

// Заглушка: макет «Сводка начальника отдела кадров» (бэкенд: GET /api/v1/head/summary)
const rows = [
  { vacancy: 'Python-разработчик', responses: 6, clarify: 1, manual: 3, forwarded: 1, wait: '3 дня', tone: 'gray' as const, hr: 'Марина С.' },
  { vacancy: 'Аналитик данных', responses: 14, clarify: 4, manual: 1, forwarded: 3, wait: '6 дней', tone: 'red' as const, hr: 'Ольга К.' },
  { vacancy: 'Инженер ПТО', responses: 27, clarify: 7, manual: 2, forwarded: 1, wait: '9 дней', tone: 'red' as const, hr: 'Сергей Д.' },
  { vacancy: 'Главный специалист по обращениям граждан', responses: 0, clarify: 0, manual: 0, forwarded: 0, wait: '—', tone: 'gray' as const, hr: 'Марина С.' },
];

const attention = [
  { days: 'Ждёт 6 дней', text: 'Аналитик данных · Департамент цифрового развития' },
  { days: 'Ждёт 9 дней', text: 'Инженер ПТО · Департамент строительства' },
];

export const HeadSummary: React.FC = () => {
  const [toast, setToast] = useState<string | null>(null);
  const remind = (t: string) => {
    setToast(`Напоминание отправлено: ${t}`);
    setTimeout(() => setToast(null), 3000);
  };
  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-6">
      <PageTitle title="Сводка по подбору" subtitle="Все открытые вакансии администрации · обновлено сегодня в 09:00" />

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi label="Открытые вакансии" value="4" caption="в 3 подразделениях" />
        <Kpi label="Откликов за неделю" value="47" caption="из 4 каналов" />
        <Kpi label="Нужно уточнить" value="12" caption="вопросы кандидатам отправлены" />
        <Kpi label="Ждут решения руководителя" value="5" caption="2 дольше 5 дней" />
      </div>

      <Card className="space-y-4">
        <div>
          <h2 className="text-[22px] font-bold text-[#141A24]">Требует внимания</h2>
          <p className="text-[16px] text-[#4A5363] mt-2">Руководители не ответили по переданным кандидатам дольше 5 дней</p>
        </div>
        {attention.map((a) => (
          <div key={a.text} className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-4">
              <Badge tone="red">{a.days}</Badge>
              <span className="text-[17px] font-bold text-[#141A24]">{a.text}</span>
            </div>
            <Btn onClick={() => remind(a.text)}>Напомнить руководителю</Btn>
          </div>
        ))}
      </Card>

      <Card className="overflow-x-auto">
        <table className="w-full text-left min-w-[860px]">
          <thead>
            <tr className="text-[14px] text-[#4A5363] border-b border-[#E1E5EB]">
              {['Вакансия', 'Откликов', 'Нужно уточнить', 'Проверить вручную', 'Передано руководителю', 'Ожидание ответа', 'HR-менеджер'].map((h) => (
                <th key={h} className="py-4 pr-4 font-semibold align-bottom">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.vacancy} className="border-b border-[#E1E5EB] last:border-0 text-[17px] text-[#141A24]">
                <td className="py-4 pr-4">{r.vacancy}</td>
                <td className="pr-4">{r.responses}</td>
                <td className="pr-4">{r.clarify}</td>
                <td className="pr-4">{r.manual}</td>
                <td className="pr-4">{r.forwarded}</td>
                <td className="pr-4"><Badge tone={r.tone}>{r.wait}</Badge></td>
                <td>{r.hr}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Toast message={toast} />
    </div>
  );
};

export default HeadSummary;
