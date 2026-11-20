# Горький код · продукт команды

ИИ-платформа для кадрового подразделения администрации Нижнего Новгорода: единая база кандидатов из резюме любых форматов, требования должностей, подбор с объяснением, кадровый резерв. Репозиторий для сдачи жюри.

Сейчас готовы:
- каркас базы данных: схема, миграции, справочники, функции доступа и тесты. Устройство — [docs/modules/db.md](docs/modules/db.md);
- импорт откликов с очисткой персональных данных. Устройство — [docs/modules/ingest.md](docs/modules/ingest.md).

## Запуск базы

Нужны Python 3.13, [uv](https://docs.astral.sh/uv/) и Docker.

```bash
cp .env.example .env
docker compose up -d db
uv sync
uv run alembic upgrade head
uv run python -m app.db.seed
```

`DATABASE_URL` в `.env` указывает на базу приложения. Новая миграция после изменения моделей: `uv run alembic revision --autogenerate -m "<что изменилось>"`, затем проверить файл в `migrations/versions/` руками.

## Тесты

Тесты работают на настоящей PostgreSQL с pgvector: создают схему миграцией и откатывают каждую проверку. Нужна отдельная пустая база, имя которой оканчивается на `_test` (защита от запуска на рабочей базе):

```bash
docker compose exec db createdb -U hr hr_test
uv run pytest
```

Адрес задаётся в `TEST_DATABASE_URL`. Без него тесты базы пропускаются, тесты схемы карточки выполняются.

## Импорт откликов

```bash
uv run python -m app.ingest --input fixtures/stage_0a --mapping fixtures/stage_0a/mapping.json
```

Команда загружает синтетический контрольный пакет и печатает JSON-отчёт. Ожидаемые счётчики на чистой базе: `imported=2, excluded_non_resume=1, quarantined=1`. Повторный запуск дублей не создаёт. Как подключить реальный архив, переименовать папки через словарь `folders` в `mapping.json` и проверить таблицы, описано в [docs/modules/ingest.md](docs/modules/ingest.md).

## HTTP API

```bash
uv run uvicorn app.main:app --reload
```

Swagger UI — http://127.0.0.1:8000/docs, проверка — `GET /api/v1/health`. Маршруты чтения Этапа 1, контуры `working`/`training`, статусы оценки и переменная `CORS_ORIGINS` описаны в [docs/modules/api.md](docs/modules/api.md), контракт — [docs/contracts/api.md](docs/contracts/api.md).

## Контрольный набор оценки

```bash
uv run python -m scripts.check_assessment_fixtures
```

Синтетический отклик `py-9001` с ожидаемой карточкой, проверками, цитатами и итогом для 12 случаев, включая отрицательные. Описание — [fixtures/assessment/README.md](fixtures/assessment/README.md), устройство модуля — [docs/modules/assessment.md](docs/modules/assessment.md).

## Проверка на реальном резюме

```bash
uv run python -m scripts.smoke_real_candidate "<путь к распакованному архиву Кадры>"
```

Скрипт проводит один отклик из архива организаторов через все таблицы (кандидат, ПДн, карточка, оценка с цитатами, этапы, резерв) и откатывает изменения. Карточка и требования в нём заполнены вручную: это проверка хранения, а не извлечения.
