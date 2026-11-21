# Волна 6 · карта запуска и учебных ролей

21 ноября 2026 · Давид · для подключения интерфейса Аси и маршрута Маши.
Проверенная база `main`: **`b5e67e43518d701ccf008d25e8e8830fc17bf5da`**.
[Постановка](https://github.com/team-gorky-9/hackaton/blob/main/hq/tasks/stage-1/wave-6a-david-demo-entry.md).
Это карта самостоятельных сервисов, общего gateway и единой авторизации пока нет.

Предыдущая поставка Давида: Feedback 5A–D, PR #74–77, итог `01de7a5`:
цикл, групповой выпуск, меры/итоги и отдельное конфиденциальное обращение.
Четыре коротких HTTP-теста с SQLite/перечитыванием прошли в предыдущей задаче;
здесь они не повторялись. [Протокол](../reports/wave-5-feedback.md).

## Адреса и запуск

Все каталоги ниже относительно корня **продукта `hr/`**. Каждый сервис запускается
в отдельном терминале/окружении. Нужны Python 3.13 и uv, для frontend — Node/npm.
После нативного запуска API доступны `/docs` и `/openapi.json` на указанном base URL.
Команды соседних сервисов взяты из авторских README, связанных в таблице; **в этой
задаче запущен только Workforce**. Наличие инструкции не означает работающий стенд.

| Компонент, каталог и источник | Подготовка → команда запуска | Base URL | Конфигурация и учебный вход |
|---|---|---|---|
| [Legacy: подбор, поиск, отчёт](../../README.md), `hr/` | Создать `.env` из `.env.example`, только если его ещё нет; `docker compose up -d db`; `uv sync --locked`; `uv run alembic upgrade head`; `uv run python -m app.db.seed` → `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000` | `http://127.0.0.1:8000` | Корневой `.env`, `DATABASE_URL`, PostgreSQL/pgvector. `X-User-Login: hr_demo`, `admin_demo`, назначенные `dept_demo`/`dept2_demo`; без пароля. Поиск `contour=training`, отчёты — учебный каталог; рабочие токены отдельно |
| [Workforce: кадры, адаптация, развитие](../../services/workforce/README.md), `services/workforce` | `uv sync --locked`; задать `DATABASE_URL=sqlite:///wave6-workforce.db`, `AUTH_MODE=workforce`; `uv run python -m workforce prepare` → `uv run uvicorn workforce.api:create_app --factory --host 127.0.0.1 --port 8101` | `http://127.0.0.1:8101` | Окружение процесса, `.env` автоматически не читается. `POST /api/v1/sessions`, `hr/123` или `employee/123`, UUID `Idempotency-Key` → серверная Bearer-сессия |
| [Requirements: профили и вакансии](../../services/requirements/README.md), `hr/` | Безопасный Compose ниже: `services/requirements/compose.yml` | `http://127.0.0.1:8102` | Compose + отдельный env; PostgreSQL на 5433, файлы в собственном томе. `AUTH_MODE=fixture`, `Bearer fixture:hr`; `department` — согласующий. При workforce-режиме переменная **`WORKFORCE_BASE_URL`** |
| [Hiring: оформление и кабинет кандидата](../../services/hiring/README.md), `hr/` | Безопасный Compose ниже: `services/hiring/compose.yml` | `http://127.0.0.1:8103` | Compose + отдельный env; PostgreSQL 5413 и том файлов. `Bearer fixture:hr` / `fixture:candidate`, также `candidate2`. `AUTH_MODE=fixture`, `SELECTION_SOURCE=fixture`; workforce-режим использует **`WORKFORCE_URL`** |
| [Students: практика](../../services/students/README.md), `services/students` | `uv sync --python 3.13 --dev`; `New-Item -ItemType Directory -Force data`; `uv run alembic upgrade head` → `uv run uvicorn students.main:app --host 127.0.0.1 --port 8105` | `http://127.0.0.1:8105` | `STUDENTS_DATABASE_URL` (по умолчанию файловая SQLite), `STUDENTS_ACTORS_PATH`, `STUDENTS_MENTOR_CAPACITY`. `Bearer fixture:hr`, `fixture:candidate`; наставник `fixture:department` |
| [Social support](../../services/social-support/README.md), `services/social-support` | `uv sync --python 3.13 --dev` → `uv run uvicorn support.main:app --host 127.0.0.1 --port 8106` | `http://127.0.0.1:8106` | `SUPPORT_DATA_DIR` (по умолчанию `data/`), `SUPPORT_ACTORS_PATH`; создание БД при старте. `Bearer fixture:employee`, `fixture:specialist`, `fixture:secretary`, `fixture:coordinator`, `fixture:executor` |
| [Mobility](../../services/mobility/README.md), `services/mobility` | `uv sync --locked`; `New-Item -ItemType Directory -Force data`; `uv run alembic upgrade head` → `uv run uvicorn mobility.main:app --host 127.0.0.1 --port 8107` | `http://127.0.0.1:8107` | `MOBILITY_DATABASE_URL` (SQLite `data/mobility.db`), `MOBILITY_ACTORS_PATH`. `Bearer fixture:employee`, `fixture:owner`, `fixture:manager`, `fixture:hr`. **8107 выбран здесь**, поскольку авторский 8105 занят Students; команда с заменённым портом не запускалась |
| [Recognition: признание, семейное участие, сессии](../../services/recognition/README.md), `services/recognition` | `uv sync --locked`; `uv run python -m recognition seed-demo` → `uv run uvicorn recognition.api:create_app --factory --host 127.0.0.1 --port 8024` | `http://127.0.0.1:8024` | `RECOGNITION_DB`; если изменён, seed передать тот же путь через `--database`. Bearer `demo-alice`/`demo-bob` — сотрудники, `demo-organizer`, `demo-moderator`, `demo-reviewer`, `demo-facilitator` — назначенные роли |
| [Feedback](../../services/feedback/README.md), `services/feedback` | `uv sync --locked`; `uv run python -m feedback seed-demo` → `uv run uvicorn feedback.api:create_app --factory --host 127.0.0.1 --port 8025 --no-access-log` | `http://127.0.0.1:8025` | `FEEDBACK_DB`; seed `--database` при своём пути. Bearer `demo-organizer`, `demo-manager`, `demo-alice`, `demo-bob`, `demo-recipient`. HR не получает именное обращение по одной общей роли |
| [React-прототип](../../frontend/package.json), `frontend` | `npm ci --no-audit --no-fund` → `npm run dev -- --host 127.0.0.1 --port 5173 --strictPort` | `http://127.0.0.1:5173` | `vite.config.ts`, локальные демонстрационные роли. Это не вход Workforce. Авторское [наблюдение #78](../reports/wave-6-recruitment-demo.md): кабинет использовал макетные данные, запросов к API не было |

Нативная SQLite Workforce достаточна для ручного кадрового назначения и ознакомления.
Worker/RabbitMQ для этого пути не нужны; обмен событиями этим запуском не проверяется.
Для исходного учебного подбора есть `uv run python -m scripts.demo_setup --no-llm`
из `hr/`: команда изменяет выбранную учебную БД, модель не вызывает. Для маршрута
кандидата #78 автор использовал `uv run python -m app.search load-demo` и
`uv run python -m hiring.recruitment_demo --legacy-url http://127.0.0.1:8000`
из `services/hiring`; точные условия и ручная учебная связь — в отчёте #78 выше.

## Compose без подхвата legacy `.env`

Принятое [исправление запуска](../reports/existing-product-alignment.md) обязательно
и для этой карты. В отдельном PowerShell из `hr/` убрать переопределения процесса,
затем выполнить **только нужную** строку сервиса:

```powershell
Remove-Item Env:DATABASE_URL, Env:POSTGRES_PORT, Env:HTTP_PORT, Env:RABBITMQ_URL, Env:AMQP_PORT, Env:MANAGEMENT_PORT, Env:AUTH_MODE, Env:WORKFORCE_URL, Env:WORKFORCE_BASE_URL, Env:SELECTION_SOURCE, Env:POSTGRES_USER, Env:POSTGRES_PASSWORD, Env:POSTGRES_DB, Env:REQUIREMENTS_PG_PORT, Env:REQUIREMENTS_PORT, Env:FILE_ROOT, Env:FILE_MAX_BYTES, Env:OUTBOX_POLL_INTERVAL_SEC, Env:OUTBOX_MAX_ATTEMPTS, Env:OUTBOX_BASE_BACKOFF_SEC, Env:SEED_ON_STARTUP -ErrorAction SilentlyContinue
docker compose --env-file scripts/compose-services.env -f services/workforce/compose.yml up --build -d
docker compose --env-file scripts/compose-services.env -f services/hiring/compose.yml up --build -d
docker compose --env-file scripts/compose-services.env -f services/requirements/compose.yml up --build -d
```

Пустой [compose-services.env](../../scripts/compose-services.env) отключает чтение
корневого `.env`; shell всё равно имеет приоритет, поэтому очистка необходима.
Для своей конфигурации используйте отдельный локальный env сервиса. Не выводите
полный config с реальными секретами. Workforce Compose поднимает PostgreSQL 5411,
RabbitMQ 5681 и worker; Hiring и Requirements этапа 1 запускаются без брокера.
Тяжёлая сборка и повтор инфраструктурной проверки в этой задаче не выполнялись.

## Проверенный путь Workforce

Один короткий проход на **синтетических** данных, Python 3.13.7, SQLite,
`AUTH_MODE=workforce`, без внешних сервисов. Из `services/workforce`:

```powershell
uv sync --locked --python 3.13
uv run python -m tests.support.onboarding_smoke
```

В текущей Windows-среде системный alias `python` не работает; после `uv sync --locked`
фактическая команда — `.venv/Scripts/python.exe -m tests.support.onboarding_smoke`.
Завершилась с кодом 0 за 7,51 с. Скрипт сам поднимает loopback API на свободном порту,
создаёт отдельную SQLite, выполняет HTTP и останавливает сервер. Напечатанный каталог
содержит `workforce.db` и `openapi.json`; БД содержит учебные сессии и не публикуется.

| Шаг и вход | Наблюдаемый результат |
|---|---|
| `POST /api/v1/sessions`, `{"login":"hr","password":"123"}`, `Idempotency-Key: <новый UUID>` | 201, Bearer-сессия HR, actor `00000000-0000-4000-8000-000000000101` |
| HR `POST /api/v1/employees`: `display_name="Марина Учебная"`, `source_refs=[{system:"test",id:<UUID>}]`, `account_actor_id="00000000-0000-4000-8000-000000000104"`, `confirmation_basis="Учебное подтверждение"`; новый ключ команды | 201, кадровая запись связана с учебным `employee` |
| HR `POST /api/v1/employees/{employee_id}/assignments`: `department_id="00000000-0000-4000-8000-000000000011"`, `position_code="economist-training"`, `starts_on="2026-01-01"`, `basis={reference:"DEMO-21",issued_on:"2026-11-21"}`; новый ключ | 201, действующее назначение |
| HR `POST /api/v1/onboarding/programs`: `{workforce_assignment_id:<assignment_id>,template_code:"intro-v1",template_version:1}` | 201, снимок трёх материалов, 0/3, revision 1; повтор — 200 с прежним ID |
| `employee/123` входит через sessions; читает программу и вызывает `POST /api/v1/onboarding/programs/{id}/steps/{key}/acknowledge` с `expected_revision=1`, затем 2, затем 3 | Шаги `introduction`, `contacts`, `first-day`; 200, последовательно 1/3 → 2/3 → 3/3 |
| HR перечитывает программу; повтор первой отметки сотрудником с revision 1 | `intro_completed`, 3/3, revision 4; повтор возвращает ту же запись, без нового достижения |
| HR пытается отметить шаг за сотрудника; другая employee-учётка читает завершённую программу | 403 для отметки HR; 404 и пустой список для `employee_other` в той же организации |
| HTTP остановлен; новая SQLAlchemy-сессия читает SQLite | Та же программа, revision 4, три сохранённых отметки |

Идентификаторы этого прогона (при повторе будут другие):

| Объект | ID |
|---|---|
| Employee | `0b846c39-1c57-4219-bbfa-710ad6a1162b` |
| Assignment | `707251f8-d61c-4427-bef4-34612fb04db4` |
| Program | `1053d687-a7a0-47dd-bcb0-4a1d760d4cdd` |

Скрипт дополнительно проверил недоступность несвязанной программы, повтор назначения
и наличие шести onboarding-операций в живом OpenAPI. Учебный `employee_other`
создаётся только этим smoke (actor `00000000-0000-4000-8000-000000000204`), обычный
`prepare` его не добавляет. `intro_completed` означает ознакомление, не итог испытания.

После smoke API повторно запущен на той же БД:

```powershell
# Подставить каталог artifacts из вывода smoke; прямые слеши подходят и на Windows.
$env:DATABASE_URL = 'sqlite:///C:/path/from/artifacts/workforce.db'
$env:AUTH_MODE = 'workforce'
uv run uvicorn workforce.api:create_app --factory --host 127.0.0.1 --port 18101 --no-access-log
```

Порт 8101 был занят, чужой процесс не изменялся. Новый вход hr/123 и HTTP-чтение
`/api/v1/session`, `/api/v1/employees/{employee_id}` и `/api/v1/onboarding/programs/{id}`
на 18101 подтвердили того же HR, кадровую запись и `intro_completed / 3 / 3 / revision 4`.
Сессия повторного чтения отозвана через `DELETE /api/v1/session`.

**Браузерное наблюдение:** Google Chrome, `http://127.0.0.1:18101/docs`.
Инструмент управления браузером показал `Workforce 1.0 / OAS 3.1`, `Authorize`,
`POST /api/v1/sessions`, операции employees, шесть операций onboarding и development.
Это наблюдение живого Swagger, а не проверка подключённого кабинета HR/сотрудника.
Основные действия и сохранение выше выполнены настоящим HTTP-клиентом.

## Передача и ограничения

Ася получает base URL, раздельные входы и последовательность API выше. Bearer Workforce
не подставляется в legacy `X-User-Login` или `demo-*` других сервисов. Кадровые
`employee_id`/`assignment_id` нельзя заменять `candidate_id` из подбора. Общие акторы —
[actors.json](../../fixtures/wave-1/actors.json); отдельные сервисы используют свои fixtures.

Недоступные/неподтверждённые зависимости: подключённый UI — задачи Аси; общий вход
между сервисами, автоматическая передача Hiring → Workforce и CORS/proxy общего UI —
отдельная интеграция. Hiring этапа 1 сохраняет явно ручное кадровое подтверждение.
При сверке GitHub PR практики [#79](https://github.com/team-gorky-9/hr/pull/79) и помощи
[#80](https://github.com/team-gorky-9/hr/pull/80) ещё открыты: их отчёты не включены в
проверенный SHA; авторские README уже доступных сервисов используются независимо.

Новых прикладных дефектов в выбранном пути не найдено; код и контракты не менялись.
Сохранено предупреждение Starlette о TestClient/httpx. PostgreSQL, Docker, RabbitMQ,
рабочие данные, нагрузка, общая UI-интеграция и полные тестовые наборы здесь не проверялись.
Дальнейшая инфраструктурная проверка относится к этапу 2, новые функции волны 7 не добавлялись.
