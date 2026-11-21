# Hiring · оформление выбранного кандидата (первая волна, этап 1)

Stage 2: [серверное единое окно взаимодействия](../../docs/modules/interaction-window.md) объединяет кабинет кандидата и legacy-передачи. Включается отдельным закрытым учебным профилем; по умолчанию выключено.

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

## Candidate-portal: собственное обращение кандидата (wave-5, 5A)

Контракт — [wave-5-candidate-portal-stage-1](../../docs/contracts/wave-5-candidate-portal-stage-1.md), раздел 5A. Маршруты `/api/v1/candidate-requests` в этом же сервисе. Миграция `0002`, применяется командой `python -m hiring serve`.

Учебные кандидаты: `fixture:candidate` из общего набора и `fixture:candidate2` из `fixtures/extra-actors.json`. HR — `fixture:hr`. Публичные вакансии — учебный снимок `fixtures/public-vacancies.json` (`source=training_snapshot`): живой каталог вакансий не подключён.

```bash
uv run python -m hiring serve &            # API на 127.0.0.1:8103
uv run python -m hiring.portal_demo        # два кандидата, чужой доступ, второе резюме, очередь HR
curl -s -X POST localhost:8103/api/v1/candidate-requests \
  -H 'Authorization: Bearer fixture:candidate2' -H 'Content-Type: application/json' \
  -d '{"message": "Ищу работу по специальности (учебно)", "contact": {"channel": "email", "value": "c2@example.test"}}'
```

Ответ `201` — черновик: `status=draft`, `target_question=no_target`, `contact.source=candidate_reported`. Подача — `POST /candidate-requests/{id}/submit {expected_revision}`, она присваивает номер `ОБР-000001`.

### 5B · уточнение и передача в подбор

```bash
uv run python -m hiring.portal_clarification_demo   # запрос сведений → дополнение → выбор вакансии → ready → регистрация рассмотрения
```

HR: `POST /candidate-requests/{id}/information-request`, `…/ready`, `…/record-consideration`. Кандидат: `…/addendum`, `…/choose-vacancy`. Все операции принимают `expected_revision`. Ссылки на записи подбора в демо учебные (`system=legacy-hr-training`), реального соединения нет.

После запроса уточнения ответ и `GET /candidate-requests/{id}` содержат `information_request_ref={request_id,event_sequence}`. Клиент сохраняет эту ссылку для формы ответа и отправляет её в `…/addendum` вместе с `expected_revision`. Загрузка документа обновляет только ожидаемую revision: Q-ref формы сохраняется. Если HR заменил вопрос, старое дополнение получает `409 STALE_REVISION` с `field=information_request_ref`; нельзя автоматически подставлять ссылку нового вопроса и повторять отправку. Только исторический запрос без сохранённого event_sequence принимает прежнее тело без Q-ref; окно помечает его `basis_unknown` и не предлагает действие ответа до открытия прежнего предметного экрана.

В окне `related_ref` — ссылка-основание, вручную подтверждённая HR (`record-consideration` / `source_reference`), а не автоматическое соединение R1 и A1. Поле `instance` сохраняет исходный `application_ref.system`; совпадение ID с записью другого экземпляра не подтверждает связь и не разрешает переход в него. Кандидат этой ссылки и внутреннего основания не видит. Ключ строки включает организацию и контур `training`.

### 5C · понятный исход и сообщения кабинета

```bash
uv run python -m hiring.portal_outcome_demo   # запрос → прочтение → итог со следующим шагом; «нет открытой вакансии»; отзыв
```

HR публикует исход: `POST /candidate-requests/{id}/public-outcome {expected_revision, outcome, public_explanation, next_action, source_reference}`. Кандидат работает с сообщениями — `GET …/messages`, `POST …/messages/{message_id}/read` — и может отозвать обращение: `POST …/withdraw {expected_revision, reason}`. Сообщения доставляются только внутри кабинета, без email, СЭД и брокера.

### Волна 6 · сквозной показ HR и кандидата

```bash
uv run python -m hiring.recruitment_demo --legacy-url http://127.0.0.1:8000 \
  --transcript ../../docs/reports/wave-6-recruitment-demo.transcript.json
```

Обращение → запрос уточнения → дополнение → поиск подготовленной записи в старом подборе (нужен `python -m app.search load-demo`) → ручная учебная регистрация рассмотрения → исход → чтение сообщения. Все запросы и ответы сохраняются в transcript. Подробности и ограничения — [отчёт](../../docs/reports/wave-6-recruitment-demo.md).


### Live public vacancy catalog

Set REQUIREMENTS_URL to the internal requirements origin (for example http://requirements:8000). Candidate portal vacancies then come from GET /api/v1/public/vacancies in the actor organization. The exact reference is {system: "requirements", id, revision}; title matching is never used. Before creating, editing, choosing, and submitting an application, hiring resolves the publication snapshot again. Closed vacancies remain identifiable and are accepted with target_question=vacancy_closed; missing/stale/cross-organization references yield vacancy_unknown. A catalog outage returns retryable 503 CATALOG_UNAVAILABLE and does not masquerade as an unknown vacancy. Existing fixture references remain resolvable for old applications. With no REQUIREMENTS_URL, the standalone training catalog behavior remains unchanged.

The portal frontend uses this catalog and authenticated candidate requests: create draft, upload resume, submit using the current request revision. Confirmation appears only after server submission. Retry restores the saved draft; an idempotency key persists across a lost create response. A page refresh retrieves the stored request from the server. This creates a candidate request, not an automatic legacy selection application.
