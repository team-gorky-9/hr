# Модуль «Кадровая картина для руководства» (management)

Код — `app/management/`. Контракт — [wave-4-reporting-stage-1](../contracts/wave-4-reporting-stage-1.md). Реализованы 4A (сводка текущей работы), 4B (годовой выпуск из фактов legacy-hr) и 4C (плановый снимок потребностей).

## 4A · `GET /api/v1/management/overview?from=…&to=…&contour=…`

Доступ — только `hr` и `admin` (`X-User-Login`). `department` получает 403. `contour` обязателен. Период: `from` включительно, `to` исключительно, границы суток по Москве. Пустой или обратный период даёт `422 INVALID_PERIOD`.

Пример. В учебном контуре три встречи:
- py-9103 — `continue` 20.11 в 23:59 МСК;
- py-9104 — `no_answer` 20.11 в 10:00;
- py-9105 — `stop` 21.11 в 00:00.

Ещё у py-9106 есть открытая встреча. Запрос `from=2026-11-20&to=2026-11-21`:

| Поле | Значение | Почему |
|---|---|---|
| `interviews.held_count` | 1 | только py-9103; разговор py-9105 в 00:00 уже в следующих сутках |
| `interviews.no_answer_count` | 1 | py-9104, считается по `attempt_at`, к `held_count` не прибавляется |
| `interviews.open_count` | 1 | py-9106, открытая встреча без итога на момент среза |
| `interviews.undated_count` | 0 | встречи с итогом, но без даты, в период не попадают |
| `interviews.by_interviewer` | `hr_demo`: held 1, no_answer 1, outcomes continue 1 | |

- **Воронка.** `funnel` — без изменений существующий `/analytics/funnel` того же контура. Период закрытий в нём включительный, поэтому передаётся `to − 1 день`.
- **Проведённая встреча.** Проведённой считается только встреча с `held_at`. Гайд, вопросы и ответы встречу не завершают. Повторные звонки одного отклика считаются отдельно, `held_applications_count` дедуплицирует их по отклику. Единицы всех счётчиков перечислены в `interviews.units`.
- **Источники.** `sources` показывает доступность журналов. `legacy-hr.applications` и `legacy-hr.interviews` — `available`. `workforce`, `hiring` и `practice` — `unavailable`: в legacy API к ним нет подключения. Пустой журнал подписан «0 зарегистрировано в этом журнале» без заявления о полном охвате. Без полей итога встречи (до миграции 0010) блок интервью — `unavailable`, без счётчиков.

## Запуск

```bash
uv run alembic upgrade head
uv run python -m scripts.demo_setup --no-llm                       # учебные отклики
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 &
uv run python scripts/check_management_overview.py --prepare       # встречи: continue, no_answer, stop, открытая
uv run python scripts/check_management_overview.py                 # сводка за 20.11 и 21.11, отказ department
curl -s 'localhost:8000/api/v1/management/overview?from=2026-11-20&to=2026-11-21&contour=training' -H 'X-User-Login: hr_demo'
```

## 4B · годовой выпуск из доступных фактов

| Метод | Что делает |
|---|---|
| `POST /api/v1/management/annual-reports` | Тело `{year, observed_until, contour, coverage, confirmation_basis}`, ответ 201: `snapshot_id`, `mode`, `year`, `generated_at`, `coverage_summary`, `preparation`, `report_url`, `xlsx_url` |
| `GET /api/v1/management/annual-reports/{snapshot_id}` | `{release, report}`, где `report` — снимок годового модуля в его формате |
| `GET /api/v1/management/annual-reports/{snapshot_id}/xlsx` | Excel из того же снимка |

Доступ — `hr` и `admin`, как у 4A. Читаются только выпуски из реестра `annual_report_releases` (миграция `0012`).

**Как собирается выпуск.**
1. **Отбор фактов.** Берутся отклики площадки (`source=response`) кандидатов выбранного контура и их телефонные встречи.
2. **Пакет.** Сервис пишет обычный входной пакет годового модуля — `manifest.json`, `applications.csv`, `phone_interviews.csv` — во временный каталог внутри `HR_REPORTS_DIR` сервера. Путь клиент не задаёт.
   - Ключи — технические UUID. Дата отклика — `applied_at`, дата разговора — `held_at` по Москве. ФИО, контакты и тексты резюме в пакет не попадают.
   - Факты после `observed_until` в пакет не входят и перечислены в `preparation.skipped`.
   - Отклики без вакансии тоже не входят и тоже перечислены в `preparation.skipped`.
