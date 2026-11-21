# Внутренняя мобильность · этап 1

Отдельная база и пакет, `/api/v1/mobility`. Учебный вход `mobility-training-v1`
в `fixtures/actors.json`: employee (Марина), owner (Виктор), manager (Ирина),
manager2 (другой согласующий), hr, other и foreign (другая организация).
`Authorization: Bearer fixture:<login>`. Этот вход предназначен для локальной демонстрации.
Данные не относятся к реальным сотрудникам. Запуск не требует соседних сервисов.

Из `services/mobility`, PowerShell:

```powershell
uv sync --locked
New-Item -ItemType Directory -Force data | Out-Null
uv run alembic upgrade head
uv run uvicorn mobility.main:app --host 127.0.0.1 --port 8105
```

`MOBILITY_DATABASE_URL` выбирает отдельную БД (по умолчанию `data/mobility.db`),
`MOBILITY_ACTORS_PATH` — файл подтверждённого учебного оргконтекста.
Миграции обязательны; запуск API сам таблиц не создаёт.
PostgreSQL URL поддержан SQLAlchemy, текущий проверенный контур — SQLite.

## 4A: задача и интерес

1. Owner: `POST /api/v1/mobility/opportunities`:
   `{"organization_id":"00000000-0000-4000-8000-000000000001","owner_actor_id":"00000000-0000-4000-8000-000000000102","title":"Организация практики","result_description":"Подготовить программу","starts_on":"2026-12-01","ends_on":"2026-12-31","time_percent":20}`.
2. Owner: `POST /opportunities/{id}/open {"expected_revision":1}`.
3. Employee: `GET /opportunities`, затем `POST /opportunities/{id}/interests {"comment":"Готова обсудить"}`.
4. Owner: `GET /interests/{id}`, затем `POST /interests/{id}/select {"expected_revision":1}`.
5. Employee: `POST /interests/{id}/withdraw {"expected_revision":2,"reason":"Не подходит период"}`.

Все сокращённые пути имеют префикс `/api/v1/mobility`. GET интереса содержит историю.
Повтор создания возвращает существующий открытый интерес; после закрытия можно создать новый.
Руководитель не читает чужой интерес (404); список интересов отдаёт только свои либо интересы
собственной задачи. Общая роль HR не раскрывает личные интересы. `selected` не создаёт участия.

Проверка через отдельный uvicorn и временную SQLite с миграцией:

```powershell
uv run pytest tests/test_4a.py -q
```

Тест включает перечитывание после остановки и повторного запуска API.
OpenAPI доступен на `/openapi.json`, Swagger — `/docs`.
Для сохранения фактических учебных ответов перед тестом задайте
`$env:MOBILITY_REPORT_DIR = (Resolve-Path ../../docs/reports).Path`.

Устройство — [описание модуля](../../docs/modules/mobility-service.md),
операции — [контракт](../../docs/contracts/wave-4-mobility-stage-1.md).
