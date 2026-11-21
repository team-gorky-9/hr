import React, { useState } from 'react';
import { Card, Btn, Chip, PageTitle } from '../shared/ui';

type Status = 'overdue' | 'open' | 'closed';

interface Item {
  id: string;
  day: string;
  month: string;
  name: string;
  position: string;
  status: Status;
  daysLeft?: number;
  sentBy: string;
  sentOn: string;
  deadline: string;
  requirement: string;
  competency: string;
  comment: string;
}

// Заглушка: данные из макетов 1–3 (бэкенд: GET /api/v1/handoffs/mine)
const initialItems: Item[] = [
  {
    id: 'tikhonov', day: '18', month: 'НОЯ', name: 'Тихонов Роман',
    position: 'Начальник отдела цифровизации', status: 'overdue',
    sentBy: 'Марина С.', sentOn: '04.11', deadline: '18.11',
    requirement: 'Выполнено: опыт 5 лет', competency: 'Управление проектами · 78',
    comment: 'Опыт подтвердил по телефону.',
  },
  {
    id: 'orlov', day: '24', month: 'НОЯ', name: 'Орлов Павел',
    position: 'Аналитик данных', status: 'open', daysLeft: 2,
    sentBy: 'Ольга К.', sentOn: '10.11', deadline: '24.11',
    requirement: 'Выполнено: опыт 2 года', competency: 'SQL · 80',
    comment: 'Хорошо знает отчётность.',
  },
  {
    id: 'kovaleva', day: '02', month: 'ДЕК', name: 'Ковалёва Анна',
    position: 'Python-разработчик', status: 'open', daysLeft: 8,
    sentBy: 'Марина С.', sentOn: '18.11', deadline: '02.12',
    requirement: 'Выполнено: опыт 3 года', competency: 'Тестирование API · 85',
    comment: 'Опыт подтвердил по телефону, интересуется городскими сервисами.',
  },
];

const reasons = ['Не хватает опыта', 'Другая специализация', 'Выбран другой кандидат', 'Другая причина'];

type Panel = 'idle' | 'reject' | 'close';

