# Модуль hiring-service · оформление выбранного кандидата

Сервис `services/hiring/`, порт 8103, своя БД. Реализует этап 1 по [wave-1-stage-1](../contracts/wave-1-stage-1.md) в пределах операций [wave-1-hiring](../contracts/wave-1-hiring.md) и общих правил [wave-1-common](../contracts/wave-1-common.md). Запуск и тесты — [README сервиса](../../services/hiring/README.md).

## Задача человека

Кадровик получает положительное решение по отклику и доводит кандидата до выхода. Он запрашивает документы, возвращает ошибочные с объяснением, принимает исправления, фиксирует дату выхода и основание, а затем вручную регистрирует сотрудника в кадровом учёте. Кандидат видит только своё дело, свои пункты и замечания.

## Один полный пример

1. HR (`fixture:hr`) отправляет `POST /cases` со снимком решения Марины из `fixtures/wave-1/selection.json` и комплектом из двух пунктов. Сервер сверяет снимок с учебным источником (`SELECTION_SOURCE=fixture`). Он создаёт дело `preparing`, `revision=1` и пишет в историю `case.created`. Кандидат `fixture:candidate` связан с делом через `candidate_actor_id` с основанием проверки личности.
2. `request-documents` переводит дело в `awaiting_documents`. Кандидат загружает два PDF через `POST /documents`. Он привязывает их к пунктам через `items/{id}/submit` с ревизией пункта. Каждый файл — новый неизменяемый документ. Пункт получает `received`, ревизии пункта и дела растут.
3. HR принимает паспорт и возвращает диплом с причиной «скан нечитаем» (`needs_revision`). `ready` даёт 409 `INVALID_STATE`, поле `checklist`: «Required items are not accepted: education».
4. Кандидат видит причину, загружает новый файл и отправляет его в тот же пункт. В `document_ids` хранятся обе версии. HR принимает новую версию, затем `ready` проходит.
5. HR загружает приказ (`kind=employment_basis`) и вызывает `start` с датой и основанием. Дело становится `started`, `workforce_status=not_sent`. Ответ не ждёт Workforce.
6. `GET /registration-data` отдаёт реквизиты для ручной регистрации. После неё HR вызывает `record-assignment` с `employee_ref`/`assignment_ref` (`system=workforce`). Дело получает `workforce_status=registered`, `employee_id`, `assignment_id`, подтверждение (кто и когда записал) и снимок назначения.
7. `correct-start` на 24.11 сохраняет новую версию старта и переводит `workforce_status` в `review_required`. Прежнее подтверждение остаётся рядом для сверки. HR сверяет назначение и записывает фактические кадровые сведения. При дате 23.11 итог — `registered_with_difference`, `workforce_resolution=kept_existing` и объяснение. При совпадении даты — `registered`, `corrected`.

## Устройство

| Файл | Роль |
|---|---|
| `hiring/api.py` | FastAPI: аутентификация, одна транзакция на команду, Idempotency-Key, конверт ошибок, `/health`, `/ready` |
| `hiring/domain.py` | операции дела, правила переходов, видимость полей, история |
| `hiring/auth.py` | `AUTH_MODE=fixture` (actors.json) и `AUTH_MODE=workforce` (`GET /session` Workforce, при недоступности — 503) |
| `hiring/storage.py` | файлы: временный файл → fsync → rename, проверка сигнатуры PDF/JPEG/PNG, лимит размера |
| `hiring/models.py`, `migrations/` | таблицы `cases`, `checklist_items`, `documents`, `case_events`, `idempotent_commands` |
| `hiring/demo.py` | учебный проход через HTTP |
| `tests/` | 40 тестов на PostgreSQL через собственные миграции |

## Решения и основания

