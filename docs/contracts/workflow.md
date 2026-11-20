# Контракт: передача отклика получателю, ожидания, сроки и ответы департамента (`workflow-01`)

**Версия:** 0.2 · **Дата:** 2026-11-20 · **Владелец:** Денис · **Потребители:** фронтенд (Ася), процесс HR (Маша), воронка (`backend-02`).

Опирается на [api.md](api.md) v0.5, [database.md](database.md) v2.0, раздел 21 (миграция `0008`) и [interview.md](interview.md) (очистка заметок при сборке сводки).

## 1. Правила процесса и доступов

- **Разделение сводки, передачи, ответа и решения HR `[исслед. Frappe HR]`:**
  1. `GET /api/v1/applications/{id}/handoff-summary` ничего не пишет в БД (0 ожиданий). Заметки кадровика и интервью с признаками контактов или ПДн кандидата исключаются целиком (`omitted_notes_count`).
  2. Первая передача выполняется **одной транзакцией** вместе с переводом этапа в `sent_to_department` через `POST /api/v1/applications/{id}/stage` (обязателен блок `handoff`). Передача при устаревшей оценке (`stale`) **строго запрещена** (`409 ASSESSMENT_STALE`). Повторная передача другому адресату, когда отклик уже на `sent_to_department` или `department_interview`, выполняется через `POST /api/v1/applications/{id}/handoffs`.
  3. Получатель (`recipient_user_id` с ролью `department`, либо внешний адресат `recipient_name` + `recipient_department` для СЭД/телефона) прикрепляется к попытке передачи (`attempt_id`), а отправленная сводка сохраняется как неизменяемый снимок (`summary_snapshot`).
  4. **Срок ответа, производственный календарь РФ и перенос срока:**
     - При создании передачи сервер вычисляет и сохраняет в самой попытке `initial_due_date` / `due_date` (`HANDOFF_FEEDBACK_DEADLINE_BUSINESS_DAYS = 10` рабочих дней) и `reminder_date` (`HANDOFF_FEEDBACK_REMINDER_BUSINESS_DAY = 7` рабочих дней) по производственному календарю РФ (`production_calendar_days`). Изменение настроек не сдвигает уже сохранённые сроки.
     - На момент чтения вычисляются `deadline_status` (`on_track` | `due_soon` с рабочего дня 7 | `overdue` после срока | `responded` | `closed_without_response`), остаток рабочих дней (`business_days_left`), `overdue_notice = "Департамент не ответил"` и `cross_assessments_url` (`/api/v1/candidates/{id}/cross-assessments` для HR/admin при просрочке).
     - Очередь `GET /api/v1/handoffs` показывает просроченные передачи первыми. Просрочка **не меняет этап отклика и резерв**.
     - Для открытой передачи кадровик может перенести срок вперёд (`POST /api/v1/applications/{id}/handoffs/{attempt_id}/deadline`) с обязательной причиной (`illness`, `vacation`, `business_trip`, `other` + комментарий) и защитой от гонки (`expected_due_date` → `409 DEADLINE_CONFLICT`). Исходный `initial_due_date` сохраняется, `reminder_date` пересчитывается на `deadline - reminder` (= 3) рабочих дня назад от нового срока; перенос просроченной передачи возвращает её в `on_track` / `due_soon`, а в истории (`deadline_extensions`) фиксируется `was_overdue = true`. Время ответа `response_business_days` считается от дня передачи, а не от последнего переноса; `answered_late` и `received_after_due` считаются относительно текущего `due_date`.
  5. Ответ департамента (`POST /api/v1/applications/{id}/feedback`) закрывает ожидание **только своей попытки** (при `outcome = fit | not_fit`), но **не меняет этап отклика и не создаёт запись в базе резюме (резерве)**. Запоздалый ответ после срока (или после закрытия отклика) сохраняется у своей попытки.
- **Сквозной доступ роли `department`:**
  - Доступен только к откликам, на которые этому пользователю оформлена попытка передачи (`recipient_user_id == user.id`): `GET /handoffs`, `GET /handoffs/{attempt_id}`, `GET /applications/{id}/handoffs`, `GET /applications/{id}/handoff-summary` (читает снимок), `GET/POST /applications/{id}/feedback`, `GET /applications/{id}` и `GET /candidate-texts/{id}` (только для `candidate_text_id`, вошедших в переданный ему снимок).
  - Чужой ID или чужой текст → `403 FORBIDDEN_SCOPE`. Общие списки (`/vacancies*`, `/comparison`, `/history`, `/analytics/funnel`, `/stage`, `POST /handoffs`, `POST .../deadline`, `/reserve`) → `403 FORBIDDEN_ROLE`.

## 2. Маршруты

