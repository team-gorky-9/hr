import React, { useState } from 'react';

export type CandidateCardKey = 'r1' | 'r2' | 'r3' | 'r4' | 'r5' | 'r6';

interface CandidateCardProps {
  candidateId?: string;
  initialLoading?: boolean;
  onBack?: () => void;
  onRequestClarification?: () => void;
  onReject?: () => void;
  onSendToHead?: () => void;
  onSaveToReserve?: () => void;
  onManualCheck?: () => void;
  onReevaluate?: () => void;
}

interface CandidateDetailData {
  id: string;
  fullName: string;
  roleDept: string;
  sourceDate: string;
  contacts: string;
  statusBanner: {
    type: 'amber' | 'green' | 'red' | 'blue';
    title: string;
    text: string;
  };
  mandatoryRequirement: {
    statusBadge: 'Нужно уточнить' | 'Выполнено' | 'Не выполнено' | 'Не оценено';
    badgeColor: 'amber' | 'green' | 'red' | 'gray';
    text: string;
    hasAskButton?: boolean;
  };
  competency: {
    title: string;
    badgeText: 'Цитата найдена' | 'Цитата не найдена' | 'Не оценено';
    badgeColor: 'green' | 'red' | 'gray';
    text: string;
  };
  actionBar: {
    hint: string;
    primaryButton: string;
    primaryAction: 'clarify' | 'forward' | 'reject' | 'manual' | 'reevaluate' | 'retry';
    secondaryButton?: string;
    secondaryAction?: 'reject' | 'reserve' | 'clarify' | 'manual';
  };
  cleanedText: {
    hasSourceError?: boolean;
    sourceErrorTitle?: string;
    sourceErrorText?: string;
    hasV2Notice?: boolean;
    v2NoticeTitle?: string;
    v2NoticeText?: string;
    lines: { text: string; isMarked?: boolean }[];
    caption: string;
  };
}

