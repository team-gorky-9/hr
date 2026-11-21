import type { AppMode, PortalRoute } from '../../App';
import type { HRNavTab } from '../hr/HeaderHR';

export type TourRole = AppMode;

export type TourPlacement = 'bottom' | 'top' | 'right' | 'left';

export interface TourNavigationTarget {
  appMode: AppMode;
  portalRoute?: PortalRoute;
  hrTab?: HRNavTab;
  hrAnalyticsView?: 'dashboard' | 'report';
  opkTab?: string;
  employeeTab?: string;
}

export interface TourStep {
  id: string;
  title: string;
  description: string;
  tryAction: string;
  targetSelector: string;
  fallbackSelector?: string;
  preferredPlacement?: TourPlacement;
  navigate: TourNavigationTarget;
}

export interface TourRoleMeta {
  id: TourRole;
  title: string;
  shortLabel: string;
  description: string;
  accentBg: string;
  accentText: string;
}

export const TOUR_ROLES: TourRoleMeta[] = [
  {
    id: 'portal',
    title: 'Соискатель и студент',
    shortLabel: 'Соискатель и студент',
    description:
      'Карьерный портал, поиск вакансий, подача отклика, раздел «Студентам» и личный кабинет кандидата',
    accentBg: 'bg-[#EEF3FE]',
    accentText: 'text-[#1F4FD1]',
  },
  {
    id: 'hr',
    title: 'Сотрудник по подбору персонала (HR)',
    shortLabel: 'HR-специалист',
    description:
      'Единая база, светофор откликов с проверкой цитат, гайд телефонного интервью, архив, оформление и годовой доклад Excel',
    accentBg: 'bg-[#E6F4EA]',
    accentText: 'text-[#137333]',
  },
  {
    id: 'dept',
    title: 'Руководитель подразделения (ОПК)',
    shortLabel: 'Руководитель ОПК',
    description:
      'Кандидаты на рассмотрении, контроль срока 10 рабочих дней, обратная связь и аналитика',
    accentBg: 'bg-[#FFF4E5]',
    accentText: 'text-[#B45309]',
  },
  {
    id: 'employee',
    title: 'Действующий сотрудник',
    shortLabel: 'Сотрудник',
    description:
      'Рабочее пространство, адаптация и ИПР, материальная помощь, анонимные опросы и забота',
    accentBg: 'bg-[#F1EDFF]',
    accentText: 'text-[#5B3FC4]',
  },
];

