# Модуль «Двунаправленный подбор» (matching)

Код — `app/matching/`. Контракт — [wave-3-matching-stage-1](../contracts/wave-3-matching-stage-1.md). Реализованы 3A (люди под выбранную вакансию), 3B (вакансии по присланному резюме) и 3C (сохранённая подборка после публикации).

## Как работает 3A

Пример. HR выбирает опубликованную учебную вакансию «Аналитик ИС» и явно задаёт `search_query` «анализ и согласование требований к ИС».

1. **Проверка доступа.** До поиска проверяются роль (`X-User-Login`: только `hr` и `admin`) и контур. Рабочий контур требует серверный ключ поиска — тот же, что `/api/v1/search`. Закрытая вакансия получает `409 VACANCY_NOT_PUBLISHED`. Профиль из другого контура — `409 CONTOUR_MISMATCH`.
2. **Поиск.** `search_query` уходит в действующий поиск (`app.search.api.run_search`) вместе с `filters` и `limit` из `SearchRequest`. Описание объявления в запрос не подставляется и не обрезается.
3. **Статус оценки.** Для каждой найденной записи ищется актуальная оценка по точному `profile_ref`: legacy-профиль с той же версией и должностью, к тому же действующий утверждённый. Правила те же, что в списке откликов (`resolve_states`). Оценка есть — `qualification_status` равен `met`, `unknown` или `not_met` и приходит `assessment_id`. Иначе — `not_evaluated` с причиной: `no_profile_ref`, `unmapped_profile` (профиль нового Requirements без отображения), `profile_not_found`, `profile_mismatch`, `profile_not_current`, `not_assessed`, `assessment_stale`.
4. **Ответ.** Строки действующего поиска (цитата `evidence`, `applications`, `in_reserve`) плюс поля оценки. Также `source_mode=provided`, `observed_at` из снимка, `unit=candidate_record`, `matching_status=completed`.

Отклики, приглашения и записи резерва не создаются. Ноль совпадений — `200` с `items: []`. Сбой базы — `503 SEARCH_UNAVAILABLE`.

## Запуск и пример

```bash
uv run alembic upgrade head
uv run python -m app.search load-demo                # учебный корпус поиска
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
uv run python scripts/check_matching_candidates.py    # в другом терминале
```

Учебные учётки legacy API: `X-User-Login: hr_demo` / `admin_demo`; `dept_demo` получает 403.

```bash
curl -s -X POST localhost:8000/api/v1/matching/candidates -H 'X-User-Login: hr_demo' \
  -H 'Content-Type: application/json' -d '{
  "vacancy": {"ref": {"system": "legacy-hr", "id": "00000000-0000-4000-8000-0000000000a1"}, "revision": 1,
    "title": "Аналитик ИС (учебная)", "description": "Учебное объявление", "position_code": "analyst-training",
    "status": "published", "contour": "training", "observed_at": "2026-11-21T09:00:00+03:00",
    "profile_ref": null, "search_query": "анализ и согласование требований к ИС"},
  "limit": 3}'
```

Первая строка ответа — `search-9015` с фрагментом «Анализ и согласование требований к ИС при модернизации портала…» и `qualification_status: not_evaluated` (`no_profile_ref`). С `"filters": {"required_terms": ["SAP ERP"]}` выдача пустая.

## Как работает 3B

`POST /api/v1/matching/vacancies` принимает `{candidate_id, contour, vacancies: [VacancySnapshot] (1–50), limit}`. В 3B `search_query` у снимка не нужен.

Пример. Учебный кандидат `match-9001` прислал резюме без вакансии. HR передаёт четыре снимка: python-dev, qa-manual, frontend-dev и закрытую python-dev.

1. **Проверка доступа и контура.** Права и контур — как в 3A. Кандидата нет — `404 CANDIDATE_NOT_FOUND`. Кандидат из другого контура — `409 CONTOUR_MISMATCH`.
2. **Отсев.** Закрытая вакансия или вакансия другого контура попадает в `excluded` только с причиной (`closed` / `other_contour`).
3. **Сопоставление с оценкой.** Остальные вакансии сопоставляются с сохранёнными кросс-оценками (`app.assessment.cross`, та же модель чтения, что `GET /candidates/{id}/cross-assessments`). Совпасть должны id профиля, его версия и код должности. Похожее название не используется.
4. **Готовая оценка.** Вакансия попадает в `items` с `formal_result`, `assessment_id` и `reason`. Основание собирается из сохранённых проверок обязательных требований этапа отбора: «Нет сведений: …», «Не выполнено: …». Порядок — met → unknown → not_met, затем по id публикации.
5. **Оценки нет.** Вакансия попадает в `needs_evaluation` с причиной: `not_assessed`, `assessment_stale` (с `stale_reason`), `no_profile_ref`, `unmapped_profile`, `profile_not_found`, `profile_mismatch` или `profile_not_current`.

Если готовых оценок нет, `items` пуст, а `needs_evaluation` показывает, что проверить. Это не ответ «подходящих вакансий нет». Новые оценки, отклики и вызовы модели не создаются.

Проверка на отдельной пустой учебной базе (подготовка утверждает учебные копии профилей):

```bash
DATABASE_URL=…/hr_match uv run alembic upgrade head
DATABASE_URL=…/hr_match uv run python scripts/check_matching_vacancies.py --prepare
DATABASE_URL=…/hr_match uv run uvicorn app.main:app &
DATABASE_URL=…/hr_match uv run python scripts/check_matching_vacancies.py
```

## Как работает 3C

`POST /api/v1/matching/suggestions` принимает тот же вход, что 3A, и отвечает `201`. `GET /api/v1/matching/suggestions/{id}` перечитывает подборку. Хранение — таблица `matching_suggestions`, миграция `0011`.

Порядок вызовов экрана после публикации вакансии:
1. Опубликовать вакансию в каталоге или взять учебный снимок.
2. `POST /matching/suggestions` с `{vacancy, filters, limit}` → показать `items`, запомнить `id`.
3. Позже `GET /matching/suggestions/{id}` → тот же результат с датой расчёта (`created_at`), автором, редакцией вакансии (`vacancy_revision`) и запросом.
4. После правки вакансии — новый `POST` с новой `revision`. Прежняя подборка остаётся для объяснения.

Подборка — явное действие API, а не фоновое событие: автоматический запуск по событию публикации относится к этапу 2.

**Что хранится.** Разрешённая выдача: `candidate_id`, балл, тип совпадения, статус оценки, ссылка на версию источника (`candidate_text_id` и границы фрагмента). Текст фрагмента и описание вакансии не хранятся. При чтении фрагмент берётся из действующего источника, а `source_status` показывает его состояние:
- `available` — текст кандидата текущий, фрагмент и границы UTF-16 отдаются;
- `superseded` — текст заменён новой версией, фрагмента нет, ссылка остаётся;
- `unavailable` — кандидат удалён или из другого контура, фрагмента и кода нет.

Права и контур проверяются при каждом чтении. Подборка не создаёт отклик, приглашение, запись резерва и не даёт права на контакт (`qualification_note` в ответе).

```bash
uv run python scripts/check_matching_suggestions.py   # API запущен, учебный корпус загружен (load-demo)
```