| Метод и путь | Роли | Назначение и коды успеха |
|---|---|---|
| `GET /api/v1/applications/{id}/handoff-summary` | `hr`, `admin`, назначенный `department` | `200`: JSON + Markdown + `summary_revision` (SHA-256). Для `department` отдаётся замороженный снимок (`from_snapshot = true`). |
| `POST /api/v1/applications/{id}/stage` (`sent_to_department`) | `hr`, `admin` | `201` (повтор с тем же `handoff.request_id` → `200`): транзакционно меняет этап, создаёт `handoff_attempt` со сроком 10/7 раб. дней и снимок. |
| `POST /api/v1/applications/{id}/handoffs` | `hr`, `admin` | `201` (повтор → `200`): дополнительная передача другому получателю на этапе `sent_to_department` / `department_interview`. |
| `GET /api/v1/applications/{id}/handoffs` | `hr`, `admin`, назначенный `department` | `200`: попытки передачи отклика (для `department` — только свои). |
| `GET /api/v1/handoffs` | `hr`, `admin`, `department` | `200`: очередь передач (просроченные первыми); фильтры `contour`, `status`, `deadline_status`, `department`, `recipient_user_id`, `actor_login`, `vacancy_id`, `position_id`. |
| `GET /api/v1/handoffs/{attempt_id}` | `hr`, `admin`, назначенный `department` | `200`: карточка попытки, замороженный снимок (`summary`, `markdown`), `deadline_extensions` и `feedback_history`. |
| `POST /api/v1/applications/{id}/handoffs/{attempt_id}/deadline` | `hr`, `admin` | `201` (повтор с тем же `request_id` → `200`): перенос срока открытой передачи с причиной (`expected_due_date` против гонки). |
| `POST /api/v1/applications/{id}/feedback` | `hr`, `admin`, назначенный `department` | `201` (повтор с тем же `request_id` → `200`): запись ответа или правка через `supersedes_id`. |
| `GET /api/v1/applications/{id}/feedback` | `hr`, `admin`, назначенный `department` | `200`: все версии отзывов по отклику (`origin_unrecorded = true` для прежних строк без `attempt_id`). |

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
    "request_id": "22222222-2222-4222-8222-222222222222"
  }
}
```
Для внешнего адресата без учётки передаются `recipient_name` и `recipient_department` вместо `recipient_user_id`.

**Тело `POST /api/v1/applications/{id}/handoffs/{attempt_id}/deadline`:**
```json
{
  "expected_due_date": "2026-12-15",
  "new_due_date": "2026-12-22",
  "reason_code": "illness",
  "comment": "Руководитель на больничном",
  "request_id": "66666666-6666-4666-8666-666666666666"
}
```

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
| 409 | `ASSESSMENT_STALE` | оценка устарела; передача запрещена до пересчёта оценки |
| 409 | `SUMMARY_CHANGED` | после предпросмотра изменилась сводка (`details.expected_revision`, `details.current_revision`) |
| 409 | `REQUEST_ID_REUSED` | `request_id` повторно использован с другими данными |
| 409 | `FEEDBACK_CONFLICT` | выбранная версия отзыва уже исправлена или попытка требует `supersedes_id` |
| 409 | `DEADLINE_CONFLICT` | срок передачи уже изменён параллельным запросом (`details.current_due_date`, `details.extensions_count`) |
| 409 | `HANDOFF_NOT_OPEN` | попытка перенести срок у уже закрытой передачи |
| 409 | `HANDOFF_STAGE_REQUIRED` | дополнительная передача вызвана не на этапе `sent_to_department` / `department_interview` |
| 422 | `HANDOFF_REQUIRED`, `HANDOFF_NOT_ALLOWED`, `HANDOFF_RECIPIENT_REQUIRED`, `RECIPIENT_INVALID`, `FEEDBACK_SOURCE_REQUIRED`, `ATTEMPT_OF_OTHER_APPLICATION`, `FEEDBACK_OF_OTHER_ATTEMPT`, `EXTENSION_COMMENT_REQUIRED`, `INVALID_DEADLINE_DATE` | ошибка входа или привязки |

## 5. Что остаётся на предметное согласование с HR/командой

- Наличие чисто «внутренних» заметок HR без ПДн, которые нельзя показывать департаменту, и полнота причин отказа.
- Нужен ли самостоятельный перенос срока руководителем департамента и ограничение числа/длины переносов (сейчас переносит только `hr`/`admin` без лимита).
- Согласование с Родионом порога `open_over_15` в годовой сводке `reporting` и статуса `closed_without_response` при возврате этапа.
- Следующий слой (вне объёма задачи): уведомления и эскалация заместителю в СЭД/почту, кнопки ответа в письме, отчёт по срокам ответа департаментов.