const candidateDataMap: Record<string, CandidateDetailData> = {
  // МАКЕТ 6: Фролов Денис Андреевич (Карточка_ нужно уточнить.png)
  r1: {
    id: 'r1',
    fullName: 'Фролов Денис Андреевич',
    roleDept: 'Python-разработчик · департамент цифрового развития',
    sourceDate: 'Источник: HH.ru · 18.11.2026',
    contacts: '+7 910 384-21-55 · d.frolov@mail.ru',
    statusBanner: {
      type: 'amber',
      title: 'Нужно уточнить 1 обязательное требование',
      text: 'Прежде чем передавать отклик руководителю, спросите кандидата о длительности коммерческого опыта.',
    },
    mandatoryRequirement: {
      statusBadge: 'Нужно уточнить',
      badgeColor: 'amber',
      text: 'В тексте нет длительности коммерческого опыта. Это не значит, что опыта нет.',
      hasAskButton: true,
    },
    competency: {
      title: 'Автоматизированное тестирование API',
      badgeText: 'Цитата найдена',
      badgeColor: 'green',
      text: 'Оценка 85 · ожидаемый уровень 70–100 · «Написал API-тесты для сервиса заявок.»',
    },
    actionBar: {
      hint: 'ИИ подсказывает, решение принимает HR-менеджер',
      primaryButton: 'Запросить уточнение',
      primaryAction: 'clarify',
      secondaryButton: 'Отклонить с причиной',
      secondaryAction: 'reject',
    },
    cleanedText: {
      lines: [
        { text: 'Написал API-тесты для сервиса заявок.', isMarked: true },
      ],
      caption: 'Цитата совпадает с текстом дословно',
    },
  },

  // МАКЕТ 7: Ковалёва Анна Сергеевна (Карточка_ выполнено.png)
  r2: {
    id: 'r2',
    fullName: 'Ковалёва Анна Сергеевна',
    roleDept: 'Python-разработчик · департамент цифрового развития',
    sourceDate: 'Источник: «Работа России» · 18.11.2026',
    contacts: '+7 920 115-07-43 · a.kovaleva@yandex.ru',
    statusBanner: {
      type: 'green',
      title: 'Обязательное требование выполнено',
      text: 'Отклик можно передать руководителю департамента. Решение о собеседовании принимает он.',
    },
    mandatoryRequirement: {
      statusBadge: 'Выполнено',
      badgeColor: 'green',
      text: 'Найдено в тексте: 3 года при требовании от 2 лет. · «Общий коммерческий опыт — 3 года.»',
      hasAskButton: false,
    },
    competency: {
      title: 'Автоматизированное тестирование API',
      badgeText: 'Цитата найдена',
      badgeColor: 'green',
      text: 'Оценка 85 · ожидаемый уровень 70–100 · «Написал API-тесты для сервиса заявок.»',
    },
    actionBar: {
      hint: 'ИИ подсказывает, решение принимает HR-менеджер',
      primaryButton: 'Передать руководителю',
      primaryAction: 'forward',
      secondaryButton: 'Отклонить с причиной',
      secondaryAction: 'reject',
    },
    cleanedText: {
      lines: [
        { text: 'Написал API-тесты для сервиса заявок.', isMarked: false },
        { text: 'Общий коммерческий опыт — 3 года.', isMarked: true },
      ],
      caption: 'Цитата совпадает с текстом дословно',
    },
  },

  // МАКЕТ 8: Морозов Илья Викторович (Карточка_ не выполнено.png)
  r3: {
    id: 'r3',
    fullName: 'Морозов Илья Викторович',
    roleDept: 'Python-разработчик · департамент цифрового развития',
    sourceDate: 'Источник: Сайт администрации · 18.11.2026',
    contacts: '+7 903 652-90-18 · morozov.ilya@gmail.com',
    statusBanner: {
      type: 'red',
      title: 'Обязательное требование не выполнено',
      text: 'Оценка 85 по тестированию API этого не меняет. Сильную компетенцию можно сохранить в кадровый резерв.',
    },
    mandatoryRequirement: {
      statusBadge: 'Не выполнено',
      badgeColor: 'red',
      text: 'Найдено в тексте: 1 год при требовании от 2 лет. · «Общий коммерческий опыт — 1 год.»',
      hasAskButton: false,
    },
    competency: {
      title: 'Автоматизированное тестирование API',
      badgeText: 'Цитата найдена',
      badgeColor: 'green',
      text: 'Оценка 85 · ожидаемый уровень 70–100 · «Написал API-тесты для сервиса заявок.»',
    },
    actionBar: {
      hint: 'ИИ подсказывает, решение принимает HR-менеджер',
      primaryButton: 'Отклонить с причиной',
      primaryAction: 'reject',
      secondaryButton: 'Сохранить в кадровый резерв',
      secondaryAction: 'reserve',
    },
    cleanedText: {
      lines: [
        { text: 'Написал API-тесты для сервиса заявок.', isMarked: false },
        { text: 'Общий коммерческий опыт — 1 год.', isMarked: true },
      ],
      caption: 'Цитата совпадает с текстом дословно',
    },
  },

  // МАКЕТ 9: Белова Ольга Николаевна (Карточка_ цитата не найдена.png)
  r4: {
    id: 'r4',
    fullName: 'Белова Ольга Николаевна',
    roleDept: 'Python-разработчик · департамент цифрового развития',
    sourceDate: 'Источник: HH.ru · 18.11.2026',
    contacts: '+7 915 241-66-02 · o.belova@mail.ru',
    statusBanner: {
      type: 'blue',
      title: 'Один вывод не подтверждён текстом',
      text: 'Система не нашла цитату в отклике и не считает навык доказанным. Проверьте текст сами.',
    },
    mandatoryRequirement: {
      statusBadge: 'Нужно уточнить',
      badgeColor: 'amber',
      text: 'В тексте нет длительности коммерческого опыта.',
      hasAskButton: true,
    },
    competency: {
      title: 'Автоматизированное тестирование API',
      badgeText: 'Цитата не найдена',
      badgeColor: 'red',
      text: 'Оценка не засчитана: нет подтверждения в тексте · «Руководил командой»',
    },
    actionBar: {
      hint: 'ИИ подсказывает, решение принимает HR-менеджер',
      primaryButton: 'Проверить вручную',
      primaryAction: 'manual',
      secondaryButton: 'Запросить уточнение',
      secondaryAction: 'clarify',
    },
    cleanedText: {
      hasSourceError: true,
      sourceErrorTitle: 'Источник недоступен',
      sourceErrorText: 'Фраза «Руководил командой» не найдена в тексте отклика. Вывод не подтверждён, проверьте вручную.',
      lines: [
        { text: 'Написал API-тесты для сервиса заявок.', isMarked: false },
      ],
      caption: 'Основание вывода не найдено',
    },
  },

  // МАКЕТ 10: Соколов Артём Дмитриевич (Карточка_ оценка устарела.png)
  r5: {
    id: 'r5',
    fullName: 'Соколов Артём Дмитриевич',
    roleDept: 'Python-разработчик · департамент цифрового развития',
    sourceDate: 'Источник: Почта · 18.11.2026',
    contacts: '+7 930 707-31-84 · sokolov.a@yandex.ru',
    statusBanner: {
      type: 'blue',
      title: 'Текст отклика изменился после оценки',
      text: 'Кандидат прислал новую версию резюме. Старая оценка скрыта, чтобы не вводить в заблуждение.',
    },
    mandatoryRequirement: {
      statusBadge: 'Не оценено',
      badgeColor: 'gray',
      text: 'Оценка по старой версии текста не показывается.',
      hasAskButton: false,
    },
    competency: {
      title: 'Автоматизированное тестирование API',
      badgeText: 'Не оценено',
      badgeColor: 'gray',
      text: 'Оценка не проводилась',
    },
    actionBar: {
      hint: 'ИИ подсказывает, решение принимает HR-менеджер',
      primaryButton: 'Оценить заново',
      primaryAction: 'reevaluate',
    },
    cleanedText: {
      hasV2Notice: true,
      v2NoticeTitle: 'Новая версия текста (v2)',
      v2NoticeText: 'Прежняя оценка делалась по версии v1 и скрыта.',
      lines: [
        { text: 'Написал API-тесты для сервиса заявок.', isMarked: false },
        { text: 'Общий коммерческий опыт — 3 года.', isMarked: false },
      ],
      caption: 'Нажмите «Показать в тексте» у вывода, чтобы увидеть основание',
    },
  },

  // МАКЕТ 11: Кузнецова Мария Алексеевна (Карточка_ не оценено, сбой сервиса.png)
  r6: {
    id: 'r6',
    fullName: 'Кузнецова Мария Алексеевна',
    roleDept: 'Python-разработчик · департамент цифрового развития',
    sourceDate: 'Источник: HH.ru · 18.11.2026',
    contacts: '+7 908 199-45-27 · m.kuznetsova@mail.ru',
    statusBanner: {
      type: 'blue',
      title: 'Отклик ещё не оценён: сервис анализа недоступен',
      text: 'Это не «нужно уточнить»: писать кандидату не нужно. Повторите оценку позже или разберите отклик вручную.',
    },
    mandatoryRequirement: {
      statusBadge: 'Не оценено',
      badgeColor: 'gray',
      text: 'Оценка не проводилась.',
      hasAskButton: false,
    },
    competency: {
      title: 'Автоматизированное тестирование API',
      badgeText: 'Не оценено',
      badgeColor: 'gray',
      text: 'Оценка не проводилась',
    },
    actionBar: {
      hint: 'ИИ подсказывает, решение принимает HR-менеджер',
      primaryButton: 'Повторить оценку',
      primaryAction: 'retry',
      secondaryButton: 'Разобрать вручную',
      secondaryAction: 'manual',
    },
    cleanedText: {
      lines: [
        { text: 'Написал API-тесты для сервиса заявок.', isMarked: false },
      ],
      caption: 'Нажмите «Показать в тексте» у вывода, чтобы увидеть основание',
    },
  },
};

