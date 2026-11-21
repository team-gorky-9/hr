# Вводная программа · этап 1 · 21 ноября 2026

Реализованы шесть операций `/api/v1/onboarding` по [контракту](../contracts/wave-2-stage-1.md).
База `0a20c84c52522d6743d6503d3c0135030c301540`, ветка `feature/wave-2-onboarding`.
Проверены изменения рабочего дерева поверх этой базы; SHA поставки фиксируется продуктовым PR.
[Постановка](https://github.com/team-gorky-9/hackaton/blob/main/hq/tasks/stage-1/wave-2-david-onboarding.md).

## Что подтверждено запуском

Два адресных сценария pytest на настоящем приложении и SQLite: основной прошёл за общий запуск
2,19 с; после исправления сравнения равнозначных UTC-записей `Z`/`+00:00` второй прошёл отдельно за 1,21 с.
Ошибка была в строковом сравнении теста, подтверждения в истории не изменялись.
Затем основной путь прошёл через настоящий uvicorn/httpx на `http://127.0.0.1:52327` и отдельной SQLite.
HTTP-сервер завершён скриптом; этот порт не является адресом постоянно работающего стенда.

| Шаг | Наблюдаемый результат |
|---|---|
| Миграция и двукратный seed | Шаблон intro-v1/1 доступен с тремя информационными шагами |
| Вход HR и employee через `POST /api/v1/sessions` | Настоящие серверные сессии, учебный пароль `123` |
| `POST /api/v1/employees` и `…/{id}/assignments` | Учебный сотрудник связан с actor `00000000-0000-4000-8000-000000000104`, начало `2026-01-01`, department `00000000-0000-4000-8000-000000000011`, position `economist-training`, basis `DEMO-21` от `2026-11-21` |
| `POST /api/v1/onboarding/programs` | 201, 0/3, revision=1; повтор той же пары — 200 и прежний id |
| `GET /api/v1/onboarding/programs` как employee | Только связанная собственная программа |
| `POST …/steps/introduction/acknowledge`, затем contacts и first-day | expected_revision=1,2,3; результат 3/3, revision=4, intro_completed |
| Повтор первого ознакомления с expected_revision=1 | 200, прежние подтверждения, revision=4, прогресс 3/3 |
| Другая employee-учётка той же организации | Пустой список, 404 по чужому id |
| HR пытается отметить шаг за сотрудника | 403 |
| Будущее назначение / новая отметка после окончания | 409 ASSIGNMENT_NOT_ACTIVE; история читается, assignment_state=inactive |
| Отмена с устаревшей / актуальной ревизией | 409 STALE_REVISION / cancelled, причина и прежнее ознакомление сохранены в ответе и Audit |
| Новое соединение с БД после остановки HTTP | Сохранены intro_completed, revision=4 и три отметки |
| `GET /openapi.json` | Шесть новых операций и схемы ответов |

ID настоящего HTTP-прохода:

- employee: `40af8514-67e1-4af1-9e76-8bfd7ea50c72`;
- assignment: `62cb7473-9f69-4346-9470-e296f45a18eb`;
- program: `c25a87bf-63db-4b0b-9d3b-56146fa54127`.

Локальная БД и OpenAPI сохранены в `%TEMP%/onboarding-smoke-cjuahpvj`; это локальное свидетельство,
не зависимость продукта. Все входы синтетические; рабочие кадровые данные не использовались.

## Повтор и передача Маше

Из `services/workforce/`:

```sh
uv sync --locked
uv run python -m tests.support.onboarding_smoke
uv run pytest tests/test_onboarding.py -q
```

В проверенной Windows-среде использован существующий Python 3.13.17 и отдельное временное окружение
из того же lock: `& "$env:TEMP/onboarding-venv/Scripts/python.exe" -X utf8 -m tests.support.onboarding_smoke`.
Это короткий автономный API-пример, без Docker и RabbitMQ. Скрипт печатает новые ID/порт/каталог;
локальные session-токены не входят в отчёт.

Для интеграции со штатным API порт 8101, OpenAPI `http://localhost:8101/openapi.json`, документация
`http://localhost:8101/docs`. Сначала применить `python -m workforce prepare` с нужной DATABASE_URL.
Схемы ProgramView/ProgramStep описывают чтение прогресса, assignment_state и account_link_required.
Запрос назначения:

```json
{"workforce_assignment_id":"62cb7473-9f69-4346-9470-e296f45a18eb","template_code":"intro-v1","template_version":1}
```

UUID выше относится только к выполненному учебному проходу; в другом контуре использовать его действующее
назначение. `GET /programs/{id}` используется и для чтения employee, и для обновления прогресса HR.
В новых операциях достаточно Bearer и JSON; `Idempotency-Key` первой волны не требуется.

## Граница проверки

Полный набор, конкурентные/стрессовые матрицы, PostgreSQL, Docker, RabbitMQ, UI и рабочая идентификация
не прогонялись. Общий стенд не переключался. В окружении есть предупреждение зависимости
Starlette об устаревающей связке TestClient/httpx; оно не скрыто. Информационное ознакомление не означает
подтверждённую компетенцию, прохождение испытания или полное завершение адаптации.
