# Workforce · кадровые назначения и вводные программы

## Вводная программа · этап 1 второй волны

Модуль `workforce/onboarding` использует ту же БД и серверные сессии. `python -m workforce prepare`
применяет миграцию `0003` и повторяемый seed `intro-v1`, версия 1. Три материала явно учебные,
их текст находится в `steps[].description`; `material_url=null` не мешает прочитать материал.
[Контракт](../../docs/contracts/wave-2-stage-1.md) · [Проверенный пример](../../docs/reports/wave-2-onboarding.md).

Все URL ниже имеют префикс `/api/v1/onboarding`; требуется `Authorization: Bearer <access_token>`.

| Метод и путь | Действие |
|---|---|
| `GET /templates` | Шаблоны для HR/admin и employee |
| `POST /programs` | HR назначает `{workforce_assignment_id,template_code:"intro-v1",template_version:1}`; 201, повтор пары — 200 |
| `GET /programs` | HR видит организацию, employee — только свои программы |
| `GET /programs/{id}` | Программа со снимком шагов и прогрессом |
| `POST /programs/{id}/steps/{key}/acknowledge` | Только связанный employee, `{expected_revision}` |
| `POST /programs/{id}/cancel` | HR/admin, `{expected_revision,reason}` |

В отличие от команд первой волны, новым операциям onboarding не нужен `Idempotency-Key`:
повтор назначения определяется парой кадрового назначения и версии шаблона, повтор ознакомления —
уже сохранённой отметкой. Повтор не меняет автора, время, revision или счётчик. Для новой отметки
и отмены неверная ревизия даёт `409 STALE_REVISION`. Отменённая программа не возобновляется повтором назначения.

Начало кадрового назначения должно быть не позже текущей даты UTC; `ends_on` включается в период.
Будущая/закончившаяся занятость не позволяет создать программу или новую отметку (`ASSIGNMENT_NOT_ACTIVE`).
После окончания GET сохраняет историю и возвращает `assignment_state=inactive`.
Без связи учётки HR видит `account_link_required=true`. Отмена сохраняет подтверждения и пишет Audit.
`intro_completed` означает только три ознакомления, а не оценку компетенции или кадрового испытания.

Короткий автономный HTTP-проход (из `services/workforce`, после `uv sync --locked`):

```sh
uv run python -m tests.support.onboarding_smoke
```

Он поднимает временный loopback API на свободном порту, применяет штатные миграции и seed к отдельной
SQLite, проходит 0/3 → 3/3, проверяет чужую employee-учётку, останавливает API и перечитывает БД.
Печатает ID и каталог с сохранёнными `workforce.db` и `openapi.json`; токены не печатает.
Два быстрых адресных теста: `uv run pytest tests/test_onboarding.py -q`.
Брокер и общий стенд этим проходом не затрагиваются. Проверка PostgreSQL и полного набора здесь не заявляется.

Для фронтенда: живой `/openapi.json` содержит модели Templates/Programs/ProgramView и все шесть операций,
`/docs` — интерактивное описание. Пример с ID и команды находятся в отчёте по ссылке выше.

**Автономная поставка, завершение 21 ноября 2026.** Выполнены итоговый набор PostgreSQL/RabbitMQ, сборка Compose и настоящий HTTP/worker-проход. Версии, команды и граница интеграции с Hiring — в [отчёте](../../docs/reports/wave-1-workforce.md).

Сервис ведёт учебный вход, подразделения, сотрудников, назначения, переводы, замещения, историю и передачу результатов оформления через RabbitMQ. Контракты: [общий](../../docs/contracts/wave-1-common.md), [Workforce](../../docs/contracts/wave-1-workforce.md). [Устройство](../../docs/modules/workforce-service.md).

## Запуск из корня продукта

```sh
docker compose -f services/workforce/compose.yml up --build
```

Compose описывает собственные PostgreSQL 17, RabbitMQ, миграции/seed, API и worker. Порт API — 8101, документация — http://localhost:8101/docs, OpenAPI — `/openapi.json`. Сборка и запуск проверены с Docker Engine 29.4.3. Данные БД и брокера сохраняются в собственных томах. Файлового тома у Workforce нет.

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

Команда полного контейнерного набора:

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

Основной интерфейс повторной проверки — `POST /api/v1/intakes/{id}/resolve-correction` с `action=apply_correction|keep_existing`, двумя ожидаемыми ревизиями и обязательной причиной. Оба исхода сохраняют assignment_id и отправляют **одно** `assignment.review-resolved` с `resolution=corrected|kept_existing`. Проверка использует общий `fixtures/wave-1/corrections.json`. Файлового API у Workforce нет: сохраняются только ссылки и реквизиты оснований.

`POST /intakes/{id}/review` сохранён как совместимый алиас первоначальной ветки Давида с `decision=apply|keep`. Его HTTP-ответ сохраняет поле review. Он вызывает ту же предметную операцию и публикует только canonical `assignment.review-resolved`. Для прежнего apply без причины сообщение явно указывает применение входного основания. Новые потребители используют resolve-correction.

Для отдельного прогона сбоя: `smoke prepare` → остановить **свой учебный** брокер → `smoke offline` → запустить брокер → `smoke recover`. После перезапуска API/worker/БД выполнить `smoke restart`. Для Compose остановка/восстановление: `docker compose -f services/workforce/compose.yml stop rabbitmq` / `start rabbitmq` из корня продукта. Если истёк лимит автоматических попыток, перед recover выполнить ручной retry доставки через API.

Скрипты сохраняют учебный токен в локальном `workforce-smoke-state.json`, исключённом из Git; его не публиковать. Параметр `--state` задаёт другой путь. Издатель фиксированного общего примера: `python -m tests.support.broker --repeat 2`; отрицательный пример: `--foreign`; чтение результата: `--read-result`. Эти подмены предназначены для автономного стенда, не для конкурентного чтения очередей настоящего Hiring.