- **Конкуренция.** Каждая команда блокирует строку дела (`SELECT … FOR UPDATE`) и проверяет `expected_revision`. Изменение пункта увеличивает и ревизию пункта, и ревизию дела. Поэтому форма `ready`/`start`, открытая до новой загрузки, получает `STALE_REVISION`. Новая загрузка в принятый пункт снимает `accepted` и возвращает дело из `ready` в `awaiting_documents`. Тест гоняет параллельные `ready` и загрузку и не допускает `ready` с непроверенным файлом.
- **Один активный case на application_ref.** Это частичный уникальный индекс `status <> 'withdrawn'`. Повтор возвращает существующее дело с кодом 200, параллельные запросы дают одно дело. Отозванное дело освобождает ссылку.
- **Idempotency-Key.** По stage-1 заголовок необязателен. Если он передан, команда повторяется по ключу: область — актор, организация, метод и путь; отпечаток — нормализованное тело, для файла — kind, имя и sha256. Сохранённый результат возвращается до проверки ревизии с `Idempotency-Replayed: true`. Другая команда с тем же ключом получает 409 `IDEMPOTENCY_CONFLICT`. Без ключа повтор той же команды получает `STALE_REVISION`.
- **Источник решения.** `fixture` принимает только снимок, совпадающий с учебным файлом. Иначе — 409 `SELECTION_NOT_READY`. `manual-confirmed` принимает ввод уполномоченного HR. `legacy-api` в этапе 1 не включается: сервер не стартует с этим значением, чтобы не изображать проверку, которой нет. Режим и автор проверки видны в `provenance`.
- **Видимость.** Кандидат получает сокращённое дело без `selection`, `decision_basis`, ID акторов и основания выхода. В истории ему видны только помеченные события, в урезанной форме. Документ читает HR своей организации либо кандидат: собственный файл или файл своего дела, кроме `employment_basis`. Чужое и скрытое отвечает 404, так же как отсутствующее.
- **Ручное кадровое подтверждение.** Подтверждение помечено `method=manual-confirmed`. Это слово HR, а не автоматическая сверка с Workforce. `employee_id`/`assignment_id` заполняются только для `system=workforce`, для `external` остаются `null`. Обе ссылки должны быть из одной системы — проверка сервиса, в контракте отдельно не оговорена. `workforce_assignment_snapshot.revision = null`: у ручной записи нет ревизии Workforce.
- **Файлы.** Байты полностью записаны и переименованы до появления строки БД. Если запись в БД не прошла, файл удаляется. `original_name` — только подпись: путь отбрасывается, имя на диске — ID документа.

## Что не входит в этап 1

Публикация `employment.ready`, приём `assignment.registered`/`assignment.review-resolved`, outbox/inbox, `/deliveries`, повторы, dead-letter и тестовый получатель на RabbitMQ относятся к этапу 2 по решению от 21.11 (wave-1-stage-1). Поле `transfer_mode` и статус `pending` в схеме оставлены под этот переход. Значение `transfer_mode='broker'` разрешено ограничением БД заранее.

## Candidate-portal · собственное обращение кандидата (wave-5, 5A)

`/api/v1/candidate-requests` в этом же сервисе. Контракт — [wave-5-candidate-portal-stage-1](../contracts/wave-5-candidate-portal-stage-1.md). Код — `hiring/portal.py`. Таблицы `candidate_requests`, `candidate_request_events` и `documents.request_id` добавлены миграцией `0002`.

| Операция | Кто | Правило |
|---|---|---|
| `POST /candidate-requests {vacancy_ref?, message, contact}` | кандидат | черновик; автор — актор входа (поле автора в теле даёт 422) |
| `PATCH /candidate-requests/{id} {expected_revision, message?, contact?, vacancy_ref?, clear_vacancy?}` | автор | только черновик; устаревшая форма — `STALE_REVISION` |
| `POST /candidate-requests/{id}/documents` (multipart `file`, `kind=candidate_resume\|candidate_addendum`) | автор | черновик, `submitted` или `needs_information`; новый неизменяемый документ, прежние сохраняются |
| `POST /candidate-requests/{id}/submit {expected_revision}` | автор | `draft → submitted`; номер `ОБР-NNNNNN`, снимок подачи |
| `GET /candidate-requests`, `GET /candidate-requests/{id}`, `…/history` | автор — свои; HR — поданные своей организации | черновик виден только автору |
| `GET /candidate-requests/{id}/documents/{document_id}/content` | автор; HR после подачи | чужой — 404 |
| `GET /candidate-portal/vacancies` | любой вошедший | опубликованные из учебного снимка |

