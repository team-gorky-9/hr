# Workforce · первая волна

**Промежуточная поставка, 21 ноября 2026.** Опубликована по просьбе Давида без нового итогового прогона тестов. Что реализовано и что осталось — в [отчёте](../../docs/reports/wave-1-workforce.md). Полная приёмка пока не закрыта.

Сервис ведёт учебный вход, подразделения, сотрудников, назначения, переводы, замещения, историю и передачу результатов оформления через RabbitMQ. Контракты: [общий](../../docs/contracts/wave-1-common.md), [Workforce](../../docs/contracts/wave-1-workforce.md). [Устройство](../../docs/modules/workforce-service.md).

## Запуск из корня продукта

```sh
docker compose -f services/workforce/compose.yml up --build
```

Compose описывает собственные PostgreSQL 17, RabbitMQ, миграции/seed, API и worker. Порт API — 8101, документация — http://localhost:8101/docs, OpenAPI — `/openapi.json`. Синтаксис Compose проверен, **сборка и запуск контейнеров пока не проверены**: в среде разработки отсутствует Docker Engine. Фактические проверки выполнялись отдельными процессами Python, PostgreSQL и RabbitMQ.

`POST /api/v1/sessions` с телом `{"login":"hr","password":"123"}` и заголовком `Idempotency-Key: <UUID>` возвращает Bearer-токен. Учебные логины и роли — [actors.json](../../fixtures/wave-1/actors.json). `GET /api/v1/session` проверяет сессию, `DELETE /api/v1/session` отзывает её. По умолчанию сессия живёт 8 часов.

В локальном Compose `AUTH_MODE=fixture`: дополнительно принимается `Bearer fixture:<login>`. Для интеграции задать `AUTH_MODE=workforce` — остаются настоящие серверные учебные сессии. Фиксированный fixture-токен не является отзывной сессией. Все режимы проверяют права и организацию на сервере.

Изменяющие POST/PATCH требуют `Idempotency-Key`, изменение ресурса — `expected_revision`. Повтор команды возвращает прежний результат; другой запрос с тем же ключом даёт 409. Чужой объект скрывается через 404.

## Нативный запуск без контейнеров

Из `services/workforce/`:

```powershell
uv sync --locked --python 3.13
$env:DATABASE_URL = 'postgresql+psycopg://workforce:workforce@127.0.0.1:5411/workforce'
$env:RABBITMQ_URL = 'amqp://workforce:workforce@127.0.0.1:5681/%2F'
$env:AUTH_MODE = 'workforce'
uv run python -m workforce prepare
uv run uvicorn workforce.api:create_app --factory --host 127.0.0.1 --port 8101
```

В другом терминале с теми же переменными: `uv run python -m workforce.worker`. PostgreSQL и RabbitMQ должны быть запущены заранее. `prepare` применяет миграции и повторяемый seed; существующие данные и отозванные сессии не перезаписываются. `.env.example` показывает переменные нативного запуска; конфигурация читает окружение процесса, файл автоматически не загружается.

`DATABASE_URL` и `RABBITMQ_URL` позволяют подключить внешние зависимости. Для контейнеров адреса должны быть доступны из контейнерной сети. `SESSION_HOURS=8`, `RETRY_SECONDS=5`, `MAX_ATTEMPTS=5`, `POLL_SECONDS=1` — значения по умолчанию. Задержка повторов удваивается до предела 300 секунд. После лимита отправка становится failed; `POST /api/v1/deliveries/{event_id}/retry` с ревизией и ключом возвращает её в pending.

## Проверки и учебный проход

Команда полного контейнерного набора (ещё требует проверки Docker-сборки):

```sh
docker compose -f services/workforce/compose.yml --profile test run --build --rm tests
```

Нативно, из папки сервиса:

```powershell
$env:WORKFORCE_TEST_DATABASE_URL = 'postgresql+psycopg://workforce:workforce@127.0.0.1:5411/workforce_test'
$env:WORKFORCE_TEST_RABBITMQ_URL = 'amqp://workforce:workforce@127.0.0.1:5681/workforce_test'
uv run pytest -q
```

Тесты требуют отдельную БД с окончанием `_test`, создают/удаляют только собственные временные схемы. Брокерные тесты требуют отдельный vhost с окончанием `_test`; его учебные очереди очищаются. Без переменной БД используются SQLite-тесты, без переменной брокера интеграционные тесты пропускаются с причиной. Это не заменяет проверку PostgreSQL/RabbitMQ.

При работающих API/worker в учебном окружении:

```sh
uv run python -m tests.support.smoke normal
uv run python -m tests.support.review_smoke apply
uv run python -m tests.support.review_smoke keep
```

Повторная проверка меняет прежнее назначение либо оставляет его значения с обязательным объяснением. Оба исхода сохраняют assignment_id и отправляют `assignment.reviewed`. Файлового API у Workforce нет: сохраняются только ссылки и реквизиты оснований.

Для отдельного прогона сбоя: `smoke prepare` → остановить **свой учебный** брокер → `smoke offline` → запустить брокер → `smoke recover`. После перезапуска API/worker/БД выполнить `smoke restart`. Для Compose остановка/восстановление: `docker compose -f services/workforce/compose.yml stop rabbitmq` / `start rabbitmq` из корня продукта. Если истёк лимит автоматических попыток, перед recover выполнить ручной retry доставки через API.

Скрипты сохраняют учебный токен в локальном `workforce-smoke-state.json`, исключённом из Git; его не публиковать. Параметр `--state` задаёт другой путь. Издатель фиксированного общего примера: `python -m tests.support.broker --repeat 2`; отрицательный пример: `--foreign`; чтение результата: `--read-result`. Эти подмены предназначены для автономного стенда, не для конкурентного чтения очередей настоящего Hiring.
