# Hiring · оформление выбранного кандидата (первая волна, этап 1)

Отдельный сервис: от положительного решения по отклику до подтверждённого выхода на работу. Контракты: [этап 1](../../docs/contracts/wave-1-stage-1.md) (приоритет), [hiring](../../docs/contracts/wave-1-hiring.md), [common](../../docs/contracts/wave-1-common.md). Устройство — [docs/modules/hiring-service.md](../../docs/modules/hiring-service.md), итог проверки — [docs/reports/wave-1-hiring.md](../../docs/reports/wave-1-hiring.md).

Этап 1: передача в кадровый учёт ручная (`transfer_mode=manual`). Сервис не зависит от RabbitMQ и соседних API. Вход по умолчанию — учебные акторы `AUTH_MODE=fixture`.

## Запуск из чистого клона

Нужны Python 3.13, [uv](https://docs.astral.sh/uv/) и PostgreSQL 16+ (в compose — 17).

```bash
cd services/hiring
uv sync
# своя база; пример для локального PostgreSQL
createuser hiring --pwprompt        # пароль hiring
createdb hiring -O hiring
createdb hiring_test -O hiring    # для тестов
export DATABASE_URL="postgresql+psycopg://hiring:hiring@localhost:5432/hiring"
uv run python -m hiring serve          # применяет миграции и слушает 127.0.0.1:8103
```

Во втором терминале — учебный проход через HTTP:

```bash
cd services/hiring
uv run python -m hiring.demo
```

Через Docker (API + PostgreSQL 17, тома `db` и `files`):

```bash
docker compose -f services/hiring/compose.yml up --build
```

Учебный набор не требует отдельной загрузки: акторы и положительные решения читаются из `fixtures/wave-1/actors.json`, `fixtures/wave-1/selection.json` и `services/hiring/fixtures/extra-selections.json` (второй учебный кандидат для отзыва). Повторный `hiring.demo` находит активное дело Марины и печатает его состояние: дубль не создаётся.

## Тесты

```bash
cd services/hiring
export HIRING_TEST_DATABASE_URL="postgresql+psycopg://hiring:hiring@localhost:5432/hiring_test"
uv run pytest -q
```

Тесты пересоздают схему `public` в указанной базе. Используйте отдельную тестовую базу. Брокер не нужен: прогон «при отключённом брокере» совпадает с обычным.

В Docker: `docker compose -f services/hiring/compose.yml --profile test run --rm tests`.

## Настройки

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://hiring:hiring@localhost:5413/hiring` | своя БД сервиса; для интеграции — URL общего стенда |
| `AUTH_MODE` | `fixture` | `fixture`: `Bearer fixture:<login>` из actors.json; `workforce`: тот же Bearer проверяется `GET /api/v1/session` Workforce |
| `WORKFORCE_URL` | `http://localhost:8101` | адрес Workforce для `AUTH_MODE=workforce` |
| `SELECTION_SOURCE` | `fixture` | `fixture`: принимаются только учебные решения из файлов; `manual-confirmed`: решение вводит уполномоченный HR, источник виден в деле |
| `FIXTURE_DIR` | `<repo>/fixtures/wave-1` | акторы и selection.json |
| `EXTRA_SELECTIONS_FILE` | `fixtures/extra-selections.json` | дополнительные учебные решения |
| `FILE_ROOT` | `services/hiring/.files` | оригиналы файлов, `<organization>/<document_id>` |
| `FILE_MAX_BYTES` | `20971520` | лимит файла, превышение — 413 `FILE_TOO_LARGE` |

## Пример входа и выхода

```bash
curl -s -X POST localhost:8103/api/v1/cases \
  -H 'Authorization: Bearer fixture:hr' -H "Idempotency-Key: $(uuidgen)" -H 'Content-Type: application/json' \
  -d "{\"selection\": $(cat ../../fixtures/wave-1/selection.json),
       \"checklist\": [{\"key\":\"passport\",\"title\":\"Копия паспорта\",\"required\":true}],
       \"checklist_version\": \"training-1\"}"
```

Ответ `201` — дело: `status=preparing`, `revision=1`, `workforce_status=not_sent`, `transfer_mode=manual`, `provenance.source_mode=fixture`, `checklist[0].status=requested`. Повтор того же `application_ref` возвращает `200` и то же дело.

После `start` HR читает `GET /cases/{id}/registration-data`, регистрирует сотрудника в Workforce или внешней кадровой системе и записывает результат `POST /cases/{id}/record-assignment`. Полный порядок вызовов — в `hiring/demo.py`.
