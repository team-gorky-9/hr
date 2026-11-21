# Отчёт о проверке · wave-1-requirements

**Дата:** 2026-11-21
**Ветка продукта:** `feature/wave-1-requirements` (от базового SHA `f82f5825858ebc5bf1ccd2df0b28811b2a19cbd3`, `hr#34`)
**Задача штаба:** `hq/tasks/wave-1-denis-requirements.md`
**Контракты:** [wave-1-common](../contracts/wave-1-common.md), [wave-1-requirements](../contracts/wave-1-requirements.md)

## Состав поставки

- `hr/services/requirements/`: автономный сервис на Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, `psycopg[binary]`, `pika`, `pypdf` (`pyproject.toml`, `uv.lock`, `Dockerfile`, `compose.yml`, `README.md`, `alembic.ini`, `migrations/versions/0001_initial_requirements.py`, `fixtures/wave-1/`).
- Исходный код: `src/requirements_service/` (`config.py`, `errors.py`, `auth.py`, `validation.py`, `extraction.py`, `storage.py`, `schemas.py`, `idempotency.py`, `pagination.py`, `service.py`, `seed.py`, `main.py`, `db/*`, `messaging/*`, `api/*`).
- Документация модуля: [requirements-service.md](../modules/requirements-service.md).
- Тесты и тестовый подписчик: `hr/services/requirements/tests/` (`support/consumer.py`, `support/legacy_parity_check.py`, `conftest.py`, `test_validation_parity.py`, `test_e2e_acceptance.py`, `test_errors_security_concurrency.py`, `test_outbox_and_broker.py`, `test_edge_cases_and_cli.py`, `test_integration_live.py`).

## Результаты проверок и границы покрытия

### Автономная проверка (выполнена локально)

Команда из корня штаба:

```powershell
uv --directory hr/services/requirements run pytest -v -rs
```

Результат: **25 passed, 1 skipped** (0 failed).

Что подтверждено:
1. **Валидация и паритет (`test_validation_parity.py`):**
   - `fixtures/requirement_profiles/py-9001.draft.json` проходит валидацию `validate_draft_content` и даёт побайтно/поструктурно совпадающий JSON с legacy `app.requirements.schemas.validate_draft` (через `hr/.venv`).
   - Отклоняются лишние поля, строковые булевы значения (`"false"`), булевы в целочисленных полях (`True` вместо `int`), обратный диапазон `target_level_min > target_level_max`, дубли ключей/кодов, некорректный `same_as` и ссылка `requires_requirement` на несуществующее требование; значения неизвестных полей не утекают в текст ошибки.
   - Эталон события `requirements.approved` из `fixtures/wave-1/events.json` совпадает со структурой конверта outbox.
2. **Полный путь приёмки (`test_e2e_acceptance.py`):**
   - `/health` (`auth_mode="fixture"`), `/ready` (`db="ok"`, `migrations="ok"`, `broker="ok"`), предзагруженная должность `economist-training`.
   - Загрузка `job-description.txt` через `POST /api/v1/sources`, проверка `/api/v1/documents/{id}` и `/api/v1/documents/{id}/content`.
   - Создание черновика v1 с цитатами на реальный `source_id` → `submit` на `department` → `review(returned)` → `PATCH` (`content_revision=2`) → повторный `submit` → `review(accepted)` → `approve` v1 (`is_current=true`, `version=1`, снимок `sources_snapshot`).
   - Публикация `requirements.approved` через `OutboxRelay` и чтение профиля потребителем (`tests/support/consumer.py`) по HTTP `GET /api/v1/profiles/{id}` с валидацией `requirement-draft/1.0`.
   - `POST /api/v1/profiles/{v1_id}/revise` → изменение и утверждение v2 (`version=2`, `is_current=true`); `GET /api/v1/profiles/{v1_id}` продолжает возвращать неизменную v1 (`is_current=false`), а `GET /api/v1/positions/economist-training/approved-profile?contour=training` отдаёт v2.
3. **Ошибки, права, изоляция, сканы и конкурентность (`test_errors_security_concurrency.py`, `test_edge_cases_and_cli.py`):**
   - Аутентификация (`401 AUTH_REQUIRED` / `INVALID_SESSION`), `WorkforceActorDirectory` (`200`, `401`, `503 DEPENDENCY_UNAVAILABLE`), отказ `candidate`/`employee` (`403`), ограничение области `department` только назначенными черновиками/источниками (`403`), замещение администратором только с `override_reason`.
   - Изоляция `hr_other`: `404` на ресурсы и `422 SOURCE_NOT_FOUND` (неотличимый от несуществующего UUID) при попытке сослаться на чужой источник.
   - Извлечение TXT, DOCX, текстового PDF, битого PDF (`failed` + `PDF_INVALID`) и скана PDF без текстового слоя (`unavailable` + `PDF_NEEDS_REVIEW`).
   - Попытка утверждения с недоступным источником → `409 SOURCE_NOT_READY`; ручная транскрипция `POST /sources/{id}/transcription` увеличивает `source.revision`, не меняет байты оригинала и требует пересогласования открытого черновика (`409 INVALID_STATE`), оставляя ранее утверждённые профили неизменными.
   - Неверная цитата (`422 SOURCE_MISMATCH`), превышение `FILE_MAX_BYTES` (`413 FILE_TOO_LARGE`), защита `original_name` от path traversal, `409 STALE_REVISION`, повтор `Idempotency-Key` с `Idempotency-Replayed: true` (включая повтор `approve` после смены статуса) и `409 IDEMPOTENCY_CONFLICT`, курсорная пагинация, `/ready -> 503` до миграций, CLI `seed` и `outbox --once`.
   - Конкурентный `approve` двух черновиков одной должности сериализуется в `v1` (`is_current=false`) и `v2` (`is_current=true`); две вкладки одного черновика дают `201` и `409 STALE_REVISION`.
