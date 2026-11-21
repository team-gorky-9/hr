# Горький код · продукт команды

Stage 2: [резюме → текущие вакансии](docs/contracts/resume-vacancy-stage-2.md) — приём без отклика, сведения с цитатами, исправления HR, повторное использование проверок и сохранённый результат. [Устройство](docs/modules/resume-vacancy-processing.md) · [Проверка и ограничения](docs/reports/resume-vacancy-stage-2.md). Перед запуском применить `alembic upgrade head` (миграция 0014); провайдер продукта по умолчанию — Яндекс.

ИИ-платформа для кадрового подразделения администрации Нижнего Новгорода: единая база кандидатов из резюме любых форматов, требования должностей, подбор с объяснением, кадровый резерв. Репозиторий для сдачи жюри.

## Что доступно и где запускать

Признание и участие (волна 4A–D): [отдельный пакет recognition](services/recognition/README.md)
с благодарностями, номинациями, семейными событиями, закрытыми сессиями и материалами.
Работает локально с SQLite без Docker; [OpenAPI и наблюдаемые пути](docs/modules/recognition.md).

Команды ниже выполняются из корня этого репозитория. Сейчас продукт состоит из прежнего приложения `app/` и отдельных сервисов. У каждого процесса свои данные, настройки и миграции; один запуск `app.main` не запускает всю систему.

| Контур | Доступные функции и данные | HTTP / инструкция |
|---|---|---|
| Подбор, архив и оценка (`app/`) | Импорт и очистка резюме, версии карточек/профилей, оценка с цитатами, интервью, передачи, этапы, резерв и поиск | `http://127.0.0.1:8000/docs`; [API](docs/modules/api.md), [БД](docs/modules/db.md), [импорт](docs/modules/ingest.md), [оценка](docs/modules/assessment.md) |
| Отчётность | Операционная воронка в legacy API; отдельно годовые снимки из CSV и XLSX в `app/reporting` | Тот же API: `/api/v1/analytics/funnel` и `/api/v1/reports/annual`; [инструкция годового отчёта](docs/modules/reporting.md) |
| Workforce | Сотрудники, оргструктура, назначения, учебные сессии, кадровые события | `http://127.0.0.1:8101/docs`; [запуск](services/workforce/README.md), [принятая автономная проверка](docs/reports/wave-1-workforce.md) |
| Hiring, этап 1 | Дело оформления, комплект и версии документов, подтверждение начала, ручная запись кадрового результата | `http://127.0.0.1:8103/docs`; [запуск](services/hiring/README.md), [автономная проверка и ограничения](docs/reports/wave-1-hiring.md) |
| Mobility, этап 1 | Временные задачи, приватный интерес, версии согласования времени, участие/итог/пакет; отдельное заявление на внутреннюю вакансию с ручным подтверждением HR | `http://127.0.0.1:8105/docs`; [запуск и HTTP-путь](services/mobility/README.md), [проверка](docs/reports/wave-4-mobility.md) |
| Social support, этап 1 | Личное заявление, комплектность, решение, выписка, исполнение | http://127.0.0.1:8106/docs; [запуск](services/social-support/README.md), [проверка](docs/reports/wave-5-support.md) |

Новый сервис Requirements реализуется отдельно по [контракту этапа 1](docs/contracts/wave-1-stage-1.md). Действующий загрузчик `app.requirements` продолжает обслуживать профили старого приложения; автоматическое подключение нового сервиса к оценке ещё не заявляется. Контракты следующих волн описывают задания, а не готовые операции.

### Разные входы и границы передачи

| Потребитель | Доступ |
|---|---|
| Действия подбора на 8000 | `X-User-Login: hr_demo` / `admin_demo`; назначенные департаменты — `dept_demo` / `dept2_demo`. Эти учётки создаёт legacy seed; пароля у этого входа нет |
| Поиск на 8000 | `contour=training` без ключа; рабочий поиск — отдельный серверный Bearer из `HR_SEARCH_WORK_TOKEN` |
| Годовые отчёты на 8000 | Без ключа только учебный каталог; рабочий — собственный Bearer и область `HR_REPORTS_WORK_TOKEN` / `HR_REPORTS_WORK_SCOPE`, заданные в окружении процесса |
| Workforce на 8101 | `POST /api/v1/sessions`, JSON `{"login":"hr","password":"123"}`, `Idempotency-Key: <UUID>` → Bearer-сессия. В `AUTH_MODE=fixture` также допускается `Bearer fixture:hr` |
| Hiring на 8103 | По умолчанию `Authorization: Bearer fixture:hr` или `fixture:candidate`; при `AUTH_MODE=workforce` — Bearer, проверяемый через Workforce. Этот режим пока не подтверждён сквозным прогоном двух сервисов |

