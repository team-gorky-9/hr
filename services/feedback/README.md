# Employee feedback · учебный этап 1

Самостоятельный FastAPI/SQLite сервис. [Контракт](../../docs/contracts/wave-5-feedback-stage-1.md).
Из этой папки:

```powershell
uv sync --locked
uv run python -m feedback seed-demo
uv run uvicorn feedback.api:create_app --factory --host 127.0.0.1 --port 8025 --no-access-log
```

`FEEDBACK_DB` задаёт путь файловой SQLite; seed принимает также `--database`.
API не создаёт учётки автоматически. Учебный seed повторяем и не меняет существующие записи.
Локальные bearer-токены: `demo-organizer`, `demo-manager`, `demo-small-manager`,
`demo-alice`, `demo-bob`, `demo-recipient`, `demo-hr`, `demo-outsider`.
Это только учебный контур; реальные токены и личные данные сюда не загружать.
Организатор назначен также выпускающим публикацию; manager относится к `large`,
small-manager — к `small`; alice/bob — сотрудники `large`, outsider — другая организация.
Ключи групп задают непересекающийся учебный справочник, состав людей не хранится в цикле.
Реальные назначения и контроль пересечения аудитории относятся к будущей интеграции.
UUID акторов — `feedback.store.DEMO_IDS`; сервер определяет автора по bearer, не из тела.

Префикс `/api/v1/feedback`; `/docs` и `/openapi.json` — точные HTTP-схемы.
Изменения управленческих объектов принимают `expected_revision`, конфликт — 409,
чужая область — 404, неверный вход — 422. Лишние поля запрещены.

## 5A · цикл и ответ

```powershell
uv run python -m tests.smoke --part 5a
uv run pytest tests/test_cycle.py -q
```

Короткий настоящий HTTP-путь: organizer `POST /cycles` с вопросами/темами/группами →
`POST /cycles/{id}/open {expected_revision:1}` → `/access-codes {group_key,count}` →
публичная `/form` → анонимный `POST /cycles/{id}/responses {access_code,answers,topic_key}` →
organizer `/close`. Скрипт содержит полный JSON учебного запроса, проверяет повтор кода,
ошибку диапазона без расхода кода, лимит выдачи и отказ после закрытия.
После остановки сервера форма перечитывается из той же БД.

Код выдаётся только один раз; хранится SHA-256 случайного 256-битного значения.
Выдача сверх eligible_count блокируется под `BEGIN IMMEDIATE`. Расход и запись ответа
происходят в одной транзакции. Потерянный HTTP-ответ не позволяет восстановить содержание:
повтор возвращает `CODE_ALREADY_USED`. Счётчик выдачи не меняет revision цикла.
Ответ содержит ровно `id,cycle_id,group_key,answers,topic_key`, без учётки, кода/digest,
IP/user-agent, времени или ссылки на именное обращение. Персональные журналы распределения
кодов и read-API ответов отсутствуют. Payload не передаётся в аудит; валидационные ошибки
не возвращают исходный ввод. Cookie и Authorization при подаче не используются.

Пульс добровольный. Внешние сетевые журналы, журналы СУБД и наблюдение оператора могут
связать отправку с человеком; абсолютная анонимность и защита от косвенного узнавания
не заявляются. Этот текст доступен на публичной форме. При развёртывании не включать
body/header/SQL tracing; команда выше отключает access log самого uvicorn.
Управленческие объекты ведутся отдельно в records/history. Брокера, модели и общего
персонального аудита у ответов нет. Высокая нагрузка, PostgreSQL, UI и внешние интеграции
не проверены и относятся к этапу 2.

## 5B · фиксированная публикация

`uv run python -m tests.smoke --part 5b`; короткий тест —
`uv run pytest tests/test_publication.py -q`.
После закрытия organizer вызывает `POST /cycles/{id}/publication` с
`{"expected_revision":3,"policy":{"k":5},"policy_basis":"Учебный пример"}`.
`GET /publications/{id}` читает сохранённый выпуск: организатор целиком,
руководитель только свою группу. Любой query-параметр отвергается (422), общего итога нет.

