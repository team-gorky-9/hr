# Wave 5A · собственная подача кандидата · этап 1

**21 ноября 2026 · Илья.**
- Ветка `feature/wave-5a-candidate-request` от `hr` `main` `120a4b0` (база спецификации hr#55 `6d3f836`).
- Карточка — `hq/tasks/stage-1/wave-5a-ilya-candidate-request.md` в штабе.
- Контракт — [wave-5-candidate-portal-stage-1](../contracts/wave-5-candidate-portal-stage-1.md), раздел 5A. Описание — [hiring-service.md](../modules/hiring-service.md#candidate-portal--собственное-обращение-кандидата-wave-5-5a).

## Что сделано

- Область candidate-portal внутри сервиса Hiring (`services/hiring`, порт 8103). Код — `hiring/portal.py`, маршруты — `/api/v1/candidate-requests` и `/api/v1/candidate-portal/vacancies`.
- Миграция `0002`: таблицы `candidate_requests` и `candidate_request_events`, `documents.request_id`, новые виды документов `candidate_resume` и `candidate_addendum`, последовательность номеров. `alembic check` чистый, `downgrade 0001` и повторный `upgrade` проходят. Существующие операции дел оформления не менялись.
- `GET /documents/{id}/content` для документа обращения пускает только автора и HR после подачи. Черновик и его файлы HR не видны.
- Учебные входы:
  - второй кандидат — `services/hiring/fixtures/extra-actors.json` (`candidate2`, actor `…0107`);
  - вакансии — `services/hiring/fixtures/public-vacancies.json` (`training_snapshot`: одна опубликованная, одна закрытая).

## Проверка

**Через HTTP.**
- Окружение: база `hiring_demo` (PostgreSQL 16), `python -m hiring serve` (миграция 0001 → 0002), `AUTH_MODE=fixture`.
- Команда: `uv run python -m hiring.portal_demo`.

| Шаг | Результат |
|---|---|
| `GET /candidate-portal/vacancies` | `training_snapshot`, одна опубликованная: «Экономист отдела планирования (учебная)» |
| candidate: черновик по вакансии `…0c01` ред. 1 → резюме → submit | `ОБР-000001`, `submitted`, вакансия из снимка |
| candidate2: без вакансии → submit | `ОБР-000002`, `submitted`, `target_question=no_target` |
| Список candidate | только своё обращение |
| candidate2 открывает обращение и файл candidate | 404 / 404 |
| Дополнительное резюме candidate после подачи | документов 2, первый файл читается без изменений |
| Очередь HR `?status=submitted` | обе подачи; контакт `candidate_reported`, `verified=false` |
| HR создаёт обращение за кандидата | 403 `FORBIDDEN` |

**Тесты.** `uv run pytest` в `services/hiring` → **44 passed**: 40 прежних и 4 новых в `tests/test_portal.py`. Новые тесты проверяют:
- два кандидата и очереди, чужой доступ к обращению и файлу, другая организация;
- приватность черновика, второе резюме, неизменность снимка подачи;
- закрытая и неизвестная вакансия, выбор и отказ от вакансии в черновике;
- автор берётся из входа, а поле автора в теле даёт 422;
- роли HR и department, устаревшая форма, правка и повторная подача после подачи, неверный файл, вход без контакта.

## Для интерфейса

Кабинет кандидата:
1. `GET /candidate-portal/vacancies`;
2. `POST /candidate-requests`;
3. `POST /candidate-requests/{id}/documents`;
4. `POST /candidate-requests/{id}/submit`;
5. `GET /candidate-requests` — номер и статус.

Очередь HR — `GET /candidate-requests?status=submitted`. Схемы — `/openapi.json` сервиса на 8103.

## Ограничения

- Вход — учебные fixture-акторы. Регистрация по почте не входит в задачу.
- Вакансии — учебный снимок. Живой каталог `services/requirements` не подключён.
- Связь обращения с кандидатской записью legacy и регистрация рассмотрения — часть 5B (ручное подтверждение HR). Сообщения кабинета и публичный исход — часть 5C.
- Idempotency-Key для загрузки файла обращения в этой части не поддержан: повтор создаёт второй документ. Для JSON-команд работает общий механизм сервиса.