export const CandidateCard: React.FC<CandidateCardProps> = ({
  candidateId = 'r1',
  initialLoading = false,
  onBack,
  onRequestClarification,
  onReject,
  onSendToHead,
  onSaveToReserve,
  onManualCheck,
  onReevaluate,
}) => {
  const [activeCandidateKey, setActiveCandidateKey] = useState<string>(candidateId);
  const [isLoading, setIsLoading] = useState<boolean>(initialLoading);
  const [modalAction, setModalAction] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const candidate = candidateDataMap[activeCandidateKey] || candidateDataMap['r1'];

  const triggerToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const handlePrimaryClick = () => {
    switch (candidate.actionBar.primaryAction) {
      case 'clarify':
        if (onRequestClarification) onRequestClarification();
        else setModalAction('Запрос на уточнение');
        break;
      case 'forward':
        if (onSendToHead) onSendToHead();
        else setModalAction('Передача руководителю департамента');
        break;
      case 'reject':
        if (onReject) onReject();
        else setModalAction('Отклонение отклика с указанием причины');
        break;
      case 'manual':
        if (onManualCheck) onManualCheck();
        else {
          triggerToast('Режим ручной проверки активирован');
        }
        break;
      case 'reevaluate':
        if (onReevaluate) onReevaluate();
        else {
          setIsLoading(true);
          setTimeout(() => {
            setIsLoading(false);
            triggerToast('Отклик успешно переоценён');
          }, 1000);
        }
        break;
      case 'retry':
        setIsLoading(true);
        setTimeout(() => {
          setIsLoading(false);
          triggerToast('Сервис анализа завершил оценку');
        }, 1000);
        break;
    }
  };

  const handleSecondaryClick = () => {
    if (!candidate.actionBar.secondaryAction) return;
    switch (candidate.actionBar.secondaryAction) {
      case 'reject':
        if (onReject) onReject();
        else setModalAction('Отклонение отклика с указанием причины');
        break;
      case 'reserve':
        if (onSaveToReserve) onSaveToReserve();
        else setModalAction('Сохранение в кадровый резерв');
        break;
      case 'clarify':
        if (onRequestClarification) onRequestClarification();
        else setModalAction('Запрос на уточнение');
        break;
      case 'manual':
        triggerToast('Переход к ручному разбору отклика');
        break;
    }
  };

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-6">
      {/* Top Navigation Row: Back Link & Quick Mockup Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <button
          type="button"
          onClick={onBack}
          className="text-[14px] font-medium text-[#1F4FD1] hover:underline flex items-center gap-1.5 transition-colors whitespace-nowrap"
        >
          ← Отклики · Python-разработчик
        </button>

        {/* Quick Mockup Switcher for convenience (Экраны 6–12) */}
        <div className="flex flex-wrap items-center gap-1 bg-white border border-[#E1E5EB] rounded-lg p-1 text-xs">
          <span className="text-[#8E939D] px-2 font-medium whitespace-nowrap">Макет:</span>
          <button
            type="button"
            onClick={() => {
              setIsLoading(false);
              setActiveCandidateKey('r1');
            }}
            className={`px-2.5 py-1 rounded font-medium transition-colors whitespace-nowrap ${
              !isLoading && activeCandidateKey === 'r1'
                ? 'bg-[#1F4FD1] text-white shadow-sm'
                : 'text-[#4A5363] hover:text-[#141A24]'
            }`}
          >
            6. Нужно уточнить
          </button>
          <button
            type="button"
            onClick={() => {
              setIsLoading(false);
              setActiveCandidateKey('r2');
            }}
            className={`px-2.5 py-1 rounded font-medium transition-colors whitespace-nowrap ${
              !isLoading && activeCandidateKey === 'r2'
                ? 'bg-[#1F4FD1] text-white shadow-sm'
                : 'text-[#4A5363] hover:text-[#141A24]'
            }`}
          >
            7. Выполнено
          </button>
          <button
            type="button"
            onClick={() => {
              setIsLoading(false);
              setActiveCandidateKey('r3');
            }}
            className={`px-2.5 py-1 rounded font-medium transition-colors whitespace-nowrap ${
              !isLoading && activeCandidateKey === 'r3'
                ? 'bg-[#1F4FD1] text-white shadow-sm'
                : 'text-[#4A5363] hover:text-[#141A24]'
            }`}
          >
            8. Не выполнено
          </button>
          <button
            type="button"
            onClick={() => {
              setIsLoading(false);
              setActiveCandidateKey('r4');
            }}
            className={`px-2.5 py-1 rounded font-medium transition-colors whitespace-nowrap ${
              !isLoading && activeCandidateKey === 'r4'
                ? 'bg-[#1F4FD1] text-white shadow-sm'
                : 'text-[#4A5363] hover:text-[#141A24]'
            }`}
          >
            9. Цитата не найдена
          </button>
          <button
            type="button"
            onClick={() => {
              setIsLoading(false);
              setActiveCandidateKey('r5');
            }}
            className={`px-2.5 py-1 rounded font-medium transition-colors whitespace-nowrap ${
              !isLoading && activeCandidateKey === 'r5'
                ? 'bg-[#1F4FD1] text-white shadow-sm'
                : 'text-[#4A5363] hover:text-[#141A24]'
            }`}
          >
            10. Оценка устарела
          </button>
          <button
            type="button"
            onClick={() => {
              setIsLoading(false);
              setActiveCandidateKey('r6');
            }}
            className={`px-2.5 py-1 rounded font-medium transition-colors whitespace-nowrap ${
              !isLoading && activeCandidateKey === 'r6'
                ? 'bg-[#1F4FD1] text-white shadow-sm'
                : 'text-[#4A5363] hover:text-[#141A24]'
            }`}
          >
            11. Сбой сервиса
          </button>
          <button
            type="button"
            onClick={() => setIsLoading(!isLoading)}
            className={`px-2.5 py-1 rounded font-medium transition-colors whitespace-nowrap ${
              isLoading
                ? 'bg-[#1F4FD1] text-white shadow-sm'
                : 'text-[#4A5363] hover:text-[#141A24]'
            }`}
          >
            12. Загрузка
          </button>
        </div>
      </div>

      {/* ======================================================== */}
      {/* МАКЕТ 12: ЗАГРУЗКА КАРТОЧКИ (Карточка_ загрузка.png)      */}
      {/* ======================================================== */}
      {isLoading ? (
        <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 lg:p-8 shadow-sm">
          <div className="text-[14px] text-[#616977] mb-5">
            Загружаем карточку отклика...
          </div>
          <div className="space-y-3.5">
            <div className="w-full h-10 bg-[#E5E9F2] rounded-xl animate-pulse"></div>
            <div className="w-full h-20 bg-[#E5E9F2] rounded-xl animate-pulse"></div>
            <div className="w-full h-32 bg-[#E5E9F2] rounded-xl animate-pulse"></div>
            <div className="w-full h-36 bg-[#E5E9F2] rounded-xl animate-pulse"></div>
          </div>
        </div>
      ) : (
        /* ======================================================== */
        /* МАКЕТЫ 6–11: ДЕТАЛЬНЫЙ ПРОСМОТР КАРТОЧКИ                  */
        /* ======================================================== */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column (8 cols) */}
          <div className="lg:col-span-8 space-y-6">
            {/* Card 1: Candidate Header + Status Alert Banner */}
            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mb-5">
                <div>
                  <h1 className="text-[22px] font-bold text-[#141A24] tracking-tight mb-1">
                    {candidate.fullName}
                  </h1>
                  <p className="text-[14px] text-[#4A5363] mb-1">
                    {candidate.roleDept}
                  </p>
                  <p className="text-[13px] text-[#616977]">
                    {candidate.sourceDate}
                  </p>
                </div>
                <div className="text-[13px] text-[#4A5363] font-medium sm:text-right whitespace-nowrap">
                  {candidate.contacts}
                </div>
              </div>

              {/* Status Alert Banner */}
              {candidate.statusBanner.type === 'amber' && (
                <div className="bg-[#FFF6EC] border border-[#F3DDBF] rounded-xl p-4">
                  <h2 className="text-[14px] font-bold text-[#92400E] mb-1">
                    {candidate.statusBanner.title}
                  </h2>
                  <p className="text-[13px] text-[#78350F] leading-relaxed">
                    {candidate.statusBanner.text}
                  </p>
                </div>
              )}

              {candidate.statusBanner.type === 'green' && (
                <div className="bg-[#EBF7EE] border border-[#C6E7D2] rounded-xl p-4">
                  <h2 className="text-[14px] font-bold text-[#166534] mb-1">
                    {candidate.statusBanner.title}
                  </h2>
                  <p className="text-[13px] text-[#14532D] leading-relaxed">
                    {candidate.statusBanner.text}
                  </p>
                </div>
              )}

              {candidate.statusBanner.type === 'red' && (
                <div className="bg-[#FDF2F2] border border-[#F8B4B4] rounded-xl p-4">
                  <h2 className="text-[14px] font-bold text-[#991B1B] mb-1">
                    {candidate.statusBanner.title}
                  </h2>
                  <p className="text-[13px] text-[#7F1D1D] leading-relaxed">
                    {candidate.statusBanner.text}
                  </p>
                </div>
              )}

              {candidate.statusBanner.type === 'blue' && (
                <div className="bg-[#EFF6FF] border border-[#BFDBFE] rounded-xl p-4">
                  <h2 className="text-[14px] font-bold text-[#1E40AF] mb-1">
                    {candidate.statusBanner.title}
                  </h2>
                  <p className="text-[13px] text-[#1E3A8A] leading-relaxed">
                    {candidate.statusBanner.text}
                  </p>
                </div>
              )}
            </div>

            {/* Card 2: Обязательное требование */}
            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
              <div className="mb-4">
                <h2 className="text-[16px] font-bold text-[#141A24] mb-0.5">
                  Обязательное требование
                </h2>
                <p className="text-[13px] text-[#616977]">
                  Из профиля должности. Высокая оценка компетенции его не заменяет.
                </p>
              </div>

              <div className="pt-2">
                <div className="flex items-center justify-between gap-4 mb-2">
                  <span className="font-bold text-[15px] text-[#141A24]">
                    Подтверждённый коммерческий опыт не менее 2 лет
                  </span>
                  <span
                    className={`shrink-0 inline-block px-3 py-1 rounded-full text-[12px] font-medium whitespace-nowrap ${
                      candidate.mandatoryRequirement.badgeColor === 'green'
                        ? 'bg-[#E6F4EA] text-[#15803D]'
                        : candidate.mandatoryRequirement.badgeColor === 'amber'
                        ? 'bg-[#FEF3E6] text-[#B45309]'
                        : candidate.mandatoryRequirement.badgeColor === 'red'
                        ? 'bg-[#FDE8E8] text-[#C5221F]'
                        : 'bg-[#F3F4F6] text-[#4B5563]'
                    }`}
                  >
                    {candidate.mandatoryRequirement.statusBadge}
                  </span>
                </div>
                <p className="text-[13px] text-[#4A5363] mb-4">
                  {candidate.mandatoryRequirement.text}
                </p>
                {candidate.mandatoryRequirement.hasAskButton && (
                  <button
                    type="button"
                    onClick={() => setModalAction('Вопрос кандидату об опыте')}
                    className="px-4 py-2 text-[13px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm whitespace-nowrap"
                  >
                    Спросить кандидата
                  </button>
                )}
              </div>
            </div>

            {/* Card 3: Профессиональная компетенция */}
            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
              <div className="mb-4">
                <h2 className="text-[16px] font-bold text-[#141A24] mb-0.5">
                  Профессиональная компетенция
                </h2>
                <p className="text-[13px] text-[#616977]">
                  Что кандидат делал на практике, по тексту отклика
                </p>
              </div>

              <div className="pt-2">
                <div className="flex items-center justify-between gap-4 mb-2">
                  <span className="font-bold text-[15px] text-[#141A24]">
                    {candidate.competency.title}
                  </span>
                  <span
                    className={`shrink-0 inline-block px-3 py-1 rounded-full text-[12px] font-medium whitespace-nowrap ${
                      candidate.competency.badgeColor === 'green'
                        ? 'bg-[#E6F4EA] text-[#15803D]'
                        : candidate.competency.badgeColor === 'red'
                        ? 'bg-[#FDE8E8] text-[#C5221F]'
                        : 'bg-[#F3F4F6] text-[#4B5563]'
                    }`}
                  >
                    {candidate.competency.badgeText}
                  </span>
                </div>
                <p className="text-[13px] text-[#4A5363]">
                  {candidate.competency.text}
                </p>
              </div>
            </div>

            {/* Card 4: Action Bar */}
            <div className="bg-white border border-[#E1E5EB] rounded-2xl p-4 sm:p-5 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="text-[13px] text-[#616977] text-center sm:text-left">
                {candidate.actionBar.hint}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={handlePrimaryClick}
                  className="px-5 py-2.5 text-[14px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm whitespace-nowrap"
                >
                  {candidate.actionBar.primaryButton}
                </button>
                {candidate.actionBar.secondaryButton && (
                  <button
                    type="button"
                    onClick={handleSecondaryClick}
                    className="px-5 py-2.5 text-[14px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors shadow-sm whitespace-nowrap"
                  >
                    {candidate.actionBar.secondaryButton}
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Right Column (4 cols): Очищенный текст отклика */}
          <div className="lg:col-span-4 bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            <h2 className="text-[16px] font-bold text-[#141A24] mb-1">
              Очищенный текст отклика
            </h2>
            <p className="text-[13px] text-[#616977] mb-4">
              Персональные данные удалены до анализа
            </p>

            {/* Notice for Screen 10 (Новая версия текста v2) */}
            {candidate.cleanedText.hasV2Notice && (
              <div className="bg-[#EFF6FF] border border-[#BFDBFE] rounded-xl p-4 mb-4">
                <h3 className="text-[14px] font-bold text-[#1E40AF] mb-1">
                  {candidate.cleanedText.v2NoticeTitle}
                </h3>
                <p className="text-[13px] text-[#1E3A8A] leading-relaxed">
                  {candidate.cleanedText.v2NoticeText}
                </p>
              </div>
            )}

            {/* Notice for Screen 9 (Источник недоступен) */}
            {candidate.cleanedText.hasSourceError && (
              <div className="bg-[#FDF2F2] border border-[#F8B4B4] rounded-xl p-4 mb-4">
                <h3 className="text-[14px] font-bold text-[#991B1B] mb-1">
                  {candidate.cleanedText.sourceErrorTitle}
                </h3>
                <p className="text-[13px] text-[#7F1D1D] leading-relaxed">
                  {candidate.cleanedText.sourceErrorText}
                </p>
              </div>
            )}

            {/* Resume text box */}
            <div className="bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl p-4 text-[14px] leading-relaxed text-[#141A24] space-y-2.5">
              {candidate.cleanedText.lines.map((line, idx) => (
                <p key={idx}>
                  {line.isMarked ? (
                    <mark className="bg-[#FEF08A] text-[#141A24] px-1.5 py-0.5 rounded font-medium">
                      {line.text}
                    </mark>
                  ) : (
                    line.text
                  )}
                </p>
              ))}
            </div>

            <div className="mt-3 text-[12px] text-[#616977]">
              {candidate.cleanedText.caption}
            </div>
          </div>
        </div>
      )}

      {/* Action Dialog / Modal */}
      {modalAction && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border border-[#E1E5EB]">
            <h2 className="text-[18px] font-bold text-[#141A24] mb-2">
              {modalAction}
            </h2>
            <p className="text-[13px] text-[#616977] mb-4">
              Кандидат: <strong className="text-[#141A24]">{candidate.fullName}</strong>
            </p>
            <div className="mb-5">
              <label className="block text-[12px] font-medium text-[#4A5363] mb-1">
                Комментарий или сообщение
              </label>
              <textarea
                rows={3}
                placeholder="Введите текст сообщения..."
                className="w-full px-3 py-2 text-[14px] border border-[#D2D4D8] rounded-lg focus:outline-none focus:border-[#1F4FD1]"
              />
            </div>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setModalAction(null)}
                className="px-4 py-2 text-[13px] font-medium text-[#4A5363] hover:bg-gray-100 rounded-lg transition-colors"
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={() => {
                  setModalAction(null);
                  triggerToast(`${modalAction} успешно выполнено`);
                }}
                className="px-4 py-2 text-[13px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors"
              >
                Подтвердить
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 bg-[#141A24] text-white text-[13px] px-4 py-2.5 rounded-lg shadow-lg z-50 animate-fade-in flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[#15803D]"></span>
          {toastMessage}
        </div>
      )}
    </div>
  );
};

export default CandidateCard;