4. **Outbox, сбой брокера, рестарт и потребитель (`test_outbox_and_broker.py`):**
   - При недоступном брокере `approve` сохраняет профиль и `pending`-доставку, `/ready` возвращает `200` с `broker="unavailable"`, повторы с backoff переводят доставку в `failed` без утечки payload/токенов в `GET /deliveries`.
   - Рестарт приложения на тех же БД и `FILE_ROOT` сохраняет профиль, файлы и доставку; после восстановления брокера `POST /deliveries/{event_id}/retry` успешно отправляет событие.
   - Инъекция падения потребителя после `commit` в `consumer_inbox` до `ack` (`ConsumerCrashBeforeAck`) приводит к повторной доставке, которая безопасно распознаётся как дубликат без создания второй записи.
   - Неверная `schema_version`, неожиданный `producer` и чужая `organization_id` отправляются потребителем в dead-letter очередь `w1.demo-recruitment.dead`.

### Что НЕ проверено в этом прогоне (требует среды с Docker / соседом)

1. **`test_integration_live.py` (1 skipped):** пропущен, так как на текущем Windows-хосте отсутствуют Docker, PostgreSQL 17 и RabbitMQ (`TEST_DATABASE_URL` и `TEST_RABBITMQ_URL` не заданы).
2. **Сборка и запуск Docker Compose:** `docker compose -f services/requirements/compose.yml up --build` не выполнялся из-за отсутствия Docker на хосте.
3. **Интеграция с реальным сервисом `workforce`:** `WorkforceActorDirectory` проверен на `httpx.MockTransport`; живое соединение с `workforce` при `AUTH_MODE=workforce` выполняется на этапе общей интеграции.

## Пример входа и выхода основного пути

1. Вход `POST /api/v1/sources` (`file=job-description.txt`, `position_code="economist-training"`) → `201` (`extraction_status="ready"`, `revision=1`).
2. Вход `POST /api/v1/drafts` (`position_code="economist-training"`, `content` формата `requirement-draft/1.0` с `is_synthetic=true` и цитатами на `source_id`) → `201` (`status="editing"`, `revision=1`, `content_revision=1`, `contour="training"`).
3. `submit` → `review(returned)` → `PATCH /api/v1/drafts/{id}` (`content_revision=2`) → `submit` → `review(accepted)` → `POST /api/v1/drafts/{id}/approve` → `201` (`version=1`, `contour="training"`, `is_current=true`, событие `requirements.approved` в `outbox_events`).
4. `POST /api/v1/profiles/{v1_id}/revise` → `PATCH` → `submit` → `review(accepted)` → `approve` → `201` (`version=2`, `is_current=true`), при этом `GET /api/v1/profiles/{v1_id}` сохраняет `version=1` и `is_current=false`.

## Повторная проверка этапа 1 · 21 ноября 2026

База обновлена до hr/main 376b9b4. Команда: uv --directory hr/services/requirements run pytest -q -rs -s. Результат: 26 passed, 1 skipped. Исправлена кодировка subprocess проверки legacy на Windows (-X utf8). Health дополнен implementation_stage=1/integration_mode=standalone; фоновая отправка по умолчанию выключена.

Новый test_stage1 проходит учебный путь с настоящим RabbitMQPublisher, направленным на недоступный порт, без Workforce. Хранилище — файловая SQLite, миграция Alembic; повторный экземпляр приложения открывает прежние v1/v2 и исходные байты. HTTP проверен посредством ASGI TestClient; отдельный сетевой сервер и PostgreSQL в этом прогоне не проверены.

ID источника ec7561fc-90bf-446e-8149-ff9281e0d875; v1 0aad9e4d-5624-4fe3-b5e9-21a0e5abf76c; v2 5c1e4308-08fd-4f55-89e4-65eb23327fde. Это временные учебные данные теста.

Остаётся проверка на PostgreSQL, запуск внешнего HTTP-сервера и реальный перезапуск процесса. Live PostgreSQL/RabbitMQ тест пропущен из-за отсутствия среды. PR публикуется как draft, полная сдача не заявляется. Этап 2: автоматическая доставка и реальные потребители.

### Сетевой прогон после возобновления

`uv --directory hr/services/requirements run pytest tests/test_stage1.py -q -s` — 1 passed. Тест теперь поднимает отдельный uvicorn-процесс на loopback, выполняет реальные HTTP-запросы, завершает процесс и запускает новый на той же SQLite и каталоге файлов. Подтверждены сохранение v1/v2 и исходных байтов. Источник: 0c544c15-f107-4375-8f6a-893a67bf252a; v1: 9fb04a94-0e57-44b2-a62c-ec9f2341e2ac; v2: 931b1c0e-879f-4dff-a487-c9c602fffe94. Этот прогон закрывает ранее отмеченные ограничения внешнего HTTP и рестарта процесса. PostgreSQL и Docker остаются непроверенными.

### Сдача по текущему демонстрационному режиму

Денис поручил слияние этапа 1. Ветка обновлена из main без конфликтов. На fd8e12639dd13daba27f69082fdd17ee82e17752 команда `uv --directory hr/services/requirements run pytest tests/test_stage1.py tests/test_validation_parity.py -q -rs` дала 13 passed. Проверены сетевой путь, перезапуск и паритет формата с legacy. По актуальному docs/verification.md штаба сдаётся подтверждённый демонстрационный путь; прежнее указание держать PR в draft до расширенной проверки заменено этим решением. PostgreSQL/Docker и реальные интеграции остаются непроверенными; эксплуатационная готовность не заявляется.
