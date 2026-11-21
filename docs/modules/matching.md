# Модуль «Двунаправленный подбор» (matching)

Код — `app/matching/`. Контракт — [wave-3-matching-stage-1](../contracts/wave-3-matching-stage-1.md). Сейчас реализован раздел 3A: люди под выбранную вакансию. 3B (вакансии по резюме) и 3C (сохранённая подборка) — следующие задачи.

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