export const TOUR_STEPS: Record<TourRole, TourStep[]> = {
  portal: [
    {
      id: 'portal-hero',
      title: 'Карьерный портал и единый поиск вакансий',
      description:
        'Это публичная точка входа для жителей и выпускников. Портал снимает барьер закрытости муниципальной службы: все открытые вакансии администрации и быстрый поиск по навыкам собраны на одном экране.',
      tryAction:
        'Введите в строку поиска должность или навык (например, «аналитик») или нажмите «Найти вакансии».',
      targetSelector: '[data-tour="portal-hero"]',
      preferredPlacement: 'bottom',
      navigate: { appMode: 'portal', portalRoute: 'home' },
    },
    {
      id: 'portal-new-vacancies',
      title: 'Свежие вакансии из единого каталога',
      description:
        'Карточки подтягиваются напрямую из утверждённых публикаций кадровой службы без ручного дублирования. Внутри каждой карточки отображаются обязанности, обязательные требования, условия и форма отклика с согласием по 152-ФЗ.',
      tryAction:
        'Нажмите «Подробнее →» на любой карточке, чтобы увидеть описание позиции и форму отклика.',
      targetSelector: '[data-tour="portal-vacancies-preview"]',
      preferredPlacement: 'top',
      navigate: { appMode: 'portal', portalRoute: 'home' },
    },
    {
      id: 'portal-vacancies-catalog',
      title: 'Полный каталог и структурированный отклик',
      description:
        'В каталоге собраны все опубликованные вакансии администрации с мгновенной фильтрацией по названию и департаменту. Отклик соискателя сразу попадает в единый рабочий контур сотрудника по подбору персонала.',
      tryAction:
        'Попробуйте отфильтровать список по ключевому слову или откройте карточку вакансии.',
      targetSelector: '[data-tour="portal-vacancies-preview"]',
      preferredPlacement: 'bottom',
      navigate: { appMode: 'portal', portalRoute: 'vacancies' },
    },
    {
      id: 'portal-students',
      title: 'Раздел «Студентам»: практика и стажировки',
      description:
        'Отдельный контур для студентов вузов с реальными задачами подразделений и назначенным наставником. Это заменяет формальную практику «для галочки» и формирует приток молодых специалистов в администрацию.',
      tryAction:
        'Нажмите «Откликнуться» на любом месте практики, чтобы посмотреть форму заявки, или пролистайте до блока «Моя практика».',
      targetSelector: '[data-tour="students-opportunities"]',
      fallbackSelector: '[data-tour="students-hero"]',
      preferredPlacement: 'bottom',
      navigate: { appMode: 'portal', portalRoute: 'students' },
    },
    {
      id: 'portal-cabinet',
      title: 'Личный кабинет кандидата «Мои отклики»',
      description:
        'Кандидат видит все свои обращения, статусы рассмотрения и шаги оформления при выходе на работу в одном окне. Больше не нужно дозваниваться в отдел кадров, чтобы узнать судьбу поданного резюме.',
      tryAction:
        'Переключитесь между вкладками «Обращения» и «Оформление», чтобы посмотреть этапы взаимодействия с кадровой службой.',
      targetSelector: '[data-tour="hiring-tabs"]',
      fallbackSelector: '[data-tour="hiring-workspace"]',
      preferredPlacement: 'bottom',
      navigate: { appMode: 'portal', portalRoute: 'cabinet' },
    },
  ],

  hr: [
    {
      id: 'hr-database',
      title: 'Единая база кандидатов и контроль сроков',
      description:
        'Все источники — HH.ru, «Работа России», сайт администрации, студенты, архив кадров и внутренняя ротация — сведены в одну таблицу. Правая колонка автоматически контролирует срок ответа подразделения, чтобы кандидаты не терялись.',
      tryAction:
        'Отфильтруйте таблицу по типу или источнику либо нажмите на код кандидата / «Смотреть оценку», чтобы открыть его профиль.',
      targetSelector: '[data-tour="hr-database-filters"]',
      fallbackSelector: '[data-tour="hr-database-table"]',
      preferredPlacement: 'bottom',
      navigate: { appMode: 'hr', hrTab: 'database' },
    },
    {
      id: 'hr-responses-traffic-light',
      title: 'Светофор откликов, проверка цитат и гайд интервью',
      description:
        'Система раскладывает отклики по группам относительно утверждённого профиля: «Готов к звонку», «Нужно уточнить», «Формально не проходит». Это убирает ручной разбор однотипных резюме и сразу подсвечивает спорные критерии.',
      tryAction:
        'Переключите вкладки светофора или нажмите «Открыть» в строке кандидата — внутри доступны цитаты из резюме и генерация гайда телефонного интервью.',
      targetSelector: '[data-tour="hr-responses-traffic-light"]',
      fallbackSelector: '[data-tour="hr-responses-board"]',
      preferredPlacement: 'bottom',
      navigate: { appMode: 'hr', hrTab: 'vacancies' },
    },
    {
      id: 'hr-requirements',
      title: 'Требования, согласование профиля и публикация вакансий',
      description:
        'Единый процесс от должностной инструкции до утверждённого профиля должности и публикации вакансии на портале. Именно на утверждённую версию профиля опираются светофор откликов и вопросы телефонного интервью.',
      tryAction:
        'Выберите любую редакцию требований в левой колонке или переключитесь на вкладку «Публикация вакансий».',
      targetSelector: '[data-tour="hr-requirements-nav"]',
      fallbackSelector: '[data-tour="hr-requirements-workspace"]',
      preferredPlacement: 'bottom',
      navigate: { appMode: 'hr', hrTab: 'requirements' },
    },
    {
      id: 'hr-archive',
      title: 'Архив кадров и повторное рассмотрение с цитатой',
      description:
        'Поиск по прошлым откликам и действующим подборкам под новую вакансию по смыслу и ключевым словам. Для каждого найденного кандидата система показывает точную цитату из резюме, историю прежних рассмотрений и фиксирует согласие на повторный контакт.',
      tryAction:
        'Выберите целевую вакансию, введите нужный опыт (например, «анализ») и нажмите «Найти кандидатов».',
      targetSelector: '[data-tour="hr-archive-search"]',
      preferredPlacement: 'bottom',
      navigate: { appMode: 'hr', hrTab: 'archive' },
    },
    {
      id: 'hr-hiring',
      title: 'Оформление кандидата до выхода на работу',
      description:
        'Сопровождение всех шагов от обращения кандидата до подтверждённого начала работы: проверка комплекта документов, статусы согласования и контрольные точки собраны в едином деле без разрозненных переписок.',
      tryAction:
        'Переключитесь между вкладками «Обращения» и «Оформление», чтобы просмотреть дела кандидатов.',
      targetSelector: '[data-tour="hiring-tabs"]',
      fallbackSelector: '[data-tour="hiring-workspace"]',
      preferredPlacement: 'bottom',
      navigate: { appMode: 'hr', hrTab: 'hiring' },
    },
    {
      id: 'hr-annual-report',
      title: 'Годовой кадровый доклад и выгрузка Excel (XLSX)',
      description:
        'Воспроизводимый годовой снимок по найму, штату, срокам ответов подразделений и полноте источников данных. В один клик выгружается готовый Excel-файл, а переключателем выше доступен оперативный дашборд «Аналитика подбора».',
      tryAction:
        'Нажмите «Скачать годовой XLSX», откройте вкладки «Конструктор среза» и «Штат и ответы подразделений» или переключитесь на «Аналитика подбора».',
      targetSelector: '[data-tour="report-header"]',
      fallbackSelector: '[data-tour="hr-analytics-switcher"]',
      preferredPlacement: 'bottom',
      navigate: { appMode: 'hr', hrTab: 'analytics', hrAnalyticsView: 'report' },
    },
  ],

  dept: [
    {
      id: 'dept-candidates-list',
      title: 'Направленные кандидаты и контроль 10 рабочих дней',
      description:
        'Руководитель подразделения видит только кандидатов, переданных именно в его департамент. Возле каждой карточки виден крайний срок ответа по регламенту 10 рабочих дней и явная индикация просрочки.',
      tryAction:
        'Кликните по разным кандидатам в левом списке, чтобы сравнить их сроки и статусы рассмотрения.',
      targetSelector: '[data-tour="dept-candidates-list"]',
      fallbackSelector: '[data-tour="dept-page"]',
      preferredPlacement: 'right',
      navigate: { appMode: 'dept', opkTab: 'mine' },
    },
    {
      id: 'dept-candidate-summary',
      title: 'Очищенная сводка кандидата без лишних бумаг',
      description:
        'Вместо разрозненных резюме в почте руководитель получает структурированную сводку от HR: опыт, соответствие требованиям вакансии и результаты первичного скрининга.',
      tryAction:
        'Прокрутите сводку выбранного кандидата, чтобы оценить ключевые аргументы для приглашения на собеседование.',
      targetSelector: '[data-tour="dept-candidate-summary"]',
      fallbackSelector: '[data-tour="dept-candidate-detail"]',
      preferredPlacement: 'left',
      navigate: { appMode: 'dept', opkTab: 'mine' },
    },
    {
      id: 'dept-feedback-form',
      title: 'Структурированная обратная связь для HR',
      description:
        'Решение подразделения фиксируется прямо в передаче: подошёл ли кандидат, состоялось ли собеседование и причина отказа. Сохранение ответа автоматически закрывает регламентный срок и передаёт итог в HR.',
      tryAction:
        'Ознакомьтесь с полями формы («Результат», «Собеседование состоялось», комментарий) — всё фиксируется в истории передачи.',
      targetSelector: '[data-tour="dept-feedback-form"]',
      fallbackSelector: '[data-tour="dept-candidate-detail"]',
      preferredPlacement: 'top',
      navigate: { appMode: 'dept', opkTab: 'mine' },
    },
    {
      id: 'dept-analytics',
      title: 'Аналитика подбора и дисциплина ответов',
      description:
        'Подразделение видит воронку по своим вакансиям, источники откликов, причины отказов и соблюдение сроков ответа за любой период. Рядом доступен «Годовой доклад» с выгрузкой Excel.',
      tryAction:
        'Переключите период («Неделя / Месяц / Квартал / Год»), выберите вакансию или откройте «Годовой доклад» выше.',
      targetSelector: '[data-tour="analytics-header"]',
      fallbackSelector: '[data-tour="dept-analytics-switcher"]',
      preferredPlacement: 'bottom',
      navigate: { appMode: 'dept', opkTab: 'analytics', hrAnalyticsView: 'dashboard' },
    },
  ],

  employee: [
    {
      id: 'employee-workspace',
      title: 'Рабочее пространство и адаптация сотрудника',
      description:
        'Единый кабинет действующего сотрудника: программа адаптации с прогрессом ознакомления, карточка наставника и быстрый переход к кадровым сервисам. Новый сотрудник всегда понимает свои ближайшие шаги.',
      tryAction:
        'Посмотрите список шагов адаптации и кнопку «Открыть программу» — или блок «Развитие» справа.',
      targetSelector: '[data-tour="employee-onboarding-card"]',
      fallbackSelector: '[data-tour="employee-workspace-hero"]',
      preferredPlacement: 'right',
      navigate: { appMode: 'employee', employeeTab: 'workspace' },
    },
    {
      id: 'employee-development',
      title: 'Индивидуальное развитие и ИПР (цели и планы)',
      description:
        'Сотрудник формулирует личные профессиональные цели, согласовывает план развития (ИПР) с руководителем и предъявляет подтверждённые результаты работы. Личные цели остаются приватными до явной передачи руководителю.',
      tryAction:
        'Выберите существующий план или цель слева либо посмотрите форму создания новой личной цели справа.',
      targetSelector: '[data-tour="employee-development-grid"]',
      fallbackSelector: '[data-tour="employee-development-page"]',
      preferredPlacement: 'top',
      navigate: { appMode: 'employee', employeeTab: 'development' },
    },
    {
      id: 'employee-support',
      title: 'Материальная помощь — прозрачное дело от подачи до решения',
      description:
        'Цифровая подача заявления на материальную помощь с прикреплением документов, проверкой комплекта, личной выпиской по решению и полной историей. Убирает бумажную волокиту и потерю справок между отделами.',
      tryAction:
        'Выберите дело из списка слева, чтобы посмотреть историю и выписку, или переключите учебную роль в списке выше.',
      targetSelector: '[data-tour="employee-support-toolbar"]',
      fallbackSelector: '[data-tour="employee-support-page"]',
      preferredPlacement: 'bottom',
      navigate: { appMode: 'employee', employeeTab: 'support' },
    },
    {
      id: 'employee-surveys',
      title: 'Анонимные опросы с защитой приватности',
      description:
        'Опросы принимаются по одноразовому коду без привязки к учётной записи, а результаты малых групп автоматически скрываются правилами публикации. Это повышает доверие сотрудников и честность обратной связи.',
      tryAction:
        'Переключитесь в правой колонке между текущим опросом и завершённым опросом с опубликованными итогами.',
      targetSelector: '[data-tour="employee-surveys-workspace"]',
      fallbackSelector: '[data-tour="employee-surveys-hero"]',
      preferredPlacement: 'top',
      navigate: { appMode: 'employee', employeeTab: 'surveys' },
    },
    {
      id: 'employee-care',
      title: 'Забота и мотивация сотрудников',
      description:
        'Витрина программ психологической поддержки, спорта, семейных мероприятий и обучения для сотрудников администрации. Помогает снижать выгорание и вовлекать коллектив в жизнь организации.',
      tryAction:
        'Попереключайте фильтры категорий («Психологическая поддержка», «Спорт», «Обучение») или нажмите «Открыть материальную помощь».',
      targetSelector: '[data-tour="employee-care-filters"]',
      fallbackSelector: '[data-tour="employee-care-hero"]',
      preferredPlacement: 'bottom',
      navigate: { appMode: 'employee', employeeTab: 'care' },
    },
  ],
};