Токены поиска, отчётности и Workforce не взаимозаменяемы. Учебные роли и идентификаторы новых сервисов находятся в [общих fixtures](fixtures/wave-1/README.md); legacy `candidate_id` не означает автоматически `employee_id`.

Положительный этап старого отклика сам по себе не создаёт дело Hiring. Этап 1 принимает учебный `selection.json` либо подтверждение HR с указанием источника. После проверки комплекта `start` сохраняет `started`, `workforce_status=not_sent`, `transfer_mode=manual`. HR читает `registration-data`, регистрирует назначение у владельца кадровых данных и записывает его реквизиты через `record-assignment`. Hiring показывает источник и фактическую дату ручного подтверждения. Автоматическая цепочка legacy → Hiring → Workforce относится к дальнейшей интеграции.

Годовой отчёт о подборе принимает обезличенные CSV, рассчитывает показатели по месяцам и формирует XLSX. Команды и контрольный пример приведены в [инструкции модуля](docs/modules/reporting.md).

Загрузчик профилей требований: `uv run python -m app.requirements --help`. Автономный учебный профиль, импорт ДИ и явное утверждение кадровиком описаны в [инструкции requirements](docs/modules/requirements.md).

Шесть профилей по ДИ и матрице поставляются вместе с оригиналами: [состав, решения HR и примеры](fixtures/requirement_profiles/all_six/README.md). После миграций и seed команда `uv run python -m scripts.load_all_six_profiles --commit` загружает все шесть как черновики и выдаёт UUID, источники и версии.

## Запуск базы

