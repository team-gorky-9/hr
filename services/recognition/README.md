# Recognition · этап 1

Изолированный API признания и участия. Python 3.13, FastAPI и файловая SQLite.
Общий вход, PostgreSQL, брокер, UI и клинические данные не требуются.
Контракт: [волна 4](../../docs/contracts/wave-4-motivation-stage-1.md).

Из этой папки:

```powershell
uv sync --locked
uv run python -m recognition seed-demo
uv run uvicorn recognition.api:create_app --factory --host 127.0.0.1 --port 8024
```

`RECOGNITION_DB` задаёт путь БД для API, `--database` — тот же путь для seed.
Без seed БД пустая; запуск API никогда автоматически не создаёт учебные учётки.
Повтор seed не меняет существующих акторов и записей.
Учебные bearer-токены `demo-alice`, `demo-bob`, `demo-reader`, `demo-moderator`,
`demo-moderator2`, `demo-organizer`, `demo-reviewer`, `demo-manager`, `demo-facilitator`,
`demo-outsider` предназначены только для локального демонстрационного контура.
В БД сохраняются хеши токенов. Все акторы имеют employee; HR-роль не заменяет явное
назначение moderator/organizer/publisher. Outsider принадлежит другой организации.
UUID акторов доступны в `recognition.store.DEMO_IDS`, выбор адресата — по этому учебному справочнику.

OpenAPI: `http://127.0.0.1:8024/openapi.json`, интерактивные команды: `/docs`.
Префикс всех операций — `/api/v1/recognition`. Неизвестные поля тела отвергаются.
Списки принимают `limit` (1–100), `cursor` (UUID); `next_cursor` — следующий курсор.
История содержит прежние снимки, редакцию, автора операции и дату. Она не попадает на стену.

## 4A · короткий HTTP-путь

```powershell
uv run python -m tests.smoke --part 4a
```

Команда сама поднимает API на loopback, создаёт отдельную учебную БД и проходит:
`POST /thanks` (alice → bob) → bob `/visibility` organization → moderator `/moderation`
returned с причиной → alice `PATCH /thanks/{id}` → новое согласие bob → approved.
Reader видит только текущий текст. Отзыв bob удаляет запись со стены. Проверяются
404 чужому руководителю/модератору на личную запись, 409 устаревшей редакции и
самоодобрения; после остановки и нового запуска запись перечитывается.
Каждая изменяющая команда передаёт `expected_revision` из последнего ответа.

Артефакты для макета: [OpenAPI](../../docs/reports/wave-4a-openapi.json),
[наблюдаемые ответы](../../docs/reports/wave-4a-examples.json).
Короткий автономный тест: `uv run pytest tests/test_thanks.py -q`.

## Хранение и границы

4D: `uv run python -m tests.smoke --part 4d` записывает сотрудника на
`confidential_session`: одно место, без семейных полей. Ведущий задаётся организатором
в `facilitator_actor_id` и видит список только этой сессии; руководитель читает только
собственную запись. Перенос и отмена используют тот же механизм резервирования.
Материал создаётся с `distribution_basis` — основанием распространения — и аудиторией
`{"kind":"organization"}` либо `{"kind":"actors","actor_ids":["UUID"]}`.
Только автор управляет своими версиями. Публикация открывает URL аудитории;
отзыв удаляет материал из её каталога, по прежнему ID возвращает причину без URL/истории.
Это прекращает выдачу ссылки нашим API, но не отзывает уже скачанное или сторонний URL.
Новое содержание: POST нового объекта с `version=previous.version+1` и `supersedes_id`;
старый объект и история остаются неизменными. Новая версия проходит отдельную публикацию.
Каждая версия отзывается явно, новая публикация не отзывает предыдущую автоматически.
[OpenAPI 4D](../../docs/reports/wave-4d-openapi.json) ·
[ответы 4D](../../docs/reports/wave-4d-examples.json).
Пример использует `example.org` как заведомо учебную ссылку; воспроизведение курса не проверяется.


4C: `uv run python -m tests.smoke --part 4c` создаёт событие на три места, подтверждает
семью из трёх, ставит следующую группу из двух в очередь. Отмена → предложение →
подтверждение. Предложение сразу резервирует места. Перенос даты сохраняет эти два
места и требует нового ответа; старое `agreed_event_revision` сохраняется до ответа.
Проверяются повторная действующая регистрация, предложение при нехватке мест и чужое
чтение. Места считаются под блокировкой SQLite в функции регистрации/предложения;
частичный уникальный индекс запрещает две активные записи одного event+actor.
Организатор может отменить запись с причиной; ведущий такого права не получает.
Возрастные категории фиксированы: 0–3, 4–6, 7–12, 13–17, по одному элементу на ребёнка.
Имена/фотографии родственников не принимаются. Завершение события не доказывает посещение.
[OpenAPI 4C](../../docs/reports/wave-4c-openapi.json) ·
[ответы 4C](../../docs/reports/wave-4c-examples.json).


4B: `uv run python -m tests.smoke --part 4b` проходит создание/открытие кампании,
номинацию, согласие, конфликт автора-рассматривающего, замену через PATCH campaign,
решение и отдельное разрешение публикации. Второй кандидат отказывается и отсутствует
в итогах. После перезапуска selected/allowed перечитывается. Даты включительны, день
вычисляется по Москве. PATCH меняет только рассматривающего с причиной; условия
открытой кампании не редактируются. История сохраняет прежнее назначение и автора решения.
[OpenAPI 4B](../../docs/reports/wave-4b-openapi.json) ·
[ответы 4B](../../docs/reports/wave-4b-examples.json).


SQLite-таблицы actors, records и history: индексируемые ключи/область/статус хранятся
отдельно от JSON-снимка типизированного объекта. Запись и её история коммитятся вместе.
Все команды проходят `BEGIN IMMEDIATE`; этот межпроцессный замок охватывает проверку
ревизии, предметные проверки и запись. Для маленького локального контура это даёт
определённую последовательность изменений без отдельного счётчика/брокера.
Чтения также используют короткую транзакцию; высокая нагрузка и распределённый запуск
не проверены. Версии схемы и перенос на общую инфраструктуру — продолжение этапа 2.
Учебные сценарии не доказывают эффект на мотивацию или пригодность рабочих регламентов.


## Employee frontend integration (2026-11-21)

The existing employee pages now use this service's stored data, revisions and commands.
The service still uses its original training authentication; it is not a Workforce production-session integration.
The UI explicitly identifies the training account, and does not treat the global role selector as authorization.
Added authenticated directories expose only the records visible to the same actor under existing detail access rules.
No access codes, token hashes or anonymous survey answers are included in directories.

`GET /api/v1/recognition/session`, `/colleagues`, `/nominations` and `/thanks?view=moderation` supply readable choices and work lists. The colleague directory contains names and IDs in the same organization. Nominations retain participant/reviewer visibility. Moderation includes only items whose recipient agreed to organization visibility; it exposes no historical private snapshots.