export const MyCandidates: React.FC = () => {
  const [items, setItems] = useState<Item[]>(initialItems);
  const [selectedId, setSelectedId] = useState('kovaleva');
  const [panel, setPanel] = useState<Panel>('idle');
  const [reason, setReason] = useState<string | null>(null);
  const [otherText, setOtherText] = useState('');
  const [outcome, setOutcome] = useState('');
  const [report, setReport] = useState('');
  const [result, setResult] = useState<Record<string, string>>({});

  const selected = items.find((i) => i.id === selectedId)!;
  const overdue = items.filter((i) => i.status === 'overdue').length;
  const isClosed = selected.status === 'closed';

  const canSend = reason !== null && (reason !== 'Другая причина' || otherText.trim().length > 0);

  const select = (id: string) => {
    setSelectedId(id);
    setPanel('idle');
    setReason(null);
    setOtherText('');
  };

  const closeItem = (text: string) => {
    setItems((prev) => prev.map((i) => (i.id === selectedId ? { ...i, status: 'closed' } : i)));
    setResult((r) => ({ ...r, [selectedId]: text }));
    setPanel('idle');
  };

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
      <PageTitle
        title="Кандидаты, направленные к вам"
        subtitle="Вы видите только своих кандидатов. Решение и причина сразу уходят HR-менеджеру."
      />
      <div className="text-[16px] text-[#4A5363]">
        Ответить до ·{' '}
        <span className="font-bold text-[#A3171B]">
          {overdue > 0 ? `${overdue} срок уже прошёл` : 'просроченных нет'}
        </span>
      </div>

      <div className="grid lg:grid-cols-[360px_1fr] gap-5 items-start">
        <Card className="space-y-3 !p-3">
          {items.map((i) => {
            const active = i.id === selectedId;
            return (
              <button
                key={i.id}
                type="button"
                onClick={() => select(i.id)}
                className={`w-full flex gap-4 text-left rounded-xl border p-3 transition-colors ${
                  active ? 'border-[#1F4FD1] bg-[#EEF3FE]' : 'border-[#E1E5EB] bg-white hover:bg-[#F8F9FB]'
                }`}
              >
                <div
                  className={`w-[56px] h-[56px] shrink-0 rounded-xl flex flex-col items-center justify-center ${
                    i.status === 'overdue' ? 'bg-[#FCE8E8] text-[#A3171B]' : 'bg-[#F3F5F8] text-[#141A24]'
                  }`}
                >
                  <span className="text-[22px] font-bold leading-none">{i.day}</span>
                  <span className="text-[11px] font-bold mt-0.5">{i.month}</span>
                </div>
                <div className="min-w-0">
                  <div className="text-[16px] font-bold text-[#141A24]">{i.name}</div>
                  <div className="text-[14px] text-[#4A5363]">{i.position}</div>
                  {i.status === 'overdue' && (
                    <div className="text-[14px] font-semibold text-[#A3171B]">просрочено</div>
                  )}
                  {i.status === 'open' && (
                    <div className="text-[14px] text-[#4A5363]">осталось {i.daysLeft} дн.</div>
                  )}
                  {i.status === 'closed' && <div className="text-[14px] text-[#4A5363]">закрыто</div>}
                </div>
              </button>
            );
          })}
        </Card>

        <Card className="space-y-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-[22px] font-bold text-[#141A24]">
              {selected.position} · {selected.name}
            </h2>
            <div className="text-[14px] text-[#4A5363]">
              Направила {selected.sentBy} {selected.sentOn} · срок до {selected.deadline}
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <div className="bg-[#F6F7F9] rounded-xl p-4">
              <div className="text-[14px] text-[#4A5363]">Обязательные требования</div>
              <div className="text-[16px] font-bold text-[#141A24]">{selected.requirement}</div>
            </div>
            <div className="bg-[#F6F7F9] rounded-xl p-4">
              <div className="text-[14px] text-[#4A5363]">Ключевая компетенция</div>
              <div className="text-[16px] font-bold text-[#141A24]">{selected.competency}</div>
            </div>
          </div>

          <div className="rounded-xl border-2 border-[#B7C7F2] bg-[#E8EEFC] p-4">
            <div className="text-[16px] font-bold text-[#1F4FD1]">Комментарий HR-менеджера</div>
            <div className="text-[16px] text-[#1F4FD1] mt-1">{selected.comment}</div>
          </div>

          {isClosed ? (
            <div className="rounded-xl border-2 border-[#9FD0AC] bg-[#E3F2E7] p-4">
              <div className="text-[17px] font-bold text-[#1D7A40]">
                Заявка рассмотрена, отчёт отправлен HR-менеджеру
              </div>
              <div className="text-[16px] text-[#1D7A40] mt-1">Итог: {result[selectedId]}</div>
            </div>
          ) : (
            <>
              {panel !== 'close' && (
                <div className="flex flex-wrap gap-3">
                  <Btn variant="primary" onClick={() => setPanel('close')}>
                    Пригласить на собеседование
                  </Btn>
                  <Btn
                    onClick={() => setPanel(panel === 'reject' ? 'idle' : 'reject')}
                    className={panel === 'reject' ? '!border-[#1F4FD1] !border-2 !text-[#1F4FD1]' : ''}
                  >
                    Не подходит
                  </Btn>
                </div>
              )}

              {panel === 'reject' && (
                <div className="rounded-xl border border-[#E1E5EB] bg-[#F8F9FB] p-5 space-y-4">
                  <div className="text-[18px] font-bold text-[#141A24]">Почему кандидат не подходит?</div>
                  <div className="flex flex-wrap gap-3">
                    {reasons.map((r) => (
                      <Chip key={r} active={reason === r} onClick={() => setReason(r)}>
                        {r}
                      </Chip>
                    ))}
                  </div>
                  {reason === 'Другая причина' && (
                    <div>
                      <label className="block text-[16px] font-bold text-[#141A24] mb-2">Опишите причину</label>
                      <input
                        value={otherText}
                        onChange={(e) => setOtherText(e.target.value)}
                        placeholder="Например: кандидат не готов к выезду на объекты"
                        className="w-full border border-[#C9D0DB] rounded-lg px-4 py-3 text-[16px] bg-white outline-none focus:border-[#1F4FD1]"
                      />
                    </div>
                  )}
                  <div className="flex gap-3">
                    <Btn
                      variant="primary"
                      disabled={!canSend}
                      onClick={() => closeItem(`отказ — ${reason === 'Другая причина' ? otherText : reason}`)}
                    >
                      Отправить HR-менеджеру
                    </Btn>
                    <Btn onClick={() => { setPanel('idle'); setReason(null); setOtherText(''); }}>Отмена</Btn>
                  </div>
                  <div className="text-[14px] text-[#4A5363]">
                    {reason === 'Другая причина'
                      ? 'Кнопка станет активной, когда вы напишете причину'
                      : 'Выберите причину. Она сразу уйдёт HR-менеджеру'}
                  </div>
                </div>
              )}

              {panel === 'close' && (
                <div className="rounded-xl border border-[#B7C7F2] bg-[#F5F8FF] p-5 space-y-3">
                  <div className="text-[18px] font-bold text-[#141A24]">Собеседование проведено? Закройте пункт</div>
                  <label className="block text-[16px] font-bold text-[#141A24]">Итог</label>
                  <input
                    value={outcome}
                    onChange={(e) => setOutcome(e.target.value)}
                    placeholder="Готов принять на должность"
                    className="w-full border border-[#C9D0DB] rounded-lg px-4 py-3 text-[16px] bg-white outline-none focus:border-[#1F4FD1]"
                  />
                  <label className="block text-[15px] font-bold text-[#141A24]">Короткий отчёт для HR-менеджера</label>
                  <input
                    value={report}
                    onChange={(e) => setReport(e.target.value)}
                    placeholder="Сильный в тестировании, готов выйти с 1 декабря"
                    className="w-full border border-[#C9D0DB] rounded-lg px-4 py-3 text-[16px] bg-white outline-none focus:border-[#1F4FD1]"
                  />
                  <Btn
                    variant="primary"
                    disabled={!outcome.trim()}
                    onClick={() => closeItem(outcome.trim().toLowerCase())}
                  >
                    Закрыть пункт и отправить отчёт
                  </Btn>
                </div>
              )}
            </>
          )}
        </Card>
      </div>
    </div>
  );
};

export default MyCandidates;
