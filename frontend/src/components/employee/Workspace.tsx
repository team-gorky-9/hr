import React, { useEffect, useState } from 'react';
import { developmentRequest } from '../../api/development';
import { useSession } from '../../api/session';
import { Card, Badge, Btn, Toast } from '../shared/ui';

type Program = {
  id: string;
  completed_count: number;
  total_count: number;
  status: 'active' | 'intro_completed' | 'cancelled';
  steps: { key: string; title: string; acknowledged_at: string | null }[];
};

type Step = { key: string; title: string; min?: number; done: boolean };

const fallbackSteps: Step[] = [
  { key: 'intro', title: 'Знакомство с администрацией', min: 12, done: true },
  { key: 'structure', title: 'Структура и департаменты', min: 15, done: true },
  { key: 'docs', title: 'Документооборот и СЭД', min: 20, done: false },
  { key: 'anticorruption', title: 'Антикоррупционные требования', min: 18, done: false },
  { key: 'citizens', title: 'Работа с обращениями граждан', min: 25, done: false },
];

export const Workspace: React.FC<{ onNavigate: (tab: string) => void }> = ({ onNavigate }) => {
  const { session } = useSession();
  const token = session?.access_token;
  const [programs, setPrograms] = useState<Program[] | null>(null);
  const [demoSteps, setDemoSteps] = useState<Step[]>(fallbackSteps);
  const [question, setQuestion] = useState('');
  const [toast, setToast] = useState<string | null>(null);
  const notify = (m: string) => {
    setToast(m);
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    setPrograms(null);
    if (!token) return;
    const controller = new AbortController();
    developmentRequest<{ items: Program[] }>(token, '/onboarding/programs', undefined, 'GET', controller.signal)
      .then(({ items }) => {
        if (!controller.signal.aborted) setPrograms(items);
      })
      .catch(() => {
        if (!controller.signal.aborted) setPrograms([]);
      });
    return () => controller.abort();
  }, [token]);

  const current = programs?.filter((program) => program.status !== 'cancelled') ?? [];
  const activeProgram = current[0];
  const displaySteps: Step[] = activeProgram
    ? activeProgram.steps.map((step) => ({ key: step.key, title: step.title, done: Boolean(step.acknowledged_at) }))
    : demoSteps;
  const doneCount = activeProgram ? activeProgram.completed_count : displaySteps.filter((s) => s.done).length;
  const totalCount = activeProgram ? activeProgram.total_count : displaySteps.length;
  const remainingCount = Math.max(0, totalCount - doneCount);
  const progressPercent = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;

  const heroSubtitle = remainingCount > 0
    ? `24-й день в администрации. Осталось ${remainingCount} модуля адаптации: примерно 1 час.`
    : '24-й день в администрации. Все модули адаптации пройдены.';

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-8 space-y-5">
      <div data-tour="employee-workspace-hero" className="bg-[#1F4FD1] rounded-3xl p-8 flex flex-wrap items-center justify-between gap-6 text-white">
        <div>
          <h1 className="text-[32px] font-bold">Добрый день, Кирилл!</h1>
          <p className="text-[18px] mt-2 text-[#DCE5FB]">{heroSubtitle}</p>
        </div>
        <div className="flex flex-wrap gap-4">
          {[
            [`${progressPercent}%`, 'адаптации пройдено'],
            ['1', 'документ в работе'],
            ['2', 'события на неделе'],
          ].map(([n, l]) => (
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
          ['🤝', 'bg-[#E3F2E7]', 'Материальная помощь', 'Заявления и поддержка сотрудников', 'Открыть: Материальная помощь', 'support'],
        ].map(([ic, bg, t, s, l, tab]) => (
          <Card key={t} className="space-y-3">
            <div className="flex items-center gap-4">
              <div aria-hidden="true" className={`w-[52px] h-[52px] shrink-0 rounded-xl flex items-center justify-center text-[22px] ${bg}`}>{ic}</div>
              <div>
                <div className="text-[18px] font-bold">{t}</div>
                <div className="text-[15px] text-[#4A5363]">{s}</div>
              </div>
            </div>
            <Btn variant="link" className="text-left" onClick={() => onNavigate(tab)}>{l}</Btn>
          </Card>
        ))}
      </div>

      <div className="grid lg:grid-cols-[2fr_1fr] gap-5 items-start">
        <div className="space-y-5">
          <div data-tour="employee-onboarding-card">
          <Card className="space-y-4">
            <div className="flex flex-wrap justify-between items-center gap-3">
              <h2 className="text-[22px] font-bold">Адаптация</h2>
              <span className="text-[16px] font-semibold text-[#1F4FD1]">
                Пройдено {doneCount} из {totalCount}
              </span>
            </div>
            <div
              role="progressbar"
              aria-label="Завершённые шаги адаптации"
              aria-valuenow={doneCount}
              aria-valuemin={0}
              aria-valuemax={totalCount}
              className="h-[10px] rounded-full bg-[#E8ECF2]"
            >
              <div className="h-full rounded-full bg-[#1F4FD1] transition-all" style={{ width: `${progressPercent}%` }} />
            </div>
            {displaySteps.map((step, index) => (
              <div key={step.key} className="flex items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-4 text-[17px]">
                  <Badge tone={step.done ? 'green' : 'gray'}>{step.done ? 'Пройдено' : 'Не начато'}</Badge>
                  <span>{step.title}{step.min ? ` · ${step.min} мин` : ''}</span>
                </div>
                {step.done ? (
                  <Btn variant="link" onClick={() => activeProgram ? onNavigate('onboarding') : notify(`Повтор модуля: ${step.title}`)}>Повторить</Btn>
                ) : (
                  <Btn onClick={() => activeProgram ? onNavigate('onboarding') : setDemoSteps((prev) => prev.map((item, idx) => (idx === index ? { ...item, done: true } : item)))}>Начать</Btn>
                )}
              </div>
            ))}
          </Card>
          </div>

          <Card className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-[22px] font-bold">Единое окно: мои документы</h2>
              <Btn variant="primary" onClick={() => notify('Подача документа будет добавлена позже')}>Подать документ</Btn>
            </div>
            <p className="text-[16px] text-[#4A5363]">Документы отправляются дистанционно, привозить их в администрацию не нужно</p>
            <div className="flex flex-wrap justify-between items-center gap-3 text-[17px]">
              Справка с места работы
              <span className="flex items-center gap-3">
                <Badge tone="green">Готово</Badge>
                <Btn variant="link" onClick={() => notify('Скачивание документа будет добавлено позже')}>Скачать</Btn>
              </span>
            </div>
            <div className="flex flex-wrap justify-between items-center gap-3 text-[17px]">
              Заявление на отпуск, 15–28 декабря
              <span className="flex items-center gap-3">
                <Badge tone="amber">На согласовании</Badge>
                <Btn variant="link" onClick={() => notify('Просмотр заявления будет добавлен позже')}>Подробнее</Btn>
              </span>
            </div>
          </Card>
        </div>

        <div className="space-y-5">
          <Card className="space-y-4">
            <h2 className="text-[22px] font-bold">Мой наставник</h2>
            <div className="flex items-center gap-3">
              <div aria-hidden="true" className="w-[52px] h-[52px] shrink-0 rounded-full bg-[#E8EEFC] text-[#1F4FD1] font-bold flex items-center justify-center">ОП</div>
              <div>
                <div className="text-[18px] font-bold">Ольга Петрова</div>
                <div className="text-[14px] text-[#4A5363]">Главный специалист, департамент экономики</div>
              </div>
            </div>
            <Btn className="w-full text-left" onClick={() => notify('Переписка с наставником будет добавлена позже')}>Написать наставнику</Btn>
            <div className="pt-1 border-t border-[#E1E5EB]">
              <Btn variant="link" onClick={() => onNavigate('development')}>Цели и план развития →</Btn>
            </div>
          </Card>

          <Card className="space-y-4">
            <h2 className="text-[22px] font-bold">Ближайшие события</h2>
            {[
              ['25', 'Встреча новых сотрудников с главой города'],
              ['27', 'Тест по антикоррупционным требованиям'],
            ].map(([d, t]) => (
              <div key={d} className="flex items-center gap-4">
                <div className="w-[52px] h-[52px] rounded-xl bg-[#FFEFD9] flex flex-col items-center justify-center shrink-0">
                  <span className="text-[20px] font-bold leading-none">{d}</span>
                  <span className="text-[11px] font-bold">НОЯ</span>
                </div>
                <div className="text-[16px]">{t}</div>
              </div>
            ))}
          </Card>

          <Card className="space-y-3">
            <h2 className="text-[22px] font-bold">Вопрос сотруднику по подбору персонала</h2>
            <p className="text-[15px] text-[#4A5363]">Ответ придёт в кабинет в течение рабочего дня</p>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Например: как оформить отгул?"
              className="w-full border border-[#C9D0DB] rounded-xl px-4 py-3 text-[16px] outline-none focus:border-[#1F4FD1]"
            />
            <Btn
              onClick={() => {
                notify(question.trim() ? 'Отправка обращений будет добавлена позже' : 'Введите вопрос');
                if (question.trim()) setQuestion('');
              }}
            >
              Отправить
            </Btn>
          </Card>
        </div>
      </div>
      <Toast message={toast} />
    </div>
  );
};

export default Workspace;
