# Модуль «Кадровая картина для руководства» (management)

Код — `app/management/`. Контракт — [wave-4-reporting-stage-1](../contracts/wave-4-reporting-stage-1.md). Реализован раздел 4A, сводка текущей работы. 4B (годовой выпуск) и 4C (плановый снимок) — следующие задачи.

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