Группа скрыта, если `n < k` или `n > eligible_count-k`; скрытая группа не содержит n.
Для каждой шкалы и набора тем при любой частоте ниже k скрывается всё распределение.
Категория содержит только свой ключ и `status:suppressed`, чисел нет даже в хранилище
публикации. Это уменьшает полезность результата, но предотвращает восстановление
единственной скрытой категории из остальных. Порог k — учебный параметр, не гарантия.
Первый выпуск неизменяем: повтор тех же policy/policy_basis возвращает прежний ID,
изменение — 409. Уникальный индекс и транзакция запрещают второй выпуск цикла.
Отдельный новый цикл не создаёт автоматического сравнения разностей.

[OpenAPI 5B](../../docs/reports/wave-5b-feedback-openapi.json) ·
[пример 5B](../../docs/reports/wave-5b-feedback-examples.json).

## 5C · мера и итог всей группе

`uv run python -m tests.smoke --part 5c`; `uv run pytest tests/test_actions.py -q`.
Руководитель своей группы или organizer создаёт `POST /measures`:
publication_id, group_key, topic_key, text, owner_actor_id, due_on (дата/null).
Тема должна быть показана в публикации; ответственный — учебный сотрудник той же группы.
`PATCH /measures/{id}` принимает expected_revision, status и outcome_note.
Назначенный ответственный, руководитель группы или organizer переводит planned →
in_progress/completed/cancelled либо in_progress → completed/cancelled.
Завершение и отмена требуют объяснения; терминальные состояния не переписываются.
`GET /measures` читает разрешённые меры, не первичные ответы.

Organizer публикует `POST /publications/{id}/participant-message {text,measure_ids}`.
Непустой уникальный список мер должен принадлежать одному выпуску и одной группе:
группа сообщения определяется ими, дополнительного выбираемого поля нет.
Сообщение сохраняет снимок мер на момент публикации. `GET /cycles/{id}/outcome`
доступен всей приглашённой группе, включая неответивших; список участников пульса не нужен.
Именные данные ответственного принадлежат мере и не выводятся из ответов пульса.
Завершение не доказывает эффект на настроение/текучесть; предупреждение включено в ответ API.

Новый цикл создаётся отдельно. `GET /cycles/{id}/outcome?compare_cycle_id={other}`
показывает comparable и причины QUESTIONS_DIFFER/GROUPS_DIFFER/POLICY_DIFFERS либо
PUBLICATION_PENDING. Числовых разностей и причинного вывода нет; даже при совпадении
методики состав людей мог измениться. Другие query-параметры не поддерживаются.
[OpenAPI 5C](../../docs/reports/wave-5c-feedback-openapi.json) ·
[пример 5C](../../docs/reports/wave-5c-feedback-examples.json).

## 5D · отдельное конфиденциальное обращение

`uv run python -m tests.smoke --part 5d`; `uv run pytest tests/test_confidential.py -q`.
Перед подачей сотрудник получает `GET /confidential-recipients`: назначенные адресаты
его организации, граница видимости и явно учебный ориентир ответа (три рабочих дня,
не обещание рабочего SLA). `POST /confidential-cases {recipient_actor_id,subject,text}`
создаёт именное обращение самого сотрудника; author_actor_id и organization_id определяет сервер.
Принимать response_id, access_code или подставного автора запрещено схемой.
Учебный адресат — actor `recipient` из DEMO_IDS, bearer `demo-recipient`.

`GET /confidential-cases` и `GET /confidential-cases/{id}` доступны автору и конкретному
назначенному получателю; прямое чтение посторонним возвращает 404, список — пустой.
Получатель отвечает `POST /confidential-cases/{id}/reply {expected_revision,text}`;
автор либо получатель закрывает `/close {expected_revision,reason}`.
История хранит все версии и авторов изменений; закрытое обращение не принимает ответ.
Роль HR/organizer/department не предоставляет дополнительного доступа к содержанию.
Таблицы confidential_cases/confidential_history отделены от records и responses,
ссылок на пульс нет. Переход из пульса — новое осознанное именное обращение.
Это не экстренная помощь, диагностика или автоматическое обращение по результатам пульса.

[OpenAPI 5D](../../docs/reports/wave-5d-feedback-openapi.json) ·
[полный учебный путь 5D](../../docs/reports/wave-5d-feedback-examples.json).
Общий короткий набор только этого сервиса: `uv run pytest -q` (четыре сценария).
