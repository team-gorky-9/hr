# Сервис подготовки и выпуска требований к должности (`requirements`)

Автономный сервис первой волны (контракты [wave-1-common.md](../../docs/contracts/wave-1-common.md), [wave-1-requirements.md](../../docs/contracts/wave-1-requirements.md)).

## Стек и порты

- Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2 (`psycopg`), Alembic, `pika`, `pypdf`
- HTTP API: `8102` (префикс `/api/v1`, OpenAPI `/openapi.json`, `/health`, `/ready`)
- Собственная БД: PostgreSQL 17
- Брокер: RabbitMQ (`exchange: w1.requirements`, тип `topic`, `durable`, подтверждение публикации и транзакционный `outbox`)

## Запуск из чистого клона (Docker Compose)

Из корня репозитория `hr/`:

```bash
docker compose -f services/requirements/compose.yml up --build
```

Контейнер `api` автоматически применит миграции `alembic upgrade head`, загрузит учебную должность `economist-training` из `fixtures/wave-1/organization.json` и откроет сервис на `http://localhost:8102`.

Постоянные тома сохраняют данные между перезапусками:
- `requirements_pgdata` — база данных PostgreSQL 17;
- `requirements_rabbitmq` — очереди и сообщения RabbitMQ;
- `requirements_files` — локальное хранилище загруженных файлов (`FILE_ROOT=/data/files`).

### Внешние URL и интеграционный режим (`AUTH_MODE=workforce`)

Для подключения к внешним БД, брокеру и сервису `workforce` переопределите переменные среды:

```bash
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/requirements
RABBITMQ_URL=amqp://user:pass@host:5672/%2F
AUTH_MODE=workforce
WORKFORCE_BASE_URL=http://workforce:8101
FILE_ROOT=/data/files
```

В автономном режиме `AUTH_MODE=fixture` сервис принимает только токены вида `Authorization: Bearer fixture:<login>` по [actors.json](fixtures/wave-1/actors.json) и явно отдаёт `"auth_mode": "fixture"` в `GET /health`.

## Локальная разработка и запуск тестов одной командой

Из каталога `hr/services/requirements/`:

```bash
uv sync --python 3.13 --dev
uv run pytest -v -rs
```

### Отдельный прогон сценария при отключённом брокере

Автономные тесты сбоя и восстановления брокера (`test_outbox_and_broker.py`) выполняются без внешнего RabbitMQ и включены в общий прогон, либо запускаются отдельно:

```bash
uv run pytest tests/test_outbox_and_broker.py -v
```

Для проверки с настоящими PostgreSQL 17 и RabbitMQ задайте переменные среды и запустите интеграционный маркер:

```bash
TEST_DATABASE_URL=postgresql+psycopg://requirements:requirements@localhost:5433/requirements \
TEST_RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F \
uv run pytest -m integration -v
```

## Параметры outbox и повторов

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `OUTBOX_EXCHANGE` | Topic exchange в RabbitMQ | `w1.requirements` |
| `OUTBOX_POLL_INTERVAL_SEC` | Интервал фонового опроса `outbox_events` (`0` отключает поток) | `1.0` |
| `OUTBOX_MAX_ATTEMPTS` | Лимит попыток до статуса `failed` | `5` |
| `OUTBOX_BASE_BACKOFF_SEC` | Базовая задержка экспоненциального повтора (`base * 2^(attempt-1)`) | `2.0` |
| `FILE_MAX_BYTES` | Максимальный размер загружаемого файла (`413 FILE_TOO_LARGE`) | `20971520` (20 MiB) |

Ручной CLI-запуск одного цикла outbox:

```bash
uv run python -m requirements_service.messaging.outbox --once
```

## Этап 1: запуск без брокера

Приоритет — docs/contracts/wave-1-stage-1.md. Фоновая отправка отключена по умолчанию (OUTBOX_POLL_INTERVAL_SEC=0); сохранённые outbox и /deliveries относятся к дальнейшей интеграции. /health возвращает implementation_stage=1, integration_mode=standalone и auth_mode.

Из services/requirements в PowerShell, с доступной PostgreSQL:

```powershell
uv sync --python 3.13 --dev
$env:DATABASE_URL = 'postgresql+psycopg://requirements:requirements@localhost:5432/requirements'
$env:AUTH_MODE = 'fixture'
$env:OUTBOX_POLL_INTERVAL_SEC = '0'
uv run alembic upgrade head
uv run uvicorn requirements_service.main:app --host 127.0.0.1 --port 8102
```

Swagger: http://127.0.0.1:8102/docs. Для локальной диагностики без PostgreSQL допускается DATABASE_URL=sqlite+pysqlite:///./data/requirements.db (предварительно создайте data). SQLite не заменяет проверку PostgreSQL перед общей интеграцией.

Воспроизводимый учебный API-проход: `uv run pytest tests/test_stage1.py -v -s`. Проверяет источник, возврат, исправление, согласование, v1/v2, историю, OpenAPI и повторное открытие данных/файла. Идентификаторы выводятся в конце. Полный набор: `uv run pytest -q -rs`.

Compose этапа 1 запускает PostgreSQL и API без RabbitMQ. Для дальнейшей проверки доставки: `docker compose -f services/requirements/compose.yml --profile messaging up --build` и OUTBOX_POLL_INTERVAL_SEC=1. Docker-команды на текущем Windows-хосте не проверены. test_stage1 использует отдельный uvicorn-процесс и реальные HTTP-запросы; рестарт завершает процесс и запускает новый на том же хранилище.
