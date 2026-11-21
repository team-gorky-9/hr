# Wave 2 · итог телефонной встречи · этап 1

**21 ноября 2026 · Илья.**
- Ветка `feature/wave-2-interview-outcome` от `hr` `main` `0a20c84`, после hr#40 `134a32b`.
- Карточка — `hq/tasks/stage-1/wave-2-ilya-interview-outcome.md` в штабе.
- Контракт — [wave-2-stage-1](../contracts/wave-2-stage-1.md), раздел «Илья».

## Что сделано

| Что | Где |
|---|---|
| `GET /api/v1/applications/{id}/interviews` — встречи отклика с итогом | `app/api/interview.py`, `app/api/routes.py` |
| `POST /api/v1/interviews/{id}/outcome` — завершить телефонную встречу | там же, схемы в `app/api/schemas.py` |
| Поля `revision` (старые строки — 1), `attempt_at`, `outcome_recorded_at` | миграция `0010_interview_outcome.py`, модель `Interview` |
| История записи | строка `audit_log`, `event = interview.outcome_recorded` |
| Проверка через HTTP | `scripts/check_interview_outcome.py` |
| Тесты | `tests/test_api_interview_outcome.py`; списки маршрутов в `tests/test_api.py` и `tests/test_api_workflow.py` дополнены двумя новыми путями |

### Решения

- Строка встречи блокируется на время записи (`SELECT … FOR UPDATE`). Две параллельные команды не перезапишут один итог: вторая получит повтор или 409.
- Повтор в точности той же команды того же пользователя возвращает прежний результат с кодом 200 и не создаёт новой записи в журнале. Повтор сравнивает результат, время, пояснение и автора, но не `expected_revision`: после первой записи ревизия уже выросла.
- Для `no_answer` интервьюер тоже записывается: это тот, кто звонил. `held_at` при этом пуст.
- Время без часового пояса даёт 422. Время позже серверного более чем на 5 минут — `422 INVALID_OCCURRED_AT`.
- Пояснение после свёртки пробелов должно содержать не меньше 5 символов.
- Ограничение БД `ck_interviews_outcome_shape` не даёт сохранить итог без `attempt_at` или `held_at` у состоявшегося разговора. На старые строки без `outcome_recorded_at` оно не действует.

## Проверка

**Прогон через HTTP.**
- Окружение: учебная база `hr_demo` (PostgreSQL 16, данные `demo_setup`), `alembic upgrade head` (0008 → 0009 → 0010), `uv run uvicorn app.main:app --port 8000`.
- Команда: `uv run python scripts/check_interview_outcome.py`.

| Шаг | Вход | Результат |
|---|---|---|
| Открытая встреча py-9101 | `repo.open_interview`, без модели | application `c056e458-…`, interview `851d1d6f-35cd-4d79-b9ae-180663024778` |
| `POST /interviews/851d1d6f…/outcome` | `continue`, `occurred_at=2026-11-21T02:43+03:00`, пояснение, `expected_revision=1` | 200: `held_at = attempt_at = 02:43`, interviewer `hr_demo` (`ac28c6de-…`), `revision=2` |
| Повтор той же команды | то же тело | 200, тот же результат |
| `GET /applications/c056e458…/interviews` | — | одна встреча: `continue`, та же дата и интервьюер, `outcome_recorded_at` |
| Иной итог | `stop`, `expected_revision=2` | 409 `INTERVIEW_ALREADY_COMPLETED` |
| Роль department | `dept_demo` | 403 `FORBIDDEN_ROLE` |
| py-9102 | `no_answer` | 200: `held_at=null`, `attempt_at=02:43`, `revision=2` |

**Тесты.**
- `uv run pytest tests/test_api_interview_outcome.py` → 4 passed:
  - continue, перечитывание, повтор, конфликт итога и чужого пользователя, этап отклика не изменился, одна запись журнала;
  - no_answer;
  - отказы: роль, без пользователя, пустое пояснение, время без зоны и в будущем, лишнее поле, устаревшая ревизия, неизвестная встреча, `UNSUPPORTED_INTERVIEW_KIND`, список чужого/несуществующего отклика;
  - гайд после завершённой встречи открывает новую `pending`, ответ прежней встречи читается.
- Полный прогон для совместимости: `uv run pytest` → **878 passed**, пропусков 0. Окружение: PostgreSQL 16 + pgvector, `TEST_DATABASE_URL`.

## Для интерфейса

Факт встречи интерфейс читает через `GET /api/v1/applications/{id}/interviews`. Записывает итог `POST /api/v1/interviews/{id}/outcome`. `id` встречи берётся из `interview_id` гайда либо из этого списка. Схемы — `/openapi.json` (`InterviewOut`, `InterviewOutcomeIn`).

## Что не проверено и не входит

- Исправление уже записанного итога, перепланирование встречи (`scheduled_at`) и встречи вида `department` — следующие задачи.
- Живая модель не вызывалась. Шаг «гайд после завершённой встречи» проверен на `FakeLLMClient`.
- Связь с Workforce и новыми сервисами не затрагивается.
