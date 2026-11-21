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

## 4B: версия условий и согласование

1. Owner создаёт `POST /interests/{id}/proposal`:
   `{"starts_on":"2026-12-01","ends_on":"2026-12-31","time_percent":20,"manager_actor_id":"00000000-0000-4000-8000-000000000103","manager_source_reference":"fixture:mobility-training-v1:employee-manager"}`.
2. Employee: `POST /proposals/{id}/employee-response {"expected_revision":1,"accepted":true}`.
3. Manager: `POST /proposals/{id}/manager-response {"expected_revision":2,"accepted":false,"reason":"Прошу начало позже"}`.
4. Owner: `PATCH /proposals/{id} {"expected_revision":3,"starts_on":"2026-12-15","reason":"Период уточнён"}`.
5. Employee подтверждает revision 4; manager подтверждает revision 5. GET показывает
   `agreed`, revision 6 и точные даты; оба ответа относятся к `conditions_revision=2`.

`uv run pytest tests/test_4b.py -q` воспроизводит этот путь, смену подтверждённого
назначения в отдельной копии fixture и перечитывание после рестарта. Произвольная
строка source_reference не даёт полномочия. Согласование собственного времени запрещено.

При смене руководителя локальный источник должен подтвердить новое назначение и
отозвать прежнее. Владелец вызывает существующий POST proposal с новым адресатом/
источником: старое предложение становится withdrawn, новое ссылается на него.
История не переносит согласия. Повтор того же POST возвращает существующее предложение.
Для новых дат прежнего адресата используется PATCH. После start условия неизменяемы.

Manager не читает предложение до разрешения сотрудника; PATCH снова закрывает ему
новые условия до согласия сотрудника. Из истории ему доступны только раскрытые
редакции его назначения; интерес и комментарий сотрудника не возвращаются.

## 4C: участие, результат, постоянная вакансия

1. Owner вызывает `POST /proposals/{id}/start {"expected_revision":6}` после
   согласований примера 4B. Получает Participation с revision 1, статусом active,
   proposal_revision 6. Повтор с той же revision возвращает тот же ID.
2. Employee/owner/действующий согласующий читают `GET /participations/{id}`.
3. Owner: `POST /participations/{id}/finish {"expected_revision":1,"outcome":"completed","result_note":"Подготовлены программа и расписание"}`.
   Для досрочного окончания outcome=`stopped`, фактический итог обязателен.
4. Employee: `POST /participations/{id}/employee-feedback {"expected_revision":2,"accepted":false,"note":"Расписание требует уточнения"}`.
   Несогласие не переписывает текст владельца.
5. Employee: `POST /participations/{id}/result-package {"purpose":"Развитие: планирование практики","share_allowed":true}`.
   Сохраняется снимок с автором итога и отдельным ответом сотрудника. Личные комментарии
   интереса и причины согласования времени исключены. `share_allowed=false` означает
   личную копию без права передачи. Обе версии остаются `delivery_status=not_sent`:
   автоматической отправки нет. GET участия возвращает пакеты только сотруднику.
6. Отдельно employee: `POST /vacancy-interests {"vacancy_ref":"fixture:internal-analyst-v1","publication_revision":1,"comment":"Хочу обсудить переход"}`.
   Статус prepared; кадровая должность не меняется.
7. HR: `POST /vacancy-interests/{id}/record-consideration {"expected_revision":1,"consideration_ref":"fixture:recruitment-case-77","confirmation_basis":"Учебное рассмотрение зарегистрировано вручную"}`.
   GET возвращает recorded, source_mode=`manual-confirmed`, автора и основание.
   Это запись подтверждения рассмотрения, а не решение о переводе.

`uv run pytest tests/test_4c.py -q` проходит этот путь, проверяет запрет начала без
согласия, неизменность начатых условий, приватность и сохранение после рестарта.
Полный адресный набор сервиса — `uv run pytest -q`; это три коротких сценария,
без стрессовых прогонов и без запуска полного тестового набора продукта.

Для следующего потребителя: [OpenAPI всех трёх частей](../../docs/reports/wave-4c-mobility-openapi.json),
[примеры](../../docs/reports/wave-4c-mobility-examples.json),
[протокол и границы проверки](../../docs/reports/wave-4-mobility.md).
