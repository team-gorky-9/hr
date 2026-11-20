# Контракт: передача отклика получателю, ожидания и ответы департамента (`workflow-01`)

**Версия:** 0.1 · **Дата:** 2026-11-20 · **Владелец:** Денис · **Потребители:** фронтенд (Ася), процесс HR (Маша), воронка (`backend-02`).

Опирается на [api.md](api.md) v0.5, [database.md](database.md) раздел 20 (миграция `0007`) и [interview.md](interview.md) (очистка заметок при сборке сводки).

## 1. Правила процесса и доступов

- **Разделение сводки, передачи, ответа и решения HR `[исслед. Frappe HR]`:**
  1. `GET /api/v1/applications/{id}/handoff-summary` ничего не пишет в БД (0 ожиданий). Заметки кадровика и интервью с признаками контактов или ПДн кандидата исключаются целиком (`omitted_notes_count`).
  2. Первая передача выполняется **одной транзакцией** вместе с переводом этапа в `sent_to_department` через `POST /api/v1/applications/{id}/stage` (обязателен блок `handoff`). Повторная передача другому адресату, когда отклик уже на `sent_to_department` или `department_interview`, выполняется через `POST /api/v1/applications/{id}/handoffs`.
  3. Получатель (`recipient_user_id` с ролью `department`, либо внешний адресат `recipient_name` + `recipient_department` для СЭД/телефона) прикрепляется к попытке передачи (`attempt_id`), а отправленная сводка сохраняется как неизменяемый снимок (`summary_snapshot`).
  4. Ответ департамента (`POST /api/v1/applications/{id}/feedback`) закрывает ожидание **только своей попытки** (при `outcome = fit | not_fit`), но **не меняет этап отклика и не создаёт запись в базе резюме (резерве)**.
- **Сквозной доступ роли `department`:**
  - Доступен только к откликам, на которые этому пользователю оформлена попытка передачи (`recipient_user_id == user.id`): `GET /handoffs`, `GET /handoffs/{attempt_id}`, `GET /applications/{id}/handoffs`, `GET /applications/{id}/handoff-summary` (читает снимок), `GET/POST /applications/{id}/feedback`, `GET /applications/{id}` и `GET /candidate-texts/{id}` (только для `candidate_text_id`, вошедших в переданный ему снимок).
  - Чужой ID или чужой текст → `403 FORBIDDEN_SCOPE`. Общие списки (`/vacancies*`, `/comparison`, `/history`, `/analytics/funnel`, `/stage`, `POST /handoffs`, `/reserve`) → `403 FORBIDDEN_ROLE`.

## 2. Маршруты

| Метод и путь | Роли | Назначение и коды успеха |
|---|---|---|
| `GET /api/v1/applications/{id}/handoff-summary` | `hr`, `admin`, назначенный `department` | `200`: JSON + Markdown + `summary_revision` (SHA-256). Для `department` отдаётся замороженный снимок (`from_snapshot = true`). |
| `POST /api/v1/applications/{id}/stage` (`sent_to_department`) | `hr`, `admin` | `201` (повтор с тем же `handoff.request_id` → `200`): транзакционно меняет этап, создаёт `handoff_attempt` и снимок. |
| `POST /api/v1/applications/{id}/handoffs` | `hr`, `admin` | `201` (повтор → `200`): дополнительная передача другому получателю на этапе `sent_to_department` / `department_interview`. |
| `GET /api/v1/applications/{id}/handoffs` | `hr`, `admin`, назначенный `department` | `200`: попытки передачи отклика (для `department` — только свои). |
| `GET /api/v1/handoffs` | `hr`, `admin`, `department` | `200`: очередь передач; фильтры `contour`, `status`, `department`, `recipient_user_id`, `actor_login`, `vacancy_id`, `position_id`. |
| `GET /api/v1/handoffs/{attempt_id}` | `hr`, `admin`, назначенный `department` | `200`: карточка попытки, замороженный снимок (`summary`, `markdown`) и история отзывов (`feedback_history`). |
| `POST /api/v1/applications/{id}/feedback` | `hr`, `admin`, назначенный `department` | `201` (повтор с тем же `request_id` → `200`): запись ответа или правка через `supersedes_id`. |
| `GET /api/v1/applications/{id}/feedback` | `hr`, `admin`, назначенный `department` | `200`: все версии отзывов по отклику (прежние строки без `attempt_id` помечены `origin_unrecorded = true`). |

