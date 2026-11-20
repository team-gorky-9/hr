# Сервис требований (`services/requirements/`)

Автономный сервис подготовки, согласования и выпуска версий профилей требований к должности (первая волна, порт `8102`). Реализует контракты [wave-1-common](../contracts/wave-1-common.md) и [wave-1-requirements](../contracts/wave-1-requirements.md).

## Архитектура и границы владения

Сервис полностью автономен от БД и ORM legacy-приложения (`app.db.*`): использует собственную схему БД PostgreSQL 17, собственный каталог файлов `FILE_ROOT` и собственный outbox-паблишер в RabbitMQ (`exchange: w1.requirements`).

Внутренние компоненты (`hr/services/requirements/src/requirements_service/`):

| Модуль | Ответственность |
|---|---|
| `config.py` | Конфигурация `Settings`: `DATABASE_URL`, `RABBITMQ_URL`, `AUTH_MODE`, `WORKFORCE_BASE_URL`, `FILE_ROOT`, `FILE_MAX_BYTES`, параметры outbox и seed |
| `errors.py` | Единый обработчик ошибок `{"error": {"code", "message", "field", "request_id"}}` и защита от утечки входных значений |
| `auth.py` | Интерфейс `ActorDirectory`: `FixtureActorDirectory` (`AUTH_MODE=fixture`, только `Bearer fixture:<login>`) и `WorkforceActorDirectory` (`AUTH_MODE=workforce`, `503` при сбое) |
| `validation.py` | Автономная валидация `requirement-draft/1.0`, `params` 0.1, строгих bool/int, `same_as`, `requires_requirement` и несоседних фрагментов цитат |
| `extraction.py` | Извлечение текста TXT (BOM/UTF-8/cp1251), DOCX (XML абзацы и таблицы без дублирования объединённых ячеек) и текстовых PDF (`pypdf`); сканы без текстового слоя получают статус `unavailable` |
| `storage.py` | Атомарное локальное хранение байтов (`FILE_ROOT/.tmp` → `fsync` → `os.replace`) с проверкой `FILE_MAX_BYTES` (`413`) и изоляцией путей от `original_name` |
| `db/models.py`, `migrations/` | Таблицы `positions`, `documents`, `sources`, `source_text_revisions`, `drafts`, `draft_events`, `approved_profiles`, `idempotency_records`, `outbox_events` |
| `idempotency.py`, `pagination.py` | Обязательный `Idempotency-Key` (с повтором до проверки `expected_revision`) и курсорная пагинация `(created_at, id)` |
| `service.py` | Жизненный цикл черновиков, пересчёт `content_revision`, проверка согласования, сериализованное утверждение и неизменяемые снимки источников |
| `messaging/transport.py`, `outbox.py` | Издатель `RabbitMQPublisher` (`pika`, `confirm_delivery`, persistent) и реле `OutboxRelay` с экспоненциальным backoff и ручным повтором |
| `seed.py` | Идемпотентная загрузка должностей из `fixtures/wave-1/organization.json` (`economist-training`) |

## Хранение версий и ключевые инварианты

1. **Единый идентификатор документа и источника:** `sources.id` равен `documents.id` (FK 1:1), поэтому `/api/v1/documents/{id}` и `/api/v1/documents/{id}/content` доступны для каждого источника.
2. **Неизменяемость оригинала при ручной транскрипции:** `POST /api/v1/sources/{id}/transcription` увеличивает `source.revision`, записывает новую строку в `source_text_revisions` с `text_origin="manual_transcription"`, но не изменяет байты в `FILE_ROOT` и `documents`.
3. **Разделение `revision` и `content_revision`:** любое процессуальное действие (`submit`, `review`, `approve`) увеличивает `draft.revision` (проверяется через `expected_revision`), а `draft.content_revision` увеличивается только при `PATCH /api/v1/drafts/{id}`.
4. **Привязка согласования к редакции и источникам:** `POST /api/v1/drafts/{id}/review` с `result="accepted"` сохраняет `accepted_content_revision` и словарь `accepted_source_revisions`. При правке черновика или транскрипции источника после согласования `approve` отклоняется (`409 INVALID_STATE`) до повторного согласования.
5. **Сериализация утверждения и неизменяемость выпущенных версий:** `POST /api/v1/drafts/{id}/approve` блокирует позицию (`FOR UPDATE` в PostgreSQL + внутрипроцессная блокировка по `(organization_id, position_code)`), перепроверяет готовность источников (`409 SOURCE_NOT_READY`) и цитаты (`422 SOURCE_MISMATCH`), снимает `is_current` с предыдущего профиля того же `(position_code, contour)`, создаёт новый `ApprovedProfile` (с полным снимком `sources_snapshot`), переводит черновик в `approved` и в той же транзакции пишет событие `requirements.approved` в `outbox_events`.
6. **Отказоустойчивость брокера:** при недоступном RabbitMQ `GET /ready` возвращает `200` с `"broker": "unavailable"`, утверждение профиля сохраняется с записью `pending` в `outbox_events`, реле повторяет доставку с экспоненциальным backoff до `OUTBOX_MAX_ATTEMPTS`, после чего доступен ручной перезапуск через `POST /api/v1/deliveries/{event_id}/retry`.

## Запуск и проверка

Команды запуска Docker Compose и прогона автотестов приведены в [README сервиса](../../services/requirements/README.md).

Этап 1: /health явно сообщает implementation_stage=1 и integration_mode=standalone. Фоновый outbox отключён по умолчанию; включается OUTBOX_POLL_INTERVAL_SEC при интеграции этапа 2. Основные операции работают без брокера, сохранённые механизмы доставки не объявлены проверенными на реальном RabbitMQ.