Нужны Python 3.13, [uv](https://docs.astral.sh/uv/) и Docker.

```bash
cp .env.example .env
docker compose up -d db
uv sync
uv run alembic upgrade head
uv run python -m app.db.seed
```

На Windows копирование выполняется командой `Copy-Item .env.example .env`. Создавайте `.env` только если своего файла ещё нет. Корневой Compose поднимает только PostgreSQL подбора на 5432; API запускается отдельно. Корневые `uv sync`, `alembic` и `app.db.seed` относятся только к `app/`, а не к сервисам.

`DATABASE_URL` в `.env` указывает на базу приложения. Новая миграция после изменения моделей: `uv run alembic revision --autogenerate -m "<что изменилось>"`, затем проверить файл в `migrations/versions/` руками.

## Отдельный запуск Workforce и Hiring

Корневой `.env` нельзя использовать как Compose-конфигурацию новых сервисов: его `DATABASE_URL` направит контейнер в `localhost:5432/hr`, а `POSTGRES_PORT` заменит сервисный порт на 5432. Для стандартных учебных значений ниже явно передаётся [пустой env-файл](scripts/compose-services.env).

Переменные текущего shell имеют приоритет даже над `--env-file`. Откройте **отдельный терминал для запуска сервисов**, не используемый для legacy, и удалите в нём только перечисленные переопределения. В PowerShell:

```powershell
Remove-Item Env:DATABASE_URL, Env:POSTGRES_PORT, Env:HTTP_PORT, Env:RABBITMQ_URL, Env:AMQP_PORT, Env:MANAGEMENT_PORT, Env:AUTH_MODE, Env:WORKFORCE_URL, Env:SELECTION_SOURCE -ErrorAction SilentlyContinue
```

В bash тот же шаг — `unset DATABASE_URL POSTGRES_PORT HTTP_PORT RABBITMQ_URL AMQP_PORT MANAGEMENT_PORT AUTH_MODE WORKFORCE_URL SELECTION_SOURCE`. Изменяется только окружение этого терминала. Для собственной конфигурации используйте отдельный локальный env-файл сервиса с нужными значениями; реальные секреты не выводите через полный `compose config`.

Первый запуск нужного сервиса (команды независимы):

```text
docker compose --env-file scripts/compose-services.env -f services/workforce/compose.yml up --build -d
docker compose --env-file scripts/compose-services.env -f services/hiring/compose.yml up --build -d
```

Workforce использует API 8101, PostgreSQL 5411, RabbitMQ 5681; Hiring — API 8103 и PostgreSQL 5413, без брокера. Каждый Compose сохраняет свои тома и выполняет подготовку своего сервиса. Сборка нужна при первом запуске или изменении образа; ради обычной проверки готового стенда повторять её не нужно. Для уже созданного проекта используйте прежний `-p <имя>` и его настройки: например, оставленный проверкой Workforce проект называется `workforce-completion`. Второй проект на тех же портах не запускайте, тома для проверки не удаляйте.

Нативные команды и ограничения Docker-проверки Hiring приведены в собственных README выше. Доступность кода в main не означает, что все три API уже запущены на данном компьютере.

## Короткая проверка готового стенда

Для уже настроенного legacy API достаточно прочитать health и учебные вакансии:

```text
curl http://127.0.0.1:8000/api/v1/health
curl "http://127.0.0.1:8000/api/v1/vacancies?contour=training"
```

Health подтверждает доступ к БД; список показывает имеющийся учебный срез, а не качество модели. Для первоначальной подготовки учебных данных существует `uv run python -m scripts.demo_setup --no-llm`: команда применяет миграции/seed, импортирует fixtures и утверждает учебные копии профилей, но не вызывает модель. Она изменяет выбранную БД, поэтому запускайте её осознанно в учебной среде. Вариант без `--no-llm` использует настроенную внешнюю модель.

Для готового Workforce: `GET http://127.0.0.1:8101/health` → 200, `GET /api/v1/session` без credentials → 401. Для Hiring: `GET http://127.0.0.1:8103/health` показывает `implementation_stage=1` и `transfer_mode=manual`; полный короткий учебный путь — `python -m hiring.demo` из окружения сервиса, он записывает синтетические дела и документы. Фактическая область текущей проверки инструкции — [протокол](docs/reports/existing-product-alignment.md).

## Тесты

Полный набор ниже предназначен для отдельной разработки и не требуется для каждой демонстрационной проверки. DB-тесты работают на настоящей PostgreSQL с pgvector: **в начале удаляют всю схему `public` в тестовой БД**, затем создают её миграциями и откатывают каждую проверку. Нужна отдельная база без ценных данных, имя которой оканчивается на `_test`:

```bash
docker compose exec db createdb -U hr hr_test
uv run pytest
```

Адрес задаётся в `TEST_DATABASE_URL` (в том числе через корневой `.env`). Без него тесты базы пропускаются, автономные проверки выполняются. Тестовые БД новых сервисов задаются отдельно по их инструкциям.

## Импорт откликов

```bash
uv run python -m app.ingest --input fixtures/stage_0a --mapping fixtures/stage_0a/mapping.json
```

Команда загружает синтетический контрольный пакет и печатает JSON-отчёт. Ожидаемые счётчики на чистой базе: `imported=2, excluded_non_resume=1, quarantined=1`. Повторный запуск дублей не создаёт. Как подключить реальный архив, переименовать папки через словарь `folders` в `mapping.json` и проверить таблицы, описано в [docs/modules/ingest.md](docs/modules/ingest.md).

## HTTP API

```bash
uv run uvicorn app.main:app --reload
```

Swagger UI — http://127.0.0.1:8000/docs, проверка — `GET /api/v1/health`. Маршруты чтения Этапа 1 и действий кадровика Этапа 2 (этапы с историей, кросс-оценки, резерв, воронка), контуры `working`/`training`, статусы оценки, учебная авторизация `X-User-Login` (учётки `hr_demo`, `dept_demo`, `admin_demo` загружает `python -m app.db.seed`) и переменная `CORS_ORIGINS` описаны в [docs/modules/api.md](docs/modules/api.md), контракт — [docs/contracts/api.md](docs/contracts/api.md).

## Поиск кандидатов

Поиск по профессиональному опыту, точным терминам, навыкам, образованию и действующему резерву. [HTTP-контракт](docs/contracts/search.md) · [Запуск, индексация и учебная проверка](docs/modules/search.md)

## Контрольный набор оценки

```bash
uv run python -m scripts.check_assessment_fixtures
```

Сквозной прогон `py-9001` от импорта до ответа API (утверждение профиля, оценка, цитата) — [docs/modules/assessment.md](docs/modules/assessment.md#сквозной-прогон-py-9001-qa-01).

Синтетический отклик `py-9001` с ожидаемой карточкой, проверками, цитатами и итогом для 12 случаев, включая отрицательные. Описание — [fixtures/assessment/README.md](fixtures/assessment/README.md), устройство модуля — [docs/modules/assessment.md](docs/modules/assessment.md).

## Проверка на реальном резюме

```bash
uv run python -m scripts.smoke_real_candidate "<путь к распакованному архиву Кадры>"
```

Скрипт проводит один отклик из архива организаторов через все таблицы (кандидат, ПДн, карточка, оценка с цитатами, этапы, резерв) и откатывает изменения. Карточка и требования в нём заполнены вручную: это проверка хранения, а не извлечения.

Обратная связь сотрудников: [запуск отдельного сервиса](services/feedback/README.md), [устройство](docs/modules/employee-feedback.md), [короткая проверка](docs/reports/wave-5-feedback.md).
