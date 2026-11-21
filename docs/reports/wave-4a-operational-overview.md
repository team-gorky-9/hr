# Wave 4A · текущая работа и факты интервью · этап 1

**21 ноября 2026 · Илья.**
- Ветка `feature/wave-4a-operational-overview` от `hr` `main` `3755b5f` (база спецификации hr#48 `802a8f7`).
- Карточка — `hq/tasks/stage-1/wave-4a-ilya-operational-overview.md` в штабе.
- Контракт — [wave-4-reporting-stage-1](../contracts/wave-4-reporting-stage-1.md), раздел 4A. Описание — [management.md](../modules/management.md).

## Что сделано

- `GET /api/v1/management/overview` (`app/management/`): существующая воронка без изменений и блок телефонных встреч из полей итога второй волны.
- Миграций нет, существующие маршруты не менялись.
- Кроме полей контракта, добавлены `open_count` (открытые встречи на срезе), `held_applications_count` (дедупликация по отклику) и `no_answer_count` у проводящего. Это нужно, чтобы показ различал открытую встречу и попытку.

## Проверка

**Через HTTP.**
- Окружение: учебная база `hr_demo` (PostgreSQL 16), `uvicorn app.main:app --port 8000`.
- Подготовка: `scripts/check_management_overview.py --prepare`. Встречи py-9103 / py-9104 / py-9105 завершены штатным `POST /interviews/{id}/outcome`, у py-9106 открытая встреча.
- Проход: `scripts/check_management_overview.py`.

| Запрос | Результат |
|---|---|
| `from=2026-11-20&to=2026-11-21&contour=training` | 200. held=1 (py-9103 в 23:59), no_answer=1, open=1, undated=0. `hr_demo`: continue 1. Источники: legacy-hr — available, workforce/hiring/practice — unavailable |
| `from=2026-11-21&to=2026-11-22` | 200. held=2: py-9105 stop в 00:00 и py-9101 continue от прошлой проверки второй волны. no_answer=1 (py-9102), open=1 |
| `dept_demo` | 403 `FORBIDDEN_ROLE` |
| Повторный `--prepare` | те же команды итога — повтор без нового факта (200), открытая встреча не дублируется |

**Тесты.** `uv run pytest tests/test_management_overview.py` → 3 passed:
- различение held / no_answer / open / undated;
- граница суток 23:59 и 00:00 МСК;
- старая строка `continue` без `held_at` не считается проведённой;
- воронка совпадает с `/analytics/funnel` того же периода;
- источники;
- пустой журнал рабочего контура («0 зарегистрировано в этом журнале»);
- отказы: department, без пользователя, пустой период, без контура, неверная дата.

Полный `uv run pytest` → **890 passed**, 0 пропусков.

## Для интерфейса

`GET /api/v1/management/overview?from=YYYY-MM-DD&to=YYYY-MM-DD&contour=training|working`, схема `OverviewOut` в `/openapi.json`. Счётчики интервью показывать с подписями из `interviews.units`. Источники со статусом `unavailable` — «нет подключения», а не ноль.

## Ограничения

- Только журнал legacy-hr: отклики и телефонные встречи. Встречи `department` в блок не входят. Workforce, Hiring и практика к этой сводке не подключены.
- `outcomes.pending` проводящего обычно 0: у открытой встречи проводящий ещё не записан, он появляется с итогом.
- Воронка считает срез на момент запроса по своим правилам. Период влияет только на её закрытия.
