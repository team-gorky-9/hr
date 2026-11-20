# Wave 1 · Hiring · итог этапа 1

**21 ноября 2026 · Илья.** Ветка `feature/wave-1-hiring` от `main` `2ab2584` (включает hr#36 и hr#37). Карточка — `hq/tasks/stage-1/wave-1-ilya-hiring.md` в штабе (этап 1). Объём сдачи определён [wave-1-stage-1](../contracts/wave-1-stage-1.md): операции дела, комплект, документы, старт, ручное кадровое подтверждение. Брокер и автоматический обмен относятся к этапу 2.

## Что включено

| Операция | Статус |
|---|---|
| `POST/GET /cases`, `GET /cases/{id}`, `GET /cases/{id}/history` | реализовано, пагинация `limit` + `cursor` |
| `request-documents`, `items/{id}/submit`, `items/{id}/review`, `ready` | реализовано |
| `start`, `withdraw`, `link-account`, `correct-start` | реализовано |
| `record-assignment`, `registration-data` (stage 1) | реализовано |
| `POST /documents`, `GET /documents/{id}`, `GET /documents/{id}/content` | реализовано, PDF/JPEG/PNG, лимит `FILE_MAX_BYTES` |
| `/health` (`implementation_stage=1`, `integration_mode=standalone`, `auth_mode`, `transfer_mode=manual`), `/ready` | реализовано |
| `AUTH_MODE=fixture` / `workforce` | fixture проверен целиком; workforce — тестом с подменой ответа `GET /session` |
| Idempotency-Key | реализован replay и конфликт для всех POST, включая загрузку файла; заголовок необязателен по stage 1 |
| employment.ready, assignment.registered/review-resolved, outbox/inbox, `/deliveries`, тестовый получатель RabbitMQ | **не реализовано — этап 2** |

## Что подключать к интерфейсу

OpenAPI — `GET /openapi.json`, Swagger — `/docs` на порту 8103. Это 17 операций `/api/v1` и `/health`, `/ready`, список сверен с запущенным сервисом. Вход для макета — `Authorization: Bearer fixture:<login>`: `hr`, `admin`, `candidate`, `hr_other` (чужая организация). Экраны HR: список дел, карточка с комплектом и историей, действия по пункту, готовность, старт, реквизиты для регистрации, запись назначения, исправление даты. Экран кандидата: своё дело, загрузка файла, замечание по пункту. До записи назначения в карточке видно ожидание: `workforce_status=not_sent`, `transfer_mode=manual`.

## Входы и полученные ID

| Вход | Значение |
|---|---|
| Решение Марины | `fixtures/wave-1/selection.json`, application `…0801`, candidate `…0901`, организация `…0001`, подразделение `…0011`, `economist-training` |
| Второй кандидат | `services/hiring/fixtures/extra-selections.json`, application `…0802`, «Пётр Учебный» |
| Кадровые ID в `record-assignment` | employee `…0201`, assignment `…0302` из `events.json` |
| Даты | старт 2026-11-23, основание DEMO-21 от 2026-11-21; исправление на 2026-11-24, HR сохранил 2026-11-23 (как `kept_existing` в `corrections.json`) |

ID дела и документов генерирует сервер (UUID4); в прогоне demo дело Марины — `f9648ff6-0ca0-4d15-a30e-505bc83e7422`, ревизия 10 на момент старта.

## Граница проверки

Проверка **автономная**: учебные акторы `fixtures/wave-1/actors.json`, источник решения `fixture` (selection.json + второй учебный кандидат в `services/hiring/fixtures/extra-selections.json`). Соединения с настоящим Workforce и реальным legacy-входом не было. Ручное подтверждение назначения — запись HR (`method=manual-confirmed`), автоматическая проверка в Workforce не заявляется.

## Результаты

Окружение: Linux, Python 3.13.17, PostgreSQL 16.15 (локальный кластер; в compose указан 17.6), FastAPI 0.165.0, SQLAlchemy 2.0.58, Alembic 1.20.1, Pydantic 2.14.4, psycopg 3.3.9.

`uv run pytest -q` → **40 passed, 0 skipped, 0 failed**. Прогон повторён 4 раза подряд с тем же итогом, включая два теста с параллельными потоками. Схема в тестах создаётся собственными миграциями сервиса.

| Проверка карточки / stage 1 | Тест или прогон | Наблюдаемый исход |
|---|---|---|
| Нормальный путь Марины | `test_full_training_path`, `python -m hiring.demo` | дело → комплект → возврат → исправление → ready → started/not_sent → registered |
| Кандидат видит только своё дело | `test_full_training_path`, `test_unlinked_candidate_sees_no_case_and_no_files`, `test_candidate_view_hides_internal_fields` | список содержит одно связанное дело; без связи — 404; нет `selection`, ID акторов, основания |
| Ready до принятия всех required | `test_full_training_path` | 409 `INVALID_STATE`, `field=checklist` |
| Новая версия не стирает оригинал | `test_new_file_revokes_accepted_version_and_readiness` | обе версии в `document_ids`, `accepted` снят, дело вернулось в `awaiting_documents` |
| Чужая организация | `test_other_organization_sees_nothing`, `test_selection_of_another_organization_is_forbidden` | дело, история, метаданные и содержимое файла — 404; чужой снимок — 403 |
| Права ролей | `test_other_roles_have_no_hiring_access`, `test_candidate_cannot_*` | department/employee — 403; кандидат не проверяет, не стартует, не записывает назначение |
| Прямой ID закрытого файла | `test_linked_candidate_reads_case_files_but_not_the_internal_basis` | кандидат получает 404 на `employment_basis` |
| Неверные и пустые входы | `test_unknown_and_missing_fields_are_rejected`, `test_return_requires_a_reason`, `test_file_checks` | 422 `VALIDATION_ERROR` с полем; пустой и не-PDF файл — 422; больше лимита — 413 |
| Устаревшая форма, две вкладки | `test_two_tabs_cannot_confirm_a_stale_checklist`, `test_parallel_ready_and_new_file_do_not_pass_an_old_checklist` | 409 `STALE_REVISION`; принятое не перезаписано; `ready` с непроверенным файлом не возникает |
| Повтор ключа | `test_idempotency_key_replays_and_conflicts`, `test_create_replay_keeps_201`, `test_upload_replay_returns_the_same_document` | тот же ответ + `Idempotency-Replayed: true`, одно событие; иная команда — 409 `IDEMPOTENCY_CONFLICT`; лишний файл не остаётся |
| Двойная команда без ключа | `test_double_command_without_key_is_stale` | вторая — 409 `STALE_REVISION` |
| Повтор application_ref | `test_same_application_returns_the_existing_case`, `test_parallel_creation_makes_one_case` | 200 с прежним делом; 6 параллельных запросов → одно дело, один 201 |
| Отзыв второго кандидата | `test_withdrawn_second_candidate_never_starts`, `test_candidate_withdraws_own_case_but_not_after_start` | `withdrawn`, `workforce_status=not_sent`, старт запрещён; started не отзывается |
| Ручная регистрация, расхождение | `test_correction_after_confirmation_needs_review`, `test_record_assignment_with_external_ids` | `review_required` → `registered/corrected` либо `registered_with_difference/kept_existing` с объяснением; external ID не попадают в `employee_id` |
| Перезапуск | `test_restart_keeps_data_and_files`; ручной перезапуск uvicorn на базе `hiring_demo` | дело, история, ревизия и байты файла читаются после перезапуска |
| Запуск без брокера и соседа | все тесты и demo | брокера в процессе нет; `/ready` → `broker=not_used` |

### Пример входа и выхода (demo, сокращено)

```
• HR создал дело Марины — status=preparing items=2
• HR принял паспорт и вернул документ об образовании — passport=accepted, education=needs_revision
• ready до принятия всех пунктов отклонён — Required items are not accepted: education
• исправление принято, обе версии сохранены — education.document_ids=[…f399f9, …6ec033]
• выход зафиксирован без ожидания Workforce — status=started workforce_status=not_sent transfer_mode=manual
• кандидат не открывает внутреннее основание по прямому ID
• кадровое подтверждение записано — workforce_status=registered employee_id=…0201 assignment_id=…0302
• исправление даты выхода — starts_on=2026-11-24 workforce_status=review_required
• HR сохранил прежнее назначение — workforce_status=registered_with_difference resolution=kept_existing
• второй кандидат отозван до выхода — status=withdrawn workforce_status=not_sent
```

## Ограничения

- `docker compose -f services/hiring/compose.yml up --build` **не запускался**: в среде разработки нет доступа к Docker Hub. Проверен только синтаксис (`docker compose config`). Сервис, миграции, тесты и demo проверены на локальном PostgreSQL 16.
- Режим `AUTH_MODE=workforce` проверен подменой ответа `GET /session`, без настоящего Workforce.
- `SELECTION_SOURCE=legacy-api` не реализован: в этапе 1 нет доступного API исходного подбора. Сервер не запускается с этим значением.
- `workforce_assignment_snapshot.revision` при ручной записи — `null`: ревизию назначения Workforce в ручном пути никто не передаёт.
- Требование «обе ссылки из одной системы» в `record-assignment` — проверка сервиса, в контракте оно явно не записано.
- Учебный перечень документов (паспорт, образование) — пример механизма. Реальный состав подтверждает организация.

## Следующий получатель

- Интерфейс (кабинет HR и кандидата) — операции и ответы выше, OpenAPI на `/openapi.json`.
- Интегратор — переключение `AUTH_MODE=workforce` и `DATABASE_URL` на стенд, сквозной проход с сервисом Давида.
- Этап 2 — публикация `employment.ready`, приём `assignment.registered`/`assignment.review-resolved` по `corrections.json`, outbox/inbox, `/deliveries`.