**Как устроено.**
- **Вакансия.** Цель задаётся точной ссылкой `{system, id, revision}` из учебного снимка. Если вакансия закрыта или не найдена, обращение принимается с `target_question` (`vacancy_closed` / `vacancy_unknown`). Подача без вакансии даёт `no_target`. Обращение откликом в подборе автоматически не становится. Цель перепроверяется в момент подачи.
- **Контакт.** Сохраняется как сообщение самого кандидата: `source=candidate_reported`, `verified=false`.
- **Снимок подачи.** `submitted_snapshot` фиксирует текст, контакт, цель и список файлов на момент подачи. Поздние файлы его не меняют.
- **Права.** Второй учебный кандидат (`candidate2`) задан в `fixtures/extra-actors.json` сервиса, общий набор не меняется. HR не создаёт обращение за кандидата (403). Department — 403. Другая организация — 404.


### 5B · уточнение и передача в подбор

Миграция `0003`: колонки `information_request`, `addenda`, `review`, `consideration`; статус `forwarded` невозможен без записанного рассмотрения (`CHECK`).

| Операция | Кто | Переход |
|---|---|---|
| `POST …/information-request {expected_revision, public_message, requested_items}` | HR | `submitted` / `ready` / `needs_information` → `needs_information`; из `ready` готовность снимается |
| `POST …/addendum {expected_revision, text, document_ids}` | автор | `needs_information` → `submitted`; файлы — только этого обращения; прежние материалы и снимок подачи сохраняются |
| `POST …/choose-vacancy {expected_revision, vacancy_ref}` | автор | в `submitted` / `needs_information` / `ready`; только опубликованная точная редакция, иначе `409 VACANCY_NOT_AVAILABLE`; в ответе `vacancy_conditions` — условия этой редакции |
| `POST …/ready {expected_revision, review_basis}` | HR | `submitted` → `ready` |
| `POST …/record-consideration {expected_revision, candidate_ref, application_ref, selected_vacancy_ref, identity_basis, source_reference}` | HR | `ready` → `forwarded`; `confirmation_method=manual-confirmed` |

**Идентичность.** Сервис не сопоставляет кабинет с записью подбора по имени или телефону. HR сам выбирает запись подбора (`candidate_ref`) и записывает основание выбора (`identity_basis`). Ссылки на записи и основание видит только HR. Кандидат получает только `{status: registered, recorded_at, selected_vacancy}`. Пока HR не записал регистрацию, например потому что подбор недоступен, обращение остаётся `ready`. Основание готовности (`review`) кандидату не показывается.

### 5C · понятный исход и сообщения кабинета

Миграция `0004`: таблица `candidate_request_messages`, колонки `outcomes` и `withdrawal`. Статус `withdrawn` невозможен без записи отзыва (`CHECK`).

| Операция | Кто | Правило |
|---|---|---|
| `POST …/public-outcome {expected_revision, outcome, public_explanation, next_action?, source_reference}` | HR | Из `ready` / `forwarded`. `continue` — только после регистрации рассмотрения, обязателен `next_action`, статус `forwarded`. `declined` / `no_open_opportunity` / `completed` → `closed`. Создаётся сообщение кабинета |
| `POST …/withdraw {expected_revision, reason}` | автор | Из любого незакрытого статуса → `withdrawn`. Для `forwarded`: `external_consideration_open=true` и пояснение, что рассмотрение в подборе завершает его владелец |
| `GET …/messages` | автор, HR | Сообщения о запросе сведений (создаёт `information-request`) и об исходе |
| `POST …/messages/{message_id}/read` | автор | Отметка прочтения. Повтор возвращает первую отметку. HR — 403, чужая учётка — 404 |

**Публичный текст.** В объяснение кандидату попадает только то, что HR явно написал в `public_explanation` / `next_action`. Основание готовности, отзыв департамента и оценка в него автоматически не копируются. `source_reference` и автор решения видны только HR. «Нет открытой вакансии» (`no_open_opportunity`) — отдельный исход с отдельным заголовком сообщения, его нельзя спутать с `declined`. Сохранение человека в кадровом архиве — отдельное действие с собственным основанием, исход его не выполняет.
