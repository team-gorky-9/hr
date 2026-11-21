# Единое окно взаимодействия: серверный запуск

Окно находится в Hiring и объединяет разрешённые страницы кабинета кандидата и legacy-подбора. [Контракт v1](../contracts/interaction-window.md), [протокол](../reports/interaction-window.md). UI окна — следующая задача интерфейса; эта поставка даёт HTTP, предметные команды и защищённый учебный запуск.

## Как проходит дело

HR создаёт Q1 через `candidate-requests/{R1}/information-request`. Кандидат видит свой ход, HR — ожидание кандидата. Прочтение сообщения сохраняет `read_at`, но не закрывает Q1. Дополнение с Q-ref и актуальной revision возвращает обращение HR; тот отдельно выполняет `ready` с основанием. При замене Q1 на Q2 старый Q-ref отклоняется даже при свежей revision.

По отклику A1 существуют независимые H1/H2. Ответ на H1 не меняет этап A1 и не закрывает H2. HR выбирает точную версию ответа и записывает review: продолжает ждать либо атомарно меняет этап. Исправленная версия ответа снова требует разбора. Отзыв доступа к H1 не завершает предметное ожидание и не отнимает независимый доступ к H2. Общей таблицы задач, транзакции между сервисами и автоматического решения за HR нет.

## Закрытый учебный контур

Профиль предназначен для отдельного synthetic O1/training. По умолчанию `INTERACTION_ENABLED=false`; реальные identity и tenant-изоляция legacy не заявляются.

1. Подготовить учебные БД и данные по [корневому README](../../README.md), [Hiring README](../../services/hiring/README.md) и [Compose-инструкции](deployment.md). Для legacy выполнить `uv run alembic upgrade head` (миграция `0014`), затем обычный `uv run python -m app.db.seed`. Новых колонок Hiring нет: Q sequence хранится в существующем JSON запроса и истории.
2. Скопировать [пример mapping](../../services/hiring/fixtures/interaction-mapping.example.json) в `deploy/local/interaction-mapping.json`. В целевой учебной БД legacy прочитать `SELECT id, login, role, is_active FROM users ORDER BY login;`, явно выбрать User UUID для HR/департамента и заменить placeholders. Совпадение логинов не устанавливает связь. Для Workforce issuer=`workforce`, actor/org/scope берутся из проверенной сессии этой установки; fixture-пример не является рабочим входом.
3. В локальном env Compose задать разные случайные `INTERACTION_GATEWAY_KEY` и `INTERACTION_CURSOR_SECRET` (например, по 32 случайных байта). Не помещать их в frontend, mapping или Git. Запустить с обычным release/env-файлом:

```bash
docker compose --env-file deploy/local/runtime.env -f deploy/compose.yaml -f deploy/compose.interaction.yaml up -d --build
```

Профиль включает fixture-вход Hiring, фиксирует O1 и `training-legacy`, монтирует mapping только для чтения. Legacy не публикует порт; Nginx закрывает `/legacy/`. Каждый legacy-маршрут, включая старые, требует внутренний ключ. Nginx удаляет пришедшие от клиента служебные заголовки; health-check передаёт ключ самостоятельно. Не публикуйте legacy порт отдельным override.

Hiring сам выбирает `X-User-Login` и `X-Interaction-User-Id`. Legacy проверяет активность, неизменный User UUID и предметные права. Перед переходом по ID шлюз проверяет training-принадлежность объекта. Browser-заголовок, пересозданный пользователь с прежним логином и известный UUID рабочего отклика не дают доступ.

Mapping содержит issuer, actor_id, organization_id, contour, instance_id, legacy_user_id/login/role, scope_type/id, revision и active. Удаление/деактивация или неоднозначность дают `not_linked`; файл перечитывается каждый запрос. При изменении соответствия увеличить revision. При bind mount редактировать содержимое файла на месте либо пересоздать Hiring-контейнер после атомарной замены файла. Отзыв конкретного H1 выполняется предметной командой, не изменением mapping.

## HTTP для интерфейса

Через Compose префикс `/hiring/api/v1`, напрямую у Hiring — `/api/v1`:

```http
GET /hiring/api/v1/interaction-window?relation=needs_my_action&page_size=25
Authorization: Bearer fixture:hr
```