3. **Встречи без даты.** `no_answer` и встречи без `held_at` идут с пустым `held_on`. Годовой модуль не считает их проведёнными, а итоги без даты относит к недатированным. Время запроса вместо даты не подставляется.
4. **Расчёт.** Пакет проверяется тем же `load_package` и считается тем же `generate`, снимок сохраняется тем же `store.save`. Если пакет противоречив, например интервал полноты выходит за `observed_until`, ответ — `422 PREPARATION_FAILED` с кодом загрузчика.
5. **Полнота.** Полноту заявляет HR в `coverage`; по умолчанию интервалов нет, и полнота не обещается. `confirmation_basis` сохраняется в выпуске вместе с автором. Учебный контур даёт `mode=demo`, рабочий — `mode=work`.
6. **Новая версия.** Поздняя поправка источника, например новый итог встречи, при новом POST даёт новый `snapshot_id`. Прежний выпуск читается без изменений.

```bash
export HR_REPORTS_DIR=/srv/hr/annual-reports      # каталог выпусков сервера
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 &
uv run python scripts/check_management_overview.py --prepare   # учебные встречи, если ещё нет
uv run python scripts/check_management_annual.py               # выпуск → JSON → Excel → поправка → новый выпуск
```

## 4C · плановый снимок потребностей

| Метод | Что делает |
|---|---|
| `POST /api/v1/management/plans` | Вход `{target_date, scope_label, needs, people, matches, coverage_note}` — подготовленный HR пакет на одну дату. Ответ 201 — неизменяемый снимок: ввод, автор, отпечаток `input_sha256` и результат |
| `GET /api/v1/management/plans/{id}` | Полная версия с записями и основаниями |
| `GET /api/v1/management/plans/{id}/summary` | Управленческая проекция без имён, `record_ref`, `person_ref`, оснований HR и ссылок на первичные документы |

Доступ — `hr` и `admin`. Хранение — таблица `plan_snapshots` (миграция `0013`). Изменить снимок нельзя: исправление — новый снимок.

**Расчёт.**
1. По каждой потребности считаются записи по классам `confirmed` / `expected` / `similarity` / `unknown`. Класс — заключение HR с основанием. Система его не выводит из поиска, курса или резерва.
2. **Подтверждённое ребро** — класс `confirmed`, подтверждённая личность (`person_ref`) и доступный контакт. Узел графа — человек: две записи одного `person_ref` дают одного человека.
3. **Неучтённые записи.** Запись без `person_ref` видна как `unresolved_records` с предупреждением `unresolved_identity` и в покрытие не входит. Подтверждённые без контакта показываются отдельно (`contact_unavailable`).
4. **Места.** Потребность с `quantity = n` даёт n мест на дату. Все потребности одновременные, один человек закрывает одно место.
5. **Независимое покрытие** — размер максимального паросочетания «место — человек». Считается алгоритмом увеличивающих путей (Куна) со стабильным порядком ключей, без новых зависимостей.
   - Номинальное покрытие — число потребностей хотя бы с одним подтверждённым человеком.
   - Концентрация — люди, указанные для нескольких потребностей (предупреждение называет потребности).
6. **Без назначения.** Конкретное паросочетание не возвращается: оно одно из возможных и не является назначением. По потребности показывается только верхняя граница `upper_bound_covered`.

Пример (`scripts/check_management_plans.py`):

| Ввод | Результат |
|---|---|
| П-1 и П-2 по одному месту, человек А подтверждён для обеих | номинально 2, независимо 1, концентрация П-1/П-2 |
| + человек Б подтверждён только для П-1, выпускник В — `expected` для П-2 | независимо 2: А закрывает П-2, Б — П-1. Жадный выбор «А на П-1» дал бы 1. У П-2 confirmed 1, expected 1 |

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 &
uv run python scripts/check_management_plans.py
```
