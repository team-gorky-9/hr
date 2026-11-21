import React, { useState } from 'react';

export type ActionState =
  | 'idle' // 13. Профиль кандидата
  | 'forward_form' // 14. Направление в департамент_ форма
  | 'forward_done' // 15. Направление в департамент_ отправлено
  | 'forward_expired' // 15а. Срок ответа департамента истёк
  | 'extend_form' // 15б. Продление срока ответа
  | 'reserve_form' // 16. В архив кадров_ форма
  | 'reserve_done' // 17. В архив кадров_ добавлен
  | 'reject_form' // 18. Отклонить с причиной_ форма
  | 'reject_done'; // 19. Отклонить с причиной_ отправлено

interface CandidateProfileProps {
  initialActionState?: ActionState;
  onBackToDatabase?: () => void;
  onOpenInterview?: () => void;
  onOpenReserve?: () => void;
}

export const CandidateProfile: React.FC<CandidateProfileProps> = ({
  initialActionState = 'idle',
  onBackToDatabase,
  onOpenInterview: _onOpenInterview,
  onOpenReserve,
}) => {
  const [actionState, setActionState] = useState<ActionState>(initialActionState);
  const [rejectReason, setRejectReason] = useState<string>('Не хватает опыта');
  const [offerOtherVacancy, setOfferOtherVacancy] = useState<boolean>(true);
  const [reserveConsent, setReserveConsent] = useState<boolean>(true);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  // Status badge logic based on actionState
  const getStatusBadge = () => {
    switch (actionState) {
      case 'forward_done':
        return (
          <span className="bg-[#EDF3FD] text-[#1F4FD1] px-3 py-1 rounded-full text-[12px] font-medium whitespace-nowrap">
            Ждёт решения департамента
          </span>
        );
      case 'forward_expired':
      case 'extend_form':
        return (
          <span className="bg-[#FDE8E8] text-[#C5221F] px-3 py-1 rounded-full text-[12px] font-medium whitespace-nowrap">
            Просрочен ответ департамента
          </span>
        );
      case 'reserve_done':
        return (
          <span className="bg-[#E6F4EA] text-[#15803D] px-3 py-1 rounded-full text-[12px] font-medium whitespace-nowrap">
            В архиве кадров
          </span>
        );
      case 'reject_done':
        return (
          <span className="bg-[#FDE8E8] text-[#C5221F] px-3 py-1 rounded-full text-[12px] font-medium whitespace-nowrap">
            Не подходит
          </span>
        );
      default:
        return (
          <span className="bg-[#FEF3E6] text-[#B45309] px-3 py-1 rounded-full text-[12px] font-medium whitespace-nowrap">
            Нужно уточнить данные
          </span>
        );
    }
  };

  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 py-6">
      {/* Breadcrumb */}
      <div className="mb-5">
        <nav className="text-[14px] text-[#616977] flex items-center gap-1.5 font-normal">
          <button
            type="button"
            onClick={onBackToDatabase}
            className="hover:text-[#1F4FD1] hover:underline transition-colors"
          >
            Единая база
          </button>
          <span>›</span>
          <span className="text-[#141A24] font-medium">Фролов Денис</span>
        </nav>
      </div>

      {/* Candidate Header Card */}
      <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm mb-6">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div>
            <h1 className="text-[24px] font-bold text-[#141A24] tracking-tight mb-1">
              Фролов Денис Андреевич
            </h1>
            <p className="text-[14px] text-[#4A5363] mb-1">
              Вакансия «Python-разработчик» · департамент цифрового развития
            </p>
            <p className="text-[13px] text-[#616977]">
              Внешний отклик · HH.ru · 18.11.2026
            </p>
          </div>
          <div className="flex flex-col sm:items-end gap-2">
            <span className="text-[13px] text-[#4A5363] font-medium">
              +7 910 384-21-55 · d.frolov@mail.ru
            </span>
            {getStatusBadge()}
          </div>
        </div>
      </div>

      {/* Main Grid: Left blocks (8 cols) + Right blocks (4 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* ======================================================== */}
        {/* LEFT COLUMN (8 cols)                                     */}
        {/* ======================================================== */}
        <div className="lg:col-span-8 space-y-6">
          {/* Card 1: Сравнение с профилем должности */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            <div className="mb-4">
              <h2 className="text-[16px] font-bold text-[#141A24] mb-0.5">
                Сравнение с профилем должности
              </h2>
              <p className="text-[13px] text-[#616977]">
                Профиль: Положение о департаменте цифрового развития и должностная инструкция
              </p>
            </div>

            <div className="border border-[#E1E5EB] rounded-xl overflow-hidden">
              <table className="w-full text-left text-[13px]">
                <thead className="bg-[#FAFBFD] border-b border-[#E1E5EB] text-[#616977] font-medium">
                  <tr>
                    <th className="py-3 px-4 w-[34%]">Требование профиля</th>
                    <th className="py-3 px-4 w-[46%]">Что в резюме</th>
                    <th className="py-3 px-4 w-[20%] text-right sm:text-left">Итог</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E1E5EB]">
                  <tr className="hover:bg-[#F8FAFC]">
                    <td className="py-3.5 px-4 font-medium text-[#141A24]">Высшее образование</td>
                    <td className="py-3.5 px-4 text-[#4A5363]">
                      «Образование: высшее, прикладная информатика»
                    </td>
                    <td className="py-3.5 px-4 text-right sm:text-left">
                      <span className="inline-block px-2.5 py-0.5 rounded-full text-[12px] font-medium bg-[#E6F4EA] text-[#15803D] whitespace-nowrap">
                        Выполнено
                      </span>
                    </td>
                  </tr>
                  <tr className="hover:bg-[#F8FAFC]">
                    <td className="py-3.5 px-4 font-medium text-[#141A24]">
                      Коммерческий опыт не менее 2 лет
                    </td>
                    <td className="py-3.5 px-4 text-[#4A5363]">
                      Длительность не указана
                    </td>
                    <td className="py-3.5 px-4 text-right sm:text-left">
                      <span className="inline-block px-2.5 py-0.5 rounded-full text-[12px] font-medium bg-[#FEF3E6] text-[#B45309] whitespace-nowrap">
                        Нужно уточнить
                      </span>
                    </td>
                  </tr>
                  <tr className="hover:bg-[#F8FAFC]">
                    <td className="py-3.5 px-4 font-medium text-[#141A24]">Тестирование API</td>
                    <td className="py-3.5 px-4 text-[#4A5363]">
                      «Написал API-тесты для сервиса заявок.» оценка 85
                    </td>
                    <td className="py-3.5 px-4 text-right sm:text-left">
                      <span className="inline-block px-2.5 py-0.5 rounded-full text-[12px] font-medium bg-[#E6F4EA] text-[#15803D] whitespace-nowrap">
                        Выполнено
                      </span>
                    </td>
                  </tr>
                  <tr className="hover:bg-[#F8FAFC]">
                    <td className="py-3.5 px-4 font-medium text-[#141A24]">Работа с PostgreSQL</td>
                    <td className="py-3.5 px-4 text-[#4A5363]">Не упоминается</td>
                    <td className="py-3.5 px-4 text-right sm:text-left">
                      <span className="inline-block px-2.5 py-0.5 rounded-full text-[12px] font-medium bg-[#F3F4F6] text-[#4B5563] whitespace-nowrap">
                        Нет данных
                      </span>
                    </td>
                  </tr>
                  <tr className="hover:bg-[#F8FAFC]">
                    <td className="py-3.5 px-4 font-medium text-[#141A24]">
                      Интеграция с ведомственными системами
                    </td>
                    <td className="py-3.5 px-4 text-[#4A5363]">Не упоминается</td>
                    <td className="py-3.5 px-4 text-right sm:text-left">
                      <span className="inline-block px-2.5 py-0.5 rounded-full text-[12px] font-medium bg-[#F3F4F6] text-[#4B5563] whitespace-nowrap">
                        Нет данных
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Card 2: Недостающие данные */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            <h2 className="text-[16px] font-bold text-[#141A24] mb-2">
              Недостающие данные
            </h2>
            <ul className="text-[13px] text-[#4A5363] space-y-1">
              <li>• Длительность общего коммерческого опыта</li>
              <li>• Опыт работы с PostgreSQL</li>
            </ul>
          </div>

          {/* Card 3: Черновик вопросов к телефонному интервью */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            <h2 className="text-[16px] font-bold text-[#141A24] mb-4">
              Черновик вопросов к телефонному интервью
            </h2>

            <div className="space-y-2 text-[13px] text-[#334155] leading-relaxed mb-4">
              <div>1. Расскажите, где и сколько лет вы работали разработчиком.</div>
              <div>2. Какие API-тесты вы писали для сервиса заявок? Какой инструмент использовали?</div>
              <div>3. Был ли опыт с PostgreSQL? Приведите пример задачи.</div>
              <div>4. Почему вас интересует работа в муниципальной службе?</div>
            </div>

            <p className="text-[12px] text-[#616977]">
              Собрано из пробелов в резюме. HR-менеджер может изменить вопросы.
            </p>
          </div>

          {/* Card 4: Психологическое тестирование */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
              <h2 className="text-[16px] font-bold text-[#141A24]">
                Психологическое тестирование
              </h2>
              <span className="text-[12px] text-[#616977]">
                Набор для уровня «ведущая должность»
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
              <div className="bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl p-4">
                <div className="text-[12px] text-[#616977] mb-1">Тест Равена</div>
                <div className="text-[22px] font-bold text-[#141A24] mb-2 leading-none">
                  48 из 60
                </div>
                <span className="inline-block px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-[#E6F4EA] text-[#15803D] whitespace-nowrap">
                  Выше среднего
                </span>
              </div>

              <div className="bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl p-4">
                <div className="text-[12px] text-[#616977] mb-1">Системное мышление</div>
                <div className="text-[22px] font-bold text-[#141A24] mb-2 leading-none">
                  7 из 10
                </div>
                <span className="inline-block px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-[#FEF3E6] text-[#B45309] whitespace-nowrap">
                  Средний
                </span>
              </div>

              <div className="bg-[#F8FAFC] border border-[#E1E5EB] rounded-xl p-4">
                <div className="text-[12px] text-[#616977] mb-1">Стратегическое планирование</div>
                <div className="text-[22px] font-bold text-[#141A24] mb-2 leading-none">
                  6 из 10
                </div>
                <span className="inline-block px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-[#FEF3E6] text-[#B45309] whitespace-nowrap">
                  Средний
                </span>
              </div>
            </div>

            <p className="text-[12px] text-[#616977]">
              Тип личности: аналитик · вывод носит вспомогательный характер
            </p>
          </div>
        </div>

        {/* ======================================================== */}
        {/* RIGHT COLUMN (4 cols): ДЕЙСТВИЯ + ПОДХОДИТ + ИСТОРИЯ    */}
        {/* ======================================================== */}
        <div className="lg:col-span-4 space-y-6">
          {/* Card 1: ДЕЙСТВИЯ (Screens 13, 14, 15, 16, 17, 18, 19) */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            <h2 className="text-[16px] font-bold text-[#141A24] mb-4">Действия</h2>

            {/* МАКЕТ 13: ИСХОДНЫЙ ВИД ДЕЙСТВИЙ */}
            {actionState === 'idle' && (
              <div className="space-y-3">
                <button
                  type="button"
                  onClick={() => setActionState('forward_form')}
                  className="w-full py-2.5 px-4 text-[14px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm text-center"
                >
                  Направить в департамент
                </button>
                <button
                  type="button"
                  onClick={() => setActionState('reserve_form')}
                  className="w-full py-2.5 px-4 text-[14px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors shadow-sm text-center"
                >
                  В архив кадров
                </button>
                <button
                  type="button"
                  onClick={() => setActionState('reject_form')}
                  className="w-full py-2.5 px-4 text-[14px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors shadow-sm text-center"
                >
                  Отклонить с причиной
                </button>
                <p className="text-[12px] text-[#616977] pt-1">
                  ИИ подсказывает, решение принимает человек
                </p>
              </div>
            )}

            {/* МАКЕТ 14: ФОРМА НАПРАВЛЕНИЯ В ДЕПАРТАМЕНТ */}
            {actionState === 'forward_form' && (
              <div className="border border-[#BFDBFE] rounded-xl p-4 bg-[#F8FAFF] space-y-3">
                <div>
                  <label className="block text-[12px] font-medium text-[#4A5363] mb-1">
                    Департамент
                  </label>
                  <input
                    type="text"
                    defaultValue="Департамент цифрового развития"
                    className="w-full px-3 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24] focus:outline-none focus:border-[#1F4FD1]"
                  />
                </div>
                <div>
                  <label className="block text-[12px] font-medium text-[#4A5363] mb-1">
                    Ответственный
                  </label>
                  <input
                    type="text"
                    defaultValue="Андрей Г., директор департамента"
                    className="w-full px-3 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24] focus:outline-none focus:border-[#1F4FD1]"
                  />
                </div>
                <div>
                  <label className="block text-[12px] font-medium text-[#4A5363] mb-1">
                    Срок ответа
                  </label>
                  <input
                    type="text"
                    defaultValue="10 рабочих дней (норма)"
                    className="w-full px-3 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24] focus:outline-none focus:border-[#1F4FD1]"
                  />
                </div>
                <div>
                  <label className="block text-[12px] font-medium text-[#4A5363] mb-1">
                    Комментарий
                  </label>
                  <textarea
                    rows={2}
                    defaultValue="Сильный в тестировании, опыт уточнён по телефону"
                    className="w-full px-3 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24] focus:outline-none focus:border-[#1F4FD1]"
                  />
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => {
                      setActionState('forward_done');
                      showToast('Кандидат направлен в департамент');
                    }}
                    className="flex-1 py-2 text-[13px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm text-center"
                  >
                    Направить
                  </button>
                  <button
                    type="button"
                    onClick={() => setActionState('idle')}
                    className="px-4 py-2 text-[13px] font-medium text-[#4A5363] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors"
                  >
                    Отмена
                  </button>
                </div>
              </div>
            )}

            {/* МАКЕТ 15а: СРОК ОТВЕТА ДЕПАРТАМЕНТА ИСТЁК */}
            {(actionState === 'forward_expired' || actionState === 'extend_form') && (
              <div className="space-y-3">
                {actionState === 'forward_expired' ? (
                  <div className="bg-[#FCE8E8] border border-[#F3B8B8] rounded-xl p-4">
                    <h3 className="text-[14px] font-bold text-[#A3171B] mb-1">Срок ответа департамента истёк</h3>
                    <p className="text-[12px] text-[#A3171B] mb-2">Ответственный: Андрей Г. · срок был до 04.12</p>
                    <div className="h-[6px] rounded-full bg-[#9B1C1C] mb-2" />
                    <p className="text-[12px] text-[#A3171B] leading-relaxed mb-3">
                      Прошло 11 из 10 рабочих дней. Напоминание отправлено 05.12, ответа пока нет.
                    </p>
                    <button
                      type="button"
                      onClick={() => setActionState('extend_form')}
                      className="px-4 py-2 text-[13px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2]"
                    >
                      Продлить и напомнить
                    </button>
                  </div>
                ) : (
                  <div className="border border-[#BFDBFE] rounded-xl p-4 bg-[#F8FAFF] space-y-3">
                    <h3 className="text-[14px] font-bold text-[#141A24]">Продлить срок ответа</h3>
                    <div>
                      <label className="block text-[12px] font-medium text-[#4A5363] mb-1">Новый срок</label>
                      <input
                        type="text"
                        placeholder="11.12.2026 · +5 рабочих дней"
                        className="w-full px-3 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white focus:outline-none focus:border-[#1F4FD1]"
                      />
                    </div>
                    <div>
                      <label className="block text-[12px] font-medium text-[#4A5363] mb-1">Причина продления</label>
                      <input
                        type="text"
                        placeholder="Руководитель в командировке до 08.12"
                        className="w-full px-3 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white focus:outline-none focus:border-[#1F4FD1]"
                      />
                    </div>
                    <p className="text-[12px] text-[#4A5363]">
                      Андрей Г. получит напоминание с новым сроком. Продление попадёт в историю и в аналитику сроков.
                    </p>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setActionState('forward_done');
                          showToast('Срок продлён, напоминание отправлено');
                        }}
                        className="px-4 py-2 text-[13px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2]"
                      >
                        Продлить и напомнить
                      </button>
                      <button
                        type="button"
                        onClick={() => setActionState('forward_expired')}
                        className="px-4 py-2 text-[13px] font-medium text-[#4A5363] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8]"
                      >
                        Отмена
                      </button>
                    </div>
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => setActionState('reserve_form')}
                  className="w-full py-2.5 px-4 text-[14px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] shadow-sm text-center"
                >
                  В архив кадров
                </button>
                <button
                  type="button"
                  onClick={() => setActionState('reject_form')}
                  className="w-full py-2.5 px-4 text-[14px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] shadow-sm text-center"
                >
                  Отклонить с причиной
                </button>
                <p className="text-[12px] text-[#616977] pt-1">ИИ подсказывает, решение принимает человек</p>
              </div>
            )}

            {/* МАКЕТ 15: НАПРАВЛЕНИЕ ОТПРАВЛЕНО */}
            {actionState === 'forward_done' && (
              <div className="space-y-3">
                <div className="bg-[#EBF7EE] border border-[#C6E7D2] rounded-xl p-4">
                  <h3 className="text-[14px] font-bold text-[#166534] mb-1">
                    Направлен в департамент цифрового развития
                  </h3>
                  <p className="text-[12px] text-[#14532D] font-medium mb-2">
                    Ответственный: Андрей Г. · срок ответа до 25.11
                  </p>
                  <p className="text-[12px] text-[#14532D] leading-relaxed">
                    Прошло 0 из 3 дней. Без ответа срок станет жёлтым, потом красным, а ответственному придёт напоминание.
                  </p>
                  <button
                    type="button"
                    onClick={() => setActionState('forward_expired')}
                    className="mt-2 text-[12px] text-[#166534] underline"
                  >
                    Демо: показать истёкший срок (макет 15а)
                  </button>
                </div>

                <button
                  type="button"
                  onClick={() => setActionState('reserve_form')}
                  className="w-full py-2.5 px-4 text-[14px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors shadow-sm text-center"
                >
                  В архив кадров
                </button>
                <button
                  type="button"
                  onClick={() => setActionState('reject_form')}
                  className="w-full py-2.5 px-4 text-[14px] font-medium text-[#141A24] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors shadow-sm text-center"
                >
                  Отклонить с причиной
                </button>
                <p className="text-[12px] text-[#616977] pt-1">
                  ИИ подсказывает, решение принимает человек
                </p>
              </div>
            )}

            {/* МАКЕТ 16: ФОРМА ДОБАВЛЕНИЯ В КАДРОВЫЙ РЕЗЕРВ */}
            {actionState === 'reserve_form' && (
              <div className="space-y-3">
                <div className="border border-[#BFDBFE] rounded-xl p-4 bg-[#F8FAFF] space-y-3">
                  <h3 className="text-[14px] font-bold text-[#141A24]">
                    Перенести резюме в архив кадров
                  </h3>
                  <div>
                    <label className="block text-[12px] font-medium text-[#4A5363] mb-1">
                      Раздел архива
                    </label>
                    <input
                      type="text"
                      defaultValue="Кандидаты департамента цифрового развития"
                      className="w-full px-3 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24] focus:outline-none focus:border-[#1F4FD1]"
                    />
                  </div>
                  <div>
                    <label className="block text-[12px] font-medium text-[#4A5363] mb-1">
                      Целевая должность
                    </label>
                    <input
                      type="text"
                      defaultValue="Python-разработчик, цифровое развитие"
                      className="w-full px-3 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24] focus:outline-none focus:border-[#1F4FD1]"
                    />
                  </div>
                  <div>
                    <label className="block text-[12px] font-medium text-[#4A5363] mb-1">
                      Срок хранения
                    </label>
                    <input
                      type="text"
                      defaultValue="1 год, до 20.11.2027"
                      className="w-full px-3 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24] focus:outline-none focus:border-[#1F4FD1]"
                    />
                  </div>
                  <div>
                    <label className="block text-[12px] font-medium text-[#4A5363] mb-1">
                      Почему в архив
                    </label>
                    <textarea
                      rows={2}
                      defaultValue="Сильный в тестировании API, но сейчас нет свободной ставки"
                      className="w-full px-3 py-2 text-[13px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24] focus:outline-none focus:border-[#1F4FD1]"
                    />
                  </div>
                  <label className="flex items-start gap-2 cursor-pointer pt-1">
                    <input
                      type="checkbox"
                      checked={reserveConsent}
                      onChange={(e) => setReserveConsent(e.target.checked)}
                      className="mt-0.5 rounded text-[#1F4FD1] focus:ring-[#1F4FD1]"
                    />
                    <span className="text-[12px] text-[#4A5363]">
                      Запросить у кандидата согласие на хранение резюме в архиве (152-ФЗ)
                    </span>
                  </label>
                  <div className="flex items-center gap-2 pt-1">
                    <button
                      type="button"
                      onClick={() => {
                        setActionState('reserve_done');
                      }}
                      className="flex-1 py-2 text-[13px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm text-center"
                    >
                      Перенести в архив
                    </button>
                    <button
                      type="button"
                      onClick={() => setActionState('idle')}
                      className="px-4 py-2 text-[13px] font-medium text-[#4A5363] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors"
                    >
                      Отмена
                    </button>
                  </div>
                </div>
                <p className="text-[12px] text-[#616977] pt-1">
                  ИИ подсказывает, решение принимает человек
                </p>
              </div>
            )}

            {/* МАКЕТ 17: В КАДРОВЫЙ РЕЗЕРВ ДОБАВЛЕН */}
            {actionState === 'reserve_done' && (
              <div className="space-y-3">
                <div className="bg-[#EBF7EE] border border-[#C6E7D2] rounded-xl p-4">
                  <h3 className="text-[14px] font-bold text-[#166534] mb-1">
                    Резюме перенесено в архив кадров
                  </h3>
                  <p className="text-[12px] text-[#14532D] font-medium mb-0.5">
                    Python-разработчик, цифровое развитие
                  </p>
                  <p className="text-[12px] text-[#14532D] mb-2">
                    Хранится до 20.11.2027
                  </p>
                  <p className="text-[12px] text-[#14532D] leading-relaxed mb-3">
                    Кандидату отправлен запрос согласия. Когда откроется подходящая вакансия, система напомнит о нём.
                  </p>
                  <button
                    type="button"
                    onClick={onOpenReserve}
                    className="text-[13px] font-medium text-[#1F4FD1] hover:underline"
                  >
                    Открыть архив кадров
                  </button>
                </div>
                <p className="text-[12px] text-[#616977] pt-1">
                  ИИ подсказывает, решение принимает человек
                </p>
              </div>
            )}

            {/* МАКЕТ 18: ФОРМА ОТКЛОНЕНИЯ С ПРИЧИНОЙ */}
            {actionState === 'reject_form' && (
              <div className="border border-[#F8B4B4] rounded-xl p-4 bg-[#FFF5F5] space-y-3">
                <h3 className="text-[14px] font-bold text-[#991B1B]">
                  Отклонить отклик
                </h3>

                <div>
                  <div className="text-[12px] font-medium text-[#4A5363] mb-1.5">
                    Причина
                  </div>
                  <div className="space-y-1.5 text-[13px] text-[#141A24]">
                    {[
                      'Не хватает опыта',
                      'Не та специализация',
                      'Не соответствует квалификации',
                      'Кандидат отказался сам',
                      'Другое',
                    ].map((opt) => (
                      <label key={opt} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="rejectReason"
                          value={opt}
                          checked={rejectReason === opt}
                          onChange={(e) => setRejectReason(e.target.value)}
                          className="text-[#1F4FD1] focus:ring-[#1F4FD1]"
                        />
                        <span>{opt}</span>
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-[12px] font-medium text-[#4A5363] mb-1">
                    Письмо кандидату
                  </label>
                  <textarea
                    rows={3}
                    defaultValue="Спасибо за отклик! Сейчас на эту должность нужен коммерческий опыт от 2 лет. Мы сохраним ваше резюме и сообщим о подходящих вакансиях."
                    className="w-full px-3 py-2 text-[12px] border border-[#D2D4D8] rounded-lg bg-white text-[#141A24] focus:outline-none focus:border-[#1F4FD1]"
                  />
                  <p className="text-[11px] text-[#616977] mt-1">
                    Текст предложил ИИ, проверьте его перед отправкой
                  </p>
                </div>

                <label className="flex items-start gap-2 cursor-pointer pt-1">
                  <input
                    type="checkbox"
                    checked={offerOtherVacancy}
                    onChange={(e) => setOfferOtherVacancy(e.target.checked)}
                    className="mt-0.5 rounded text-[#1F4FD1] focus:ring-[#1F4FD1]"
                  />
                  <span className="text-[12px] text-[#4A5363]">
                    Предложить вакансию «Тестировщик ПО» (совпадение 82%)
                  </span>
                </label>

                <div className="flex items-center gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => {
                      setActionState('reject_done');
                      showToast('Отказ отправлен кандидату');
                    }}
                    className="flex-1 py-2 text-[13px] font-medium text-white bg-[#1F4FD1] rounded-lg hover:bg-[#1841B2] transition-colors shadow-sm text-center"
                  >
                    Отклонить и отправить
                  </button>
                  <button
                    type="button"
                    onClick={() => setActionState('idle')}
                    className="px-4 py-2 text-[13px] font-medium text-[#4A5363] bg-white border border-[#E1E5EB] rounded-lg hover:bg-[#F3F5F8] transition-colors"
                  >
                    Отмена
                  </button>
                </div>
              </div>
            )}

            {/* МАКЕТ 19: ОТКАЗ ОТПРАВЛЕН */}
            {actionState === 'reject_done' && (
              <div className="space-y-3">
                <div className="bg-[#FFF5F5] border border-[#F8B4B4] rounded-xl p-4">
                  <h3 className="text-[14px] font-bold text-[#991B1B] mb-1">
                    Отказ отправлен кандидату
                  </h3>
                  <p className="text-[12px] text-[#7F1D1D] mb-0.5">
                    Причина: {rejectReason.toLowerCase()}
                  </p>
                  <p className="text-[12px] text-[#7F1D1D] mb-2">
                    Письмо в личном кабинете, 20.11 в 13:50
                  </p>
                  <p className="text-[12px] text-[#7F1D1D] leading-relaxed mb-3">
                    Кандидату предложена вакансия «Тестировщик ПО»
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setActionState('idle');
                      showToast('Решение отменено, отклик возвращён');
                    }}
                    className="text-[13px] font-medium text-[#1F4FD1] hover:underline"
                  >
                    Отменить решение
                  </button>
                </div>
                <p className="text-[12px] text-[#616977] pt-1">
                  ИИ подсказывает, решение принимает человек
                </p>
              </div>
            )}
          </div>

          {/* Card 2: Подходит и на другие вакансии */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            <h2 className="text-[16px] font-bold text-[#141A24] mb-4">
              Подходит и на другие вакансии
            </h2>
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <span className="bg-[#EEF3FE] text-[#1F4FD1] text-[12px] font-medium px-2 py-0.5 rounded">
                    82%
                  </span>
                  <span className="text-[14px] font-medium text-[#141A24]">
                    Тестировщик ПО
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => showToast('Вакансия «Тестировщик ПО» предложена')}
                  className="text-[13px] font-medium text-[#1F4FD1] hover:underline"
                >
                  Предложить
                </button>
              </div>

              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <span className="bg-[#EEF3FE] text-[#1F4FD1] text-[12px] font-medium px-2 py-0.5 rounded">
                    74%
                  </span>
                  <span className="text-[14px] font-medium text-[#141A24]">
                    Аналитик данных
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => showToast('Вакансия «Аналитик данных» предложена')}
                  className="text-[13px] font-medium text-[#1F4FD1] hover:underline"
                >
                  Предложить
                </button>
              </div>
            </div>
          </div>

          {/* Card 3: История */}
          <div className="bg-white border border-[#E1E5EB] rounded-2xl p-6 shadow-sm">
            <h2 className="text-[16px] font-bold text-[#141A24] mb-3">История</h2>
            <div className="space-y-2 text-[13px] text-[#4A5363] leading-relaxed">
              <div>18.11 · Отклик получен с HH.ru</div>
              <div>18.11 · ИИ сравнил резюме с профилем должности</div>
              {actionState === 'forward_done' && (
                <div>20.11 · Направлен в департамент, срок 3 дня</div>
              )}
              {actionState === 'reserve_done' && (
                <div>20.11 · Марина С. перенесла резюме в архив кадров</div>
              )}
              {actionState === 'reject_done' && (
                <div>20.11 · Марина С. отклонила: {rejectReason.toLowerCase()}</div>
              )}
            </div>
          </div>
        </div>
      </div>

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

export default CandidateProfile;