Другие акторы примера: `fixture:department`, `fixture:candidate`, `fixture:candidate2`. Кандидат никогда не вызывает legacy. Фокус требует одновременно `subject_source=hiring.portal`, `subject_kind=candidate_request`, `subject_id=<R1 UUID>`; для legacy — `legacy`, `application`, `<A1 UUID>`.

`portal_cursor` и `legacy_cursor` продолжают отдельные секции. Подписанные курсоры связаны с актором, областью, фильтрами и порядком; legacy также с версией mapping. Фильтрация и LIMIT выполняются в SQL. После команды/изменения прав начинать с первой страницы. `coverage=page` не означает полный пустой список; общего total и snapshot нет.

Успешная часть при отказе другой даёт 200 + `partial`; отсутствие всех применимых источников — 503; неверная сессия — 401. Нет mapping — `not_linked`, неприменимый источник — `not_applicable`. В списке нет свободных сообщений, контактов, резюме и приватного основания HR. Ответы имеют `Cache-Control: no-store`; UI удаляет прежнее содержание после отказа, выхода или смены роли.

Команды портала остаются на прежних маршрутах. Новые Q требуют в addendum:

```json
{"expected_revision":4,"information_request_ref":{"request_id":"<R1 UUID>","event_sequence":2},"text":"Дополнение","document_ids":[]}
```

Сохранять Q-ref формы; после загрузки перечитать revision. Не заменять Q-ref автоматически при 409. Старые Q без sequence принимают прежнюю форму; окно маркирует `basis_unknown`. Demo-клиенты и существующая кандидатская форма мигрированы на новое поле.

Legacy-команды доступны через фиксированный allowlist:

```http
POST /hiring/api/v1/interaction-window/legacy/applications/<A1>/feedback-reviews
Authorization: Bearer fixture:hr
Content-Type: application/json

{"feedbacks":[{"attempt_id":"<H1>","feedback_id":"<F1>","revision":1}],"expected_seq":7,"request_id":"<UUID>","basis":"Ответ учтён, ждём H2","result":"continue_waiting"}
```

Для `stage_changed` добавить `stage` по StageMoveIn с той же expected_seq. Review и StageEvent сохраняются одной транзакцией. Повтор request_id/body возвращает результат; иное тело — 409. После исправления отзыва требуется актуальная feedback revision.

```http
POST /hiring/api/v1/interaction-window/legacy/handoffs/<H1>/revoke-access
Authorization: Bearer fixture:hr
Content-Type: application/json

{"expected_assignment_revision":1,"request_id":"<UUID>","reason":"Назначение отозвано"}
```

Также разрешены GET конкретных application, handoff, candidate-text, истории, сводки, передач и feedback, справочники stages/rejection-reasons; POST stage, handoffs, feedback и deadline. Произвольный URL/query не принимаются. `actions.target={source,kind,id}` — подсказка для формы, не полномочие. После таймаута POST исход неизвестен: перечитать и при необходимости повторить с **тем же** request_id.

## Лимиты и проверка

Hiring: `INTERACTION_CONNECT_SECONDS=1`, `INTERACTION_READ_SECONDS=2`, `INTERACTION_OVERALL_SECONDS=3`, `INTERACTION_MAX_BYTES=262144`; page_size=25, максимум 100 на источник. Это стартовый учебный бюджет с запасом относительно локального чтения (~40 мс/7.8 КБ на малом наборе), не сетевая SLA. Источники читаются параллельно; локальных SQL-чтений одновременно максимум четыре. Для PostgreSQL ограничены подключение/ожидание пула и statement timeout; HTTP читается потоком с лимитом байтов. Нет кеша частных данных и автоматического retry POST.

Из корня продукта в окружении с зависимостями legacy и Hiring (включая `python-multipart`):

```powershell
$env:PYTHONPATH="$PWD;$PWD/services/hiring"
python -m pytest --import-mode=importlib --noconftest -p no:cacheprovider -q -s tests/test_interaction_http.py tests/test_interaction_legacy.py services/hiring/tests/test_interaction_portal.py services/hiring/tests/test_interaction_window.py
```

Используются настоящие FastAPI-маршруты и SQLAlchemy с изолированной SQLite. PostgreSQL-типы JSONB/UUID и Identity адаптированы для SQLite; частичный сетевой отказ проверяется отдельно через MockTransport. Существующие БД не очищаются. Проверка PostgreSQL-блокировок/исполнения миграции, контейнеров и большого корпуса не заявляется. Отключение окна сохраняет review, ответы и историю; downgrade для обычного выключения не нужен.