## 3. Ключевые примеры JSON

**Тело `handoff` в `POST /api/v1/applications/{id}/stage` (`sent_to_department`):**
```json
{
  "to_stage_code": "sent_to_department",
  "expected_seq": 3,
  "comment": "Передано руководителю отдела разработки",
  "handoff": {
    "recipient_user_id": "11111111-1111-4111-8111-111111111111",
    "channel": "cabinet",
    "summary_revision": "8f2c...",
    "request_id": "22222222-2222-4222-8222-222222222222",
    "allow_stale": false
  }
}
```
Для внешнего адресата без учётки передаются `recipient_name` и `recipient_department` вместо `recipient_user_id`.

**Тело `POST /api/v1/applications/{id}/feedback` (правка кадровиком ответа из СЭД):**
```json
{
  "attempt_id": "33333333-3333-4333-8333-333333333333",
  "supersedes_id": "44444444-4444-4444-8444-444444444444",
  "outcome": "not_fit",
  "contact_status": "yes",
  "interview_status": "yes",
  "rejection_reason_code": "experience",
  "keep_in_reserve": true,
  "comment": "Сильные тесты, не хватило коммерческого стажа",
  "response_channel": "sed",
  "reported_by_name": "А.С. Руководитель",
  "request_id": "55555555-5555-4555-8555-555555555555"
}
```
Для роли `department` поля `response_channel` (`cabinet`) и `reported_by` подставляются сервером из сессии.

## 4. Ошибки

| HTTP | `error.code` | Когда |
|---|---|---|
| 403 | `FORBIDDEN_ROLE` | роль не допускает маршрут |
| 403 | `FORBIDDEN_SCOPE` | попытка `department` открыть чужую передачу, сводку, текст или отзыв |
| 404 | `APPLICATION_NOT_FOUND`, `HANDOFF_NOT_FOUND`, `RECIPIENT_NOT_FOUND`, `FEEDBACK_NOT_FOUND`, `USER_NOT_FOUND` | сущность не найдена |
| 409 | `NOT_WORKING_APPLICATION` | отклик `history` или `manual` |
| 409 | `ASSESSMENT_STALE` | оценка устарела, а `allow_stale` не передан |
| 409 | `SUMMARY_CHANGED` | после предпросмотра изменилась сводка (`details.expected_revision`, `details.current_revision`) |
| 409 | `REQUEST_ID_REUSED` | `request_id` повторно использован с другими данными |
| 409 | `FEEDBACK_CONFLICT` | выбранная версия отзыва уже исправлена или попытка требует `supersedes_id` (`details.current_feedback_id`, `details.current_revision`) |
| 409 | `HANDOFF_STAGE_REQUIRED` | дополнительная передача вызвана не на этапе `sent_to_department` / `department_interview` |
| 422 | `HANDOFF_REQUIRED`, `HANDOFF_NOT_ALLOWED`, `HANDOFF_RECIPIENT_REQUIRED`, `RECIPIENT_INVALID`, `FEEDBACK_SOURCE_REQUIRED`, `ATTEMPT_OF_OTHER_APPLICATION`, `FEEDBACK_OF_OTHER_ATTEMPT` | ошибка входа или привязки |

## 5. Что остаётся на предметное согласование с HR/командой

- Подтверждение рабочего канала (СЭД/почта/кабинет) и права руководителей департаментов на самостоятельный вход.
- Разрешение передавать сводку при устаревшей оценке (`allow_stale`).
- Закрытие открытых ожиданий при возврате отклика с этапа `sent_to_department` назад на доработку (сейчас переводится в `closed_without_response`, при этом запоздалый ответ по `attempt_id` принимается).
