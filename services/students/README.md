# Практика студентов · функциональная волна 3

Собственный FastAPI API `/api/v1/students`, постоянная БД и явный fixture-вход. Наставник получает права через конкретное Placement, студент — только через свой actor_id. Учебные данные не устанавливают регламент вуза.

Из `services/students` (PowerShell):

```powershell
uv sync --python 3.13 --dev
New-Item -ItemType Directory -Force data
uv run alembic upgrade head
uv run uvicorn students.main:app --host 127.0.0.1 --port 8105
```

OpenAPI: `/openapi.json`, Swagger: `/docs`. Настройки с префиксом `STUDENTS_`: DATABASE_URL (по умолчанию файловая SQLite), ACTORS_PATH, MENTOR_CAPACITY (1). Для PostgreSQL: `postgresql+psycopg://...`; этот режим пока не проверен.

Токены `Bearer fixture:hr`, `candidate`, `candidate2`, `department` (наставник), `employee` (другой наставник), `hr_other` (чужая организация). Формат actors.json соответствует первой волне. Только учебные учётные записи; сетевого входа Workforce нет.

## 3A

HR создаёт и публикует Opportunity; кандидат подаёт Application; HR назначает Placement с confirmation_basis или отклоняет с reason. Студент может отозвать заявку до назначения. GET списков/карточек ограничен организацией и конкретным участником. GET opportunities для студента показывает published с available_places > 0.

Запись сериализуется короткой транзакцией: SQLite BEGIN IMMEDIATE, PostgreSQL advisory-lock организации. Места расходуются назначениями, повтор assign возвращает прежнее участие. Окончание участия не освобождает уже использованное место этого набора; расширение/переназначение — отдельный сценарий. Лимит наставника относится к active-участиям с пересекающимися включительно датами и вынесен в конфигурацию.

Хранилище — типизированные в API документы в SQL-оболочке kind/id/organization/revision. Ссылки проверяет доменный слой. Каждая редакция сохраняет отдельный снимок в student_history; GET заявок/участий содержит history. Такая модель сохраняет версии без перезаписи прошлых снимков. Все изменения одной команды атомарны. Цена сериализации — ограничение пропускной способности записи; это локальная функциональная поставка.

Проверка: `uv run pytest tests/test_3a.py -q -s`. Отдельный uvicorn, реальные HTTP, две заявки на одно место, точечная проверка конкурентного назначения и нагрузки наставника, чужой доступ, повтор и перезапуск. Тест создаёт собственную временную SQLite. Для постоянной демонстрации API использовать запуск выше.

## 3B: задание и проверка

Назначенный наставник создаёт POST /placements/{id}/tasks с title,description,criteria[{key,text,required}]. До первой сдачи можно опубликовать новую версию; после сдачи критерии этого пути фиксированы. GET tasks возвращает current и историю items. Студент создаёт submissions с task_version_id,text,artifact_url?; ссылка помечается external_mutable_link, её копия не хранится.

POST /submissions/{id}/review принимает results по всем критериям данной версии. Результат confirmed/needs_revision/not_verified и reason обязательны. Точный повтор того же автора возвращает тот же отзыв; изменение отзыва требует новой попытки. GET submissions показывает все попытки и их отзывы, work_state различает task_required/awaiting_submission/awaiting_review/needs_revision/not_verified/confirmed.

HR меняет наставника через POST /placements/{id}/mentor с expected_revision,mentor_actor_id,reason. Проверяются принадлежность организации и нагрузка на период. Старый автор отзыва сохраняется, старый наставник теряет доступ и право нового решения. Проверка: `uv run pytest tests/test_3b.py -q -s`.
