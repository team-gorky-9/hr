# Wave 3B · вакансии по присланному резюме · этап 1

**21 ноября 2026 · Илья.**
- Ветка `feature/wave-3b-vacancies-for-candidate` от `hr` `main` `802a8f7` (3A уже в main, hr#47).
- Карточка — `hq/tasks/stage-1/wave-3b-ilya-vacancies-for-candidate.md` в штабе.
- Контракт — [wave-3-matching-stage-1](../contracts/wave-3-matching-stage-1.md), раздел 3B. Описание модуля — [matching.md](../modules/matching.md#как-работает-3b).

## Что сделано

- `POST /api/v1/matching/vacancies` (`app/matching/`). Читает сохранённые кросс-оценки и связывает вакансию с оценкой только по точному профилю: id, версия и должность.
- Сопоставление профиля вынесено в общую функцию `match_profile`. 3A использует её же и по-прежнему отвечает 409 на профиль другого контура.
- `VacancySnapshot.search_query` стал необязательным в самом снимке. Для 3A он по-прежнему обязателен: 422 без него. Поведение 3A не изменилось, его тесты проходят.
- Миграций нет. Оценки, отклики и вызовы модели не создаются.

## Проверка

**Через HTTP.**
- Окружение: отдельная пустая учебная база `hr_match` (PostgreSQL 16), `alembic upgrade head`.
- Подготовка без модели: `scripts/check_matching_vacancies.py --prepare` создаёт учебные копии профиля py-9001 на трёх должностях и две оценки FakeLLMClient.
- Затем `uvicorn app.main:app --port 8000` и `scripts/check_matching_vacancies.py`.

| Вход | Результат |
|---|---|
| Кандидат `match-9001`, вакансии …b1 qa-manual, …b2 python-dev, …b3 frontend-dev, …b4 python-dev (закрыта) | 200, `source_mode=provided` |
| items | …b2 python-dev: `met` — «Обязательные требования выполнены (оценка v1)»; …b1 qa-manual: `unknown` — «Нет сведений: Подтверждённый общий коммерческий опыт не менее двух лет (оценка v1)» |
| needs_evaluation | …b3 frontend-dev: `not_assessed` |
| excluded | …b4: `closed` |
| Роль department | 403 `FORBIDDEN_ROLE` |
| Рабочий контур без ключа поиска | 401 `SEARCH_AUTH_REQUIRED` |

**Тесты.** `uv run pytest tests/test_matching_vacancies.py` → 3 passed. Покрыто:
- items в порядке met → unknown;
- needs_evaluation с причинами `not_assessed`, `no_profile_ref`, `profile_mismatch` (тот же профиль на чужой должности), `unmapped_profile` (catalog);
- excluded закрытой вакансии;
- повторный запрос даёт тот же ответ, число откликов и оценок не меняется;
- отказы: роль, рабочий контур без ключа, кандидат другого контура, неизвестный кандидат, вакансия другого контура;
- неверные входы: пустой список, повтор ссылки, 51 вакансия, `limit=0`, лишнее поле.

Полный `uv run pytest` → **884 passed**, 0 пропусков.

## Для интерфейса

`POST /api/v1/matching/vacancies`, схемы `VacanciesForCandidateIn` / `VacanciesForCandidateOut` в `/openapi.json`. Три списка показывать отдельно: «есть оценка», «нужно оценить» с причиной, «исключены». Пустой `items` при непустом `needs_evaluation` — не «подходящих вакансий нет». Подробности оценки по `assessment_id` — в `GET /candidates/{id}/cross-assessments`.

## Ограничения

- Список вакансий — только предоставленные снимки (`provided`). Адаптера `catalog_api` нет.
- Профили нового Requirements (`system=catalog`) — `unmapped_profile`, пока нет подтверждённого отображения.
- Профиль прежней версии, если по нему сохранена оценка, но утверждён уже новый, даёт `profile_not_current`. Сравнение со старой версией — отдельный путь `GET /applications/{id}/comparison`.
- `limit` ограничивает только `items`. `needs_evaluation` и `excluded` приходят полностью: их не больше 50 по размеру входа.
