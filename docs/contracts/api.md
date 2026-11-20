# Контракт: HTTP API (`app/api/`)

**Дополнение v0.6 (`interview-01`):** раздел 4 — гайд интервью, ревизии ответов, подтверждение требования по матрице оснований ([interview.md](interview.md) v0.4).

**Дополнение v0.5 (`requirements-03` + `workflow-01` поверх `backend-02` v0.4):**
- `requirements-03`: `posting_resolution` в списке/карточке, confirmed-цель вместо предположения по папке, RESPONSE-only списки, маршруты разрешения публикации и снимков T-13 (`GET /applications/{id}/posting-resolution`, `POST/GET /posting-snapshots`). [Точный контракт и совместимость legacy applicability](posting-position-register.md#http-и-совместимость). Реализация полного объёма поручена Давиду; подтверждения HR не подразумеваются.
- `workflow-01`: предпросмотр сводки, транзакционная передача в `POST /stage` (`sent_to_department`), повторная передача (`POST /handoffs`), очередь ожиданий со сроком и переносом срока (`GET /handoffs`, `POST .../deadline`), версионный отзыв (`POST/GET /feedback`), реальный блок `open_waits` в воронке и область доступа роли `department` ([workflow.md](workflow.md)).

**Версия:** 0.5 (`requirements-03` + `workflow-01` поверх `backend-02` v0.4) · **Дата:** 2026-11-20 · **Владелец:** Денис · **Потребители:** фронтенд (Ася), Илья (`interview-01`), Родион (`qa-01`/`qa-02`), `search-01` (правило действующего резерва). Дополнение `requirements-03` разрешено Давидом в составе интеграционного плана; согласование коллегами не приписывается.

Опирается на [database.md](database.md) v2.0 (разделы 19–21), [assessment.md](assessment.md) v0.3, [workflow.md](workflow.md) v0.2 и [posting-position-register.md](posting-position-register.md#http-и-совместимость).

## Дополнение v0.3: применимость и подробные счётчики

Список и карточка отклика возвращают posting_title, target_position_code и applicability (status/reason/версия и hash политики/входной snapshot). Для hr-consultant решение общего resolver имеет приоритет над сохранённой оценкой пары: mismatch → assessment_status=not_applicable, unresolved → mapping_required; основной assessment и его formal_result/overall_score скрыты. Это не новые CheckResult и не переход этапа отбора. Остальные должности имеют applicability=null (политика не задана), без автоматического confirmed.

GET списка принимает `applicability=confirmed|mismatch|unresolved|not_covered`. По умолчанию показывает все отклики. Ответ содержит imported_count и confirmed_count/mismatch_count/unresolved_count/not_covered_count по всем откликам вакансии выбранного контура до фильтров; total — число отфильтрованных строк. Это не число уникальных людей.

`GET /api/v1/applications/{application_id}/comparison?profile_id=<uuid>` читает явное сравнение, не вызывает модель и не создаёт отклик. Ответ: purpose=comparison, ID исходного отклика/кандидата, posting_title, целевой position_code/profile_id, applicability, assessment_status и assessment. Для реального кандидата допустим только реальный approved, для учебного — любой неархивный профиль. Контекст основного отклика остаётся прежним.

AssessmentOut дополнен algorithm_version, calculation_as_of и competency_summary. Несовпадение algorithm_version или prompt_version с текущим оценщиком (включая отсутствие версии в старой записи) даёт stale/algorithm_changed. Это существующая причина изменения обработки, новое значение enum не вводится. У competency_scores появляется details с отдельными цитатами каждого индикатора, группами same_as и счётчиками. Вложенные цитаты имеют UTF-16 offsets. competency_summary суммирует обязательные/желательные единицы и отдельные счётчики интервью, исключений и ручной сверки; при неполных/legacy details он null.

Новые значения assessment_status/stale_reason требуют обработки в клиенте с исчерпывающим switch. Изменение фронтенда в этой ветке не выполнялось. Фактические DTO — `app/api/schemas.py`; применимость — [profile-applicability.md](profile-applicability.md).

**Изменения v0.2:** учебный и рабочий контуры (п. 1.1), признаки `is_training`, `is_preliminary`, `formal_preliminary`, основание `basis` и альтернативы в блоке формальных требований.

**Изменения v0.4 (backend-02):**
- раздел 3: справочники, история и перевод этапа с `expected_seq` (две вкладки → `409 STALE_STAGE_FORM`) и обязательной причиной для `rejected`/`withdrawn`; кросс-оценки с привязкой отклика к каждой вакансии; кадровый резерв с обоснованием, основанием повторного контакта, сроком, отзывом и периодами (БД v1.8); воронка за период с моментом среза;
- учебная авторизация стенда — заголовок `X-User-Login` (п. 1.2), коды `401`/`403`;
- действия и счётчики — только для откликов `source = response` (п. 1.3);
- в контракт внесены поля, которые были описаны только в `docs/modules/api.md`: `stale_reason`, `formal_checks[].key`, `candidate.is_training`, `candidate-texts.is_training`, `vacancy = null`;
- **не входит:** гайд интервью (`interview-01`), поиск (`search-01` — вынесен в [search.md](search.md)). Раскрытия ПДн в MVP нет (hr#14).
- **Дополнение v0.5 (`workflow-01`):** см. [workflow.md](workflow.md) — предпросмотр сводки (`GET /handoff-summary`), транзакционная передача в `POST /stage` (`sent_to_department`), повторная передача (`POST /handoffs`), очередь ожиданий (`GET /handoffs`), версионный отзыв (`POST/GET /feedback`), реальный блок `open_waits` в воронке (с фильтром `department`) и ограниченный доступ роли `department` к назначенным ей откликам, снимкам и текстам цитат.
- **Терминология рабочего резерва (интервью HR 20.11):** сущность `reserve_entries` и маршруты `/reserve` в пользовательском интерфейсе и демо называются **«База резюме»** / **«Пул кандидатов»** (а не «кадровый резерв», который в администрации означает формальный конкурс).

## 1. Общие соглашения

- **Базовый префикс:** `/api/v1`.
- **Формат:** JSON UTF-8; даты — `YYYY-MM-DD`, моменты времени — ISO 8601 со смещением, например `2026-11-19T15:03:24+03:00`.
- **Безопасность данных.** API использует очищенный текст и результаты его анализа. Маршруты вакансий, списка откликов, карточки и источника цитаты исключают `source_documents.raw_text` и поля `candidate_pii` из ответа.
- **Подсветка цитат в браузере (Python Unicode vs JavaScript UTF-16):**
  - В БД `Evidence.start` / `Evidence.end` хранятся в кодовых точках Unicode (`database.md`, п. 2.11).
  - При наличии символов вне BMP (эмодзи и т. п.) до цитаты `String.prototype.slice(start, end)` в JavaScript смещается.
  - Поэтому в HTTP-ответе каждый объект `EvidenceDTO` содержит **оба** набора границ: исходные `start`/`end` (Unicode) и вычисленные бэкендом `utf16_start`/`utf16_end` (`len(text[:start].encode("utf-16-le")) // 2`). Фронтенд для подсветки в JS использует `utf16_start`/`utf16_end`.
- **Учебный и рабочий контуры [v0.2]** (`database.md` п. 2.6.1):
  - Действующий профиль должности API берёт **только** через `get_approved_profile`. По умолчанию все маршруты работают в рабочем контуре: `approved_profile_*` — рабочий профиль, учебные кандидаты (`candidates.is_synthetic`) в списки откликов не попадают, `no_approved_profile` значит «нет утверждённого рабочего профиля», даже если учебный утверждён.
  - Учебный срез — только явным query-параметром `contour=training` у `GET /vacancies` и `GET /vacancies/{id}/applications`: учебные кандидаты и учебный утверждённый профиль (`get_approved_profile(..., synthetic=True)`). Так `qa-01` показывает `py-9001` с утверждённым учебным профилем, не задевая рабочий список.
  - Каждый профиль, кандидат и оценка в ответах несут `is_training` (оценка учебная, если учебный кандидат или профиль). При `is_training = true` интерфейс показывает плашку «Учебный пример — не рабочая рекомендация».
- **Единый формат ошибок:**

```json
{
  "error": {
    "code": "APPLICATION_NOT_FOUND",
    "message": "Отклик не найден",
    "details": {}
  }
}
```

Коды HTTP: `400` (некорректный запрос), `401` (нет пользователя в `X-User-Login` или он неизвестен/отключён) [v0.3], `403` (роли пользователя действие недоступно), `404` (сущность не найдена), `409` (конфликт состояния: перевод из финального этапа, перескок без подтверждения, действие над внешним откликом), `422` (ошибка валидации запроса или неизвестный код справочника).

### 1.2. Учебная авторизация стенда [v0.4]

- Маршруты чтения раздела 2 заголовков не требуют.
- Все маршруты раздела 3 (и чтение, и запись) требуют заголовок `X-User-Login: <логин>`. API находит активного пользователя в `users` и берёт роль из базы (клиент роль не присылает). Пользователь пишется в журналы: `stage_events.actor_user_id`, `reserve_entries.added_by_user_id` и `ended_by_user_id`.
- Учётки стенда загружает `python -m app.db.seed`: `hr_demo` (роль `hr`), `dept_demo` и `dept2_demo` (`department`), `admin_demo` (`admin`). Пароля нет: это подпись действия, а не защита. В рабочей эксплуатации её заменит вход через систему учётных записей администрации.
- Нет заголовка → `401 USER_REQUIRED`; логин неизвестен или отключён → `401 UNKNOWN_USER`; роль не подходит → `403 FORBIDDEN_ROLE` с `details.role` и `details.allowed_roles`.

| Маршруты | Роли |
|---|---|
| справочники, история и перевод этапа, кросс-оценки, дополнительная передача, перенос срока передачи, резерв, воронка, снимки публикаций (`/posting-snapshots*`) | `hr`, `admin` |
| сводка передачи, очередь передач, отзывы департамента ([workflow.md](workflow.md)), карточка отклика, разрешение публикации (`/posting-resolution` — только чтение без `department`), текст переданного отклика | `hr`, `admin`, назначенный `department` (чужое → `403 FORBIDDEN_SCOPE`, `/posting-resolution` для `department` → `403 FORBIDDEN_ROLE`) |
| общие списки (`/vacancies*`, `/comparison`, `/posting-resolution`), администрирование этапов/резерва, создание передач и перенос срока | `department` получает `403 FORBIDDEN_ROLE` |

#### Область доступа роли `department` (`workflow-01`, стык для `interview-01`)

Роль `department` не имеет доступа ко всей базе откликов и видит только конкретные передачи, адресованные ей в `handoff_attempts`:

- **Правило назначения отклика:** пользователь с ролью `department` допущен к `application_id` тогда и только тогда, когда в таблице `handoff_attempts` существует запись с `application_id = application_id` и `recipient_user_id = user.id` (`repo.has_department_application_access(session, user.id, application_id)`).
- **Правило доступа к тексту резюме:** для `GET /api/v1/candidate-texts/{candidate_text_id}` пользователь `department` допущен тогда и только тогда, когда `candidate_text_id` присутствует в `summary_snapshot["referenced_text_ids"]` хотя бы одной назначенной ему попытки передачи (`repo.has_department_text_access(session, user.id, candidate_text_id)`).
- **Правило доступа к попытке и отзывам:** `GET /api/v1/handoffs/{attempt_id}` и `POST /api/v1/applications/{id}/feedback` проверяют `attempt.recipient_user_id == user.id`; `GET /api/v1/handoffs` при вызове под ролью `department` автоматически фильтруется по `recipient_user_id = user.id` (и возвращает `403 FORBIDDEN_SCOPE` при явной передаче чужого `recipient_user_id`); `GET /api/v1/applications/{id}/handoffs` и `GET /api/v1/applications/{id}/feedback` отдают только попытки/отзывы, относящиеся к передачам этого пользователя; `GET /api/v1/applications/{id}/handoff-summary` возвращает замороженный снимок (`from_snapshot = true`) последней назначенной этому пользователю попытки.
- **Коды отказов и порядок проверок:**
  - Если маршрут запрещён роли целиком (всё из `StaffUser` или `auth.ensure_not_department(user)`) → `403 FORBIDDEN_ROLE`.
  - Если для роли `department` запрашивается неназначенный `application_id` / `attempt_id` / `candidate_text_id` (в том числе несуществующий UUID) → `403 FORBIDDEN_SCOPE` (до проверки `404`, чтобы нельзя было перебирать чужие идентификаторы).
- **Публичные точки переиспользования в `app/api/auth.py` и `app/db/repository.py`:**
  - `auth.AuthenticatedUser` (`current_user`, требует `X-User-Login`), `auth.OptionalUser` (`optional_user`, проверяет заголовок при наличии), `auth.StaffUser` (`require_role(UserRole.HR, UserRole.ADMIN)`), `auth.ensure_not_department(user)`.
  - `repo.has_department_application_access(session, user_id, application_id) -> bool` и `repo.has_department_text_access(session, user_id, candidate_text_id) -> bool`.
- **Подключение `interview-01` после слияния `hr#27`:** чтение гайда интервью (`GET /api/v1/applications/{id}/interview-guide`) может использовать `AuthenticatedUser` + `repo.has_department_application_access(session, user.id, application_id)` (при `False` возвращать `403 FORBIDDEN_SCOPE`), а создание/редактирование гайда и запись ответов (`POST`/`PATCH`) остаются под `StaffUser` (`hr`, `admin`).

### 1.3. Рабочие и внешние отклики [v0.4]

Рабочие действия и счётчики — только для откликов `source = response`. Внешний отклик из «Истории общения» (`history`, БД v1.6 п. 4.5) и ручная запись (`manual`) читаются как предыстория (карточка, история этапов). Перевод этапа и использование такого отклика как основания резерва дают `409 NOT_WORKING_APPLICATION`, а воронка их не считает.

## 2. Маршруты Этапа 1 (только чтение — первый сквозной срез)

### 2.1. `GET /api/v1/vacancies`
Список вакансий для выбора на стартовом экране.

**Ответ `200 OK`:**
```json
{
  "items": [
    {
      "vacancy_id": "22222222-2222-4222-8222-222222222222",
      "position_id": "33333333-3333-4333-8333-333333333333",
      "position_code": "python-dev",
      "title": "Python-разработчик",
      "employer": "АНО «Аналитический центр города Нижнего Новгорода»",
      "is_municipal_service": false,
      "channel": "hh_ru",
      "status": "open",
      "approved_profile_id": "44444444-4444-4444-8444-444444444444",
      "approved_profile_version": 1,
      "approved_profile_is_training": true,
      "applications_count": 1
    }
  ]
}
```
Пример показан для `contour=training` (учебный профиль `py-9001`). Если у должности нет утверждённого профиля в запрошенном контуре: `approved_profile_id = null`, `approved_profile_version = null` (интерфейс явно показывает «Утверждённый профиль требований недоступен»). `applications_count` считает отклики кандидатов того же контура.

### 2.2. `GET /api/v1/vacancies/{vacancy_id}/applications`
Список откликов выбранной вакансии. Query-параметры (опциональные): `contour` (`working` по умолчанию | `training`), `stage_code`, `formal_result` (`met` | `not_met` | `unknown`), `formal_preliminary` (`true` | `false`), `assessment_status` (`ready` | `not_assessed` | `stale` | `no_approved_profile`), `sort` (`date` по умолчанию | `fit` — светофор и порядок по соответствию). В элементе списка добавлены `is_training`, `formal_preliminary` («допуск выполнен по резюме, нужен документ») и поля светофора (`app/assessment/ranking.py`): `rank_group` (`ready` | `clarify` | `not_met` | `needs_action`), `rank_position` (место внутри всей вакансии `1..N`, для `needs_action` всегда `null`; вычисляется до фильтров), `rank_reason`. Профиль для светофора — тот, по которому оценён именно этот отклик: цель берётся из `posting_resolution` (requirements-03), а не одна на вакансию. Отклик без готовой цели (`mapping_required`, `no_approved_profile`, `not_applicable`) или без актуальной оценки попадает в `needs_action` (⚪) с причиной.

**Ответ `200 OK`** (пустой список при отсутствии откликов: `{"vacancy_id": "...", "total": 0, "items": []}`):
```json
{
  "vacancy_id": "22222222-2222-4222-8222-222222222222",
  "total": 1,
  "items": [
    {
      "application_id": "55555555-5555-4555-8555-555555555555",
      "candidate_id": "66666666-6666-4666-8666-666666666666",
      "candidate_code": "py-9001",
      "headline": "Python-разработчик (синтетический пример)",
      "current_stage_code": "new",
      "current_stage_title": "Новый отклик",
      "applied_at": "2026-11-19",
      "posting_title": null,
      "assessment_status": "ready",
      "formal_result": "unknown",
      "overall_score": 85,
      "missing_count": 1,
      "rank_group": "clarify",
      "rank_position": 1,
      "rank_reason": "1 вопрос к уточнению: длительность коммерческого опыта"
    }
  ]
}
```

**Различение статусов оценки (`assessment_status`):**
- `"ready"` — есть актуальная оценка по текущему `approved`-профилю и текущей версии текста; `formal_result` содержит `"met" | "not_met" | "unknown"`.
- `"stale"` — оценка есть, но текст кандидата или утверждённый профиль обновились; интерфейс показывает предупреждение об устаревании.
- `"not_assessed"` — утверждённый профиль есть, но оценка ещё не запускалась (`formal_result = null`, `overall_score = null`). **Не путать с `formal_result = "unknown"`!**
- `"no_approved_profile"` — для должности нет утверждённого профиля требований (`formal_result = null`).

### 2.3. `GET /api/v1/applications/{application_id}`
Полная карточка отклика: обезличенная карточка кандидата, пробелы, раздельный блок формальных требований и блок компетенций со ссылками на цитаты.

**Ответ `200 OK` (контрольный пример `py-9001`, сценарий `unknown`):**
```json
{
  "application_id": "55555555-5555-4555-8555-555555555555",
  "vacancy": {
    "vacancy_id": "22222222-2222-4222-8222-222222222222",
    "position_code": "python-dev",
    "title": "Python-разработчик",
    "is_municipal_service": false
  },
  "posting_title": null,
  "stage": {
    "code": "new",
    "title": "Новый отклик",
    "is_final": false
  },
  "candidate": {
    "candidate_id": "66666666-6666-4666-8666-666666666666",
    "code": "py-9001",
    "headline": "Python-разработчик (синтетический пример)",
    "current_text_id": "11111111-1111-4111-8111-111111111111",
    "pii_hidden": true,
    "card": {
      "version": 1,
      "extractor": "fake-llm/stage-1",
      "headline": "Python-разработчик (синтетический пример)",
      "applied_to": ["Python-разработчик"],
      "education": [],
      "courses": [],
      "experience_years": null,
      "experience": [],
      "skills": [{"name": "API-тесты", "level": null}],
      "languages": [],
      "about": null,
      "cover_letter": null,
      "missing": ["длительность коммерческого опыта"],
      "pii_hidden": true
    }
  },
  "assessment_status": "ready",
  "assessment": {
    "assessment_id": "77777777-7777-4777-8777-777777777777",
    "version": 1,
    "profile_id": "44444444-4444-4444-8444-444444444444",
    "profile_version": 1,
    "profile_status": "approved",
    "is_training": true,
    "formal_preliminary": false,
    "model": "fake-llm/stage-1",
    "created_at": "2026-11-19T18:10:00+03:00",
    "is_stale": false,
    "stale_reason": null,
    "formal_result": "unknown",
    "overall_score": 85,
    "summary": "Есть свидетельство по тестированию API; длительность коммерческого опыта не указана и требует уточнения.",
    "formal_checks": [
      {
        "requirement_id": "88888888-8888-4888-8888-888888888888",
        "kind": "experience",
        "description": "Подтверждённый общий коммерческий опыт не менее 2 лет",
        "is_mandatory": true,
        "verification": "resume",
        "check_stage": "screening",
        "source_quote": "synthetic_test_rule: stage-0b-02 (учебный порог 2 года)",
        "result": "unknown",
        "basis": "resume",
        "is_preliminary": false,
        "confirmed_by": null,
        "explanation": "В очищенном тексте резюме нет сведений о длительности коммерческого опыта.",
        "evidence": [],
        "alternatives": []
      }
    ],
    "competency_scores": [
      {
        "competency_id": "99999999-9999-4999-8999-999999999999",
        "rank": "special",
        "code": "API_TEST",
        "name": "Автоматизированное тестирование API",
        "target_level_min": 70,
        "target_level_max": 100,
        "level": 85,
        "explanation": "Указан опыт написания API-тестов для сервиса заявок.",
        "evidence": [
          {
            "candidate_text_id": "11111111-1111-4111-8111-111111111111",
            "quote": "Написал API-тесты для сервиса заявок.",
            "start": 0,
            "end": 37,
            "utf16_start": 0,
            "utf16_end": 37
          }
        ]
      }
    ]
  }
}
```
Если `assessment_status` равен `"not_assessed"` или `"no_approved_profile"`, поле `assessment` равно `null`. Если карточка ещё не извлечена, `candidate.card = null`.

Дополнительные поля [v0.3, до этого были только в описании модуля]: `stale_reason` — `text_changed` | `profile_changed` при `is_stale = true`; `formal_checks[].key` — устойчивый ключ требования (`py.education.level`); `candidate.is_training`; `vacancy = null` у записи «Истории общения» без вакансии на платформе; `posting_title` — публикация hh, на которую пришёл отклик (БД v1.6), `null`, если её нет. В элементе списка откликов тоже есть `posting_title`, у текста кандидата (п. 2.4) — `is_training`.

Поля формального требования [v0.2]: `verification` — где требование положено подтверждать; `basis` — на чём результат фактически основан (`resume` у вывода модели; `documents` / `interview` / `test` — подтвердил человек, тогда `confirmed_by` — логин, а `evidence` пуст); `is_preliminary = true` — подпись «по резюме, нужен документ»; `alternatives` — `[{key, result, evidence}]` по ключам `params.alternatives`. Требования этапа `interview` показываются отдельным блоком «проверить на интервью» и на `formal_result` не влияют. Карточка отклика учебного кандидата открывается по id и в рабочем контуре, но всегда с `is_training = true`.

### 2.4. `GET /api/v1/candidate-texts/{candidate_text_id}`
Возвращает конкретную версию очищенного текста для панели источника и подсветки цитаты.

**Ответ `200 OK`:**
```json
{
  "candidate_text_id": "11111111-1111-4111-8111-111111111111",
  "candidate_id": "66666666-6666-4666-8666-666666666666",
  "candidate_code": "py-9001",
  "version": 1,
  "is_current": true,
  "redaction_method": "stage-0a-redactor-v1",
  "text": "Написал API-тесты для сервиса заявок.",
  "char_length": 37,
  "utf16_length": 37
}
```

### 2.5. `GET /api/v1/health`
Проверка доступности приложения и подключения к PostgreSQL (`{"status": "ok", "db": "ok"}`).

### 2.6. `POST /api/v1/search/candidates`

Поиск по профессиональному опыту в очищенных резюме (`M-03`). Тело запроса, серверная авторизация рабочего контура, DTO выдачи, границы цитат и ошибки описаны в [контракте поиска](search.md). Пример для учебного контура: `{"contour":"training","query":"анализ и согласование требований к ИС"}`.

## 3. Маршруты Этапа 2: действия кадровика, резерв, кросс-оценки, воронка [v0.4, backend-02]

Постановка: `hq/tasks/backend-02-denis-workflow-reserve-and-pii-api.md` в штабе. Передача руководителю и ответ департамента — `workflow-01`, гайд и ответы интервью — `interview-01`. Раскрытия ПДн в MVP нет: ни один маршрут не отдаёт `candidate_pii`.

**Общее для раздела:**
- Все маршруты требуют `X-User-Login` с ролью `hr` или `admin` (п. 1.2). Роль `department` получает `403 FORBIDDEN_ROLE`, в том числе на чтение по прямому ID: область доступа по подразделениям не согласована. Права департамента в своей области появятся в `workflow-01`.
- Действия и счётчики — только для откликов `source = response` (п. 1.3).
- Маршруты записи сами фиксируют транзакцию; при ошибке ничего не сохраняется.
- Вложенные объекты: `stage` — `{"code", "title", "is_final"}`; `rejection_reason` — `{"code", "title", "side"}` или `null`; `actor` / `added_by` / `ended_by` — `{"login", "role"}` или `null` (действие импорта).

### 3.1. Справочники

`GET /api/v1/references/stages` → `{"items": [{"code": "new", "title": "Новый отклик", "sort_order": 1, "is_final": false}, …]}` по `sort_order`.

`GET /api/v1/references/rejection-reasons` → `{"items": [{"code": "experience", "title": "Недостаточно профессионального опыта", "side": "employer"}, …]}`.

### 3.2. История и перевод этапа

`GET /api/v1/applications/{application_id}/history`:
```json
{
  "application_id": "8ca4a29c-6081-4745-b009-2cafb99286d2",
  "source": "response",
  "stage": {"code": "screening", "title": "Первичный отбор", "is_final": false},
  "last_seq": 2,
  "items": [
    {"seq": 1, "from_stage": null, "to_stage": {"code": "new", "title": "Новый отклик", "is_final": false},
     "rejection_reason": null, "actor": null, "comment": null, "created_at": "2026-11-20T11:30:09.289095Z"},
    {"seq": 2, "from_stage": {"code": "new", "title": "Новый отклик", "is_final": false},
     "to_stage": {"code": "screening", "title": "Первичный отбор", "is_final": false},
     "rejection_reason": null, "actor": {"login": "hr_demo", "role": "hr"},
     "comment": "Резюме релевантно, уточнить стаж", "created_at": "2026-11-20T11:30:09.289095Z"}
  ]
}
```
События идут по `seq`. `last_seq` — значение, которое форма передаёт как `expected_seq`. Исторический отказ без причины отдаётся с `rejection_reason = null`, интерфейс показывает «не указана».

`POST /api/v1/applications/{application_id}/stage`:
```json
{"to_stage_code": "rejected", "expected_seq": 4, "rejection_reason_code": "experience",
 "comment": "Стаж меньше двух лет", "confirm_skip": false}
```
- `expected_seq` обязателен: последний `seq` истории, который видел кадровик.
- Обычный шаг — следующий этап по порядку, «Отказ»/«Кандидат отказался» в любой момент, «Принят» — с последнего этапа. Перескок вперёд или возврат назад — только с `confirm_skip: true` и непустым `comment`.
- Для перехода в `rejected` и `withdrawn` причина обязательна, для остальных этапов запрещена.

**Ответ `201 Created`:** `{"application_id", "stage", "event"}`, где `event` — событие в формате истории. `event.seq` — новый `expected_seq`.

| HTTP | `error.code` | Когда |
|---|---|---|
| 404 | `APPLICATION_NOT_FOUND` | нет отклика |
| 409 | `NOT_WORKING_APPLICATION` | `source` не `response` (`history`, `manual`) |
| 422 | `UNKNOWN_STAGE_CODE`, `UNKNOWN_REJECTION_REASON` | кода нет в справочнике |
| 422 | `REJECTION_REASON_REQUIRED` | переход в `rejected`/`withdrawn` без причины |
| 422 | `REJECTION_REASON_NOT_ALLOWED` | причина при переходе на другой этап |
| 422 | `VALIDATION_ERROR` | нет `expected_seq` или `to_stage_code` |
| 409 | `STALE_STAGE_FORM` | `expected_seq` не равен последнему `seq`: отклик уже изменили в другой вкладке. `details`: `expected_seq`, `last_seq`, `current_stage_code` |
| 409 | `STAGE_TRANSITION_CONFLICT` | выход из финального этапа, тот же этап, перескок без подтверждения; `message` — правило по-русски |

Две вкладки с одним `expected_seq` дают один переход: строка отклика блокируется (`SELECT … FOR UPDATE`) до проверки `seq` и держится до commit, второй запрос получает `409 STALE_STAGE_FORM`.

```json
{"error": {"code": "STAGE_TRANSITION_CONFLICT", "message": "Отбор уже завершён на этапе «Отказ»",
           "details": {"current_stage_code": "rejected", "to_stage_code": "screening"}}}
```

Перевод в `sent_to_department` выполняется одной транзакцией вместе с регистрацией попытки передачи (обязательный блок `handoff`, подробнее — [workflow.md](workflow.md)). Без `handoff` возвращается `422 HANDOFF_REQUIRED`. При уходе с этапа передачи (кроме `department_interview`) открытые ожидания переводятся в `closed_without_response`.

### 3.3. Кросс-оценки по другим должностям

`GET /api/v1/candidates/{candidate_id}/cross-assessments` — оценки кандидата по всем должностям, у которых есть утверждённый профиль в контуре кандидата. Данные собирает модель чтения ai-02 `app.assessment.cross.cross_assessments` (владелец — Илья). API добавляет права (п. 1.2), `404` и порядок строк. Актуальность и цитаты считаются общими правилами `app.assessment.state`, теми же, что в п. 2.2–2.3, поэтому статус пары в списке откликов и здесь совпадает. Чтение не создаёт ни оценок, ни откликов. Явное сравнение одного отклика с выбранным профилем — `GET /applications/{id}/comparison` (дополнение v0.3).

```json
{
  "candidate_id": "eb5fb76d-b27a-4f7f-87ab-69fcd5b7ac61",
  "candidate_code": "py-9001",
  "is_training": true,
  "current_text_id": "fc616e86-…",
  "applications": [
    {"application_id": "8ca4a29c-…", "vacancy_id": "…", "position_code": "python-dev",
     "source": "response", "posting_title": null, "current_stage_code": "new"}
  ],
  "items": [
    {
      "position_id": "…", "position_code": "qa-manual", "position_title": "QA Engineer (Manual)",
      "is_municipal_service": false, "profile_id": "…", "profile_version": 1, "is_training": true,
      "is_source_position": false,
      "vacancies": [
        {"vacancy_id": "…", "title": "QA Engineer (Manual)", "channel": "hh_ru", "status": "open",
         "application_id": null, "application_source": null, "application_stage_code": null}
      ],
      "assessment_status": "ready", "stale_reason": null,
      "assessment": {
        "assessment_id": "…", "version": 1, "profile_id": "…", "profile_version": 1,
        "formal_result": "met", "formal_preliminary": false, "overall_score": 90,
        "summary": null, "gaps": [], "formal_checks": [],
        "competencies": [
          {"competency_id": "…", "code": "API_TEST", "name": "Тестирование API", "rank": null,
           "target_level_min": 60, "target_level_max": 100, "level": 90, "explanation": "пишет API-тесты",
           "mandatory": null, "desired": null,
           "evidence": [{"candidate_text_id": "fc616e86-…", "quote": "Написал API-тесты",
                         "start": 0, "end": 17, "utf16_start": 0, "utf16_end": 17}]}
        ]
      }
    }
  ],
  "empty_reason": null
}
```
- `vacancies` — все вакансии должности; у каждой отклик кандидата (`application_id`, `application_source`, `application_stage_code`) или `null`. `is_source_position` — есть прямой отклик `response` хотя бы на одну из них. `position_id` нужен для `POST /reserve` из строки рекомендации.
- `profile_id`/`profile_version` строки — утверждённый сейчас профиль. Внутри `assessment` — профиль самой оценки: при `profile_changed` это прежняя версия, и строки проверок взяты из неё.
- `formal_checks[]`: `requirement_key`, `description`, `is_mandatory`, `check_stage`, `result`, `basis`, `is_preliminary`, `evidence`. `gaps` — требования этапа `screening` с `unknown`.
- `assessment_status`: `ready`, `stale` (`stale_reason`: `text_changed`, `algorithm_changed` — алгоритм или промпт, `profile_changed`), `not_assessed`.
- Цитаты: `candidate_text_id` указывает на свою версию текста, `utf16_start`/`utf16_end` считаются по ней.
- `level` и `overall_score` новый оценщик (БД v1.7) оставляет `null`; заполнены у оценок, где их записали.
- Порядок: сначала оценённые — `met`, `unknown`, `not_met`, внутри по `overall_score` по убыванию; затем `not_assessed`.
- Пустой результат — `200`, `items: []`, `empty_reason: "no_approved_profiles"`. Неизвестный кандидат — `404 CANDIDATE_NOT_FOUND`.

### 3.4. Кадровый резерв

`POST /api/v1/reserve`:
```json
{"candidate_id": "eb5fb76d-…", "position_id": "9ee53c09-…", "competency_area": null,
 "source_application_id": "8ca4a29c-…",
 "reason": "Сильные API-тесты, не хватило стажа",
 "contact_basis": "Вернуться при новой вакансии QA",
 "valid_until": "2027-05-20"}
```
- Цель — должность (`position_id`) или направление (`competency_area`).
- `reason` (обоснование профессиональной пригодности) и `contact_basis` (основание повторного контакта) обязательны.
- `valid_until` по желанию; пусто — бессрочно. Прошедшая дата — ошибка.
- Исходный отклик, если указан, должен принадлежать тому же кандидату и быть откликом `response`.

Ответ `201` (`created: true`) для новой записи. Если у кандидата уже есть действующая запись на эту цель, ответ `200` (`created: false`) с прежней записью. Так же отвечают два одновременных запроса: уникальный индекс пропускает одну вставку, второй запрос возвращает её запись. Если прежняя запись истекла, она закрывается (`status = expired`) и открывается новый период со своим основанием и автором.

```json
{
  "created": true,
  "entry": {
    "reserve_id": "c5dea982-0151-4ec7-9145-80288a24d26b",
    "candidate_id": "eb5fb76d-b27a-4f7f-87ab-69fcd5b7ac61", "candidate_code": "py-9001", "headline": null,
    "is_training": true, "position_id": "9ee53c09-…", "competency_area": null,
    "source_application_id": "8ca4a29c-…",
    "reason": "Сильные API-тесты, не хватило стажа", "contact_basis": "Вернуться при новой вакансии QA",
    "status": "active", "added_by": {"login": "hr_demo", "role": "hr"},
    "added_at": "2026-11-20T11:30:09.289095Z", "valid_until": "2027-05-20",
    "ended_at": null, "end_reason": null, "ended_by": null
  }
}
```

| HTTP | `error.code` | Когда |
|---|---|---|
| 404 | `CANDIDATE_NOT_FOUND`, `POSITION_NOT_FOUND`, `APPLICATION_NOT_FOUND` | нет кандидата, должности или исходного отклика |
| 422 | `RESERVE_TARGET_REQUIRED` | нет ни должности, ни направления |
| 422 | `RESERVE_BASIS_REQUIRED` | пустой `reason` или `contact_basis`; `details.missing` |
| 422 | `RESERVE_VALID_UNTIL_IN_PAST` | срок уже прошёл |
| 422 | `APPLICATION_OF_OTHER_CANDIDATE` | исходный отклик другого кандидата |
| 409 | `NOT_WORKING_APPLICATION` | исходный отклик `history`/`manual` |

`POST /api/v1/reserve/{reserve_id}/withdraw` `{"reason": "Кандидат трудоустроен в другом месте"}` отзывает основание. Запись получает `status = withdrawn`, `ended_at`, `end_reason`, `ended_by`, пропадает из списка и фильтра поиска и остаётся в истории. Возобновление — новый `POST /reserve` с новым основанием. Ошибки: `404 RESERVE_NOT_FOUND`, `422 WITHDRAW_REASON_REQUIRED`, `409 RESERVE_NOT_ACTIVE`.

`GET /api/v1/positions/{position_id}/reserve?contour=` → `{"position_id", "position_code", "total", "items": [ReserveEntry…]}`: действующие записи на должность по времени добавления. Действующая запись — `status = active` и `valid_until` пусто или не раньше сегодняшнего дня, последний день срока включён. Это же правило — `repository.active_reserve_condition()` — использует фильтр поиска `search-01`. Резерв «по направлению» в список должности не входит. Ошибка: `404 POSITION_NOT_FOUND`.

### 3.5. Воронка

`GET /api/v1/analytics/funnel?contour=&vacancy_id=&position_id=&period_from=&period_to=&department=` — счётчики по фактическим записям базы. Выборка — отклики `source = response` на вакансии платформы от кандидатов выбранного контура (опциональный `department` фильтрует открытые ожидания `open_waits`).

```json
{
  "as_of": "2026-11-20T11:30:09.553480Z",
  "contour": "working",
  "vacancy_id": null,
  "position_id": null,
  "period_from": "2026-11-01",
  "period_to": "2026-11-30",
  "timezone": "Europe/Moscow",
  "total_applications": 1721,
  "stages": [
    {"code": "new", "title": "Новый отклик", "sort_order": 1, "is_final": false, "current_count": 1719, "reached_count": 1721},
    {"code": "rejected", "title": "Отказ", "sort_order": 8, "is_final": true, "current_count": 2, "reached_count": 2}
  ],
  "closures": [
    {"stage_code": "rejected", "stage_title": "Отказ", "reason_code": "experience",
     "reason_title": "Недостаточно профессионального опыта", "side": "employer", "count": 1},
    {"stage_code": "rejected", "stage_title": "Отказ", "reason_code": null,
     "reason_title": "Причина не указана", "side": null, "count": 1}
  ],
  "closures_without_reason": 1,
  "open_waits": {
    "total": 1,
    "unique_applications": 1,
    "due_soon_total": 0,
    "overdue_total": 0,
    "extended_total": 0,
    "max_wait_hours": 12.5,
    "median_wait_hours": 12.5,
    "by_department": [
      {"department": "Департамент-заказчик (учебный)", "total": 1, "unique_applications": 1,
       "due_soon_total": 0, "overdue_total": 0, "extended_total": 0,
       "max_wait_hours": 12.5, "median_wait_hours": 12.5}
    ]
  }
}
```
- `as_of` — момент среза.
- `stages` — все этапы справочника, в том числе с нулями. `current_count` — уникальные отклики, которые сейчас на этапе; `reached_count` — отклики, у которых есть переход на этап.
- `closures` — решения о закрытии (переходы в `hired`, `rejected`, `withdrawn`) с причиной. Период задают даты включительно; сутки считаются по `timezone` (Нижний Новгород, МСК). Без дат — за всё время. Исторические отказы без причины — строки с `reason_code = null`, их сумма — в `closures_without_reason`.
- `open_waits` — открытые ожидания ответа (`status = awaiting_response` в `handoff_attempts`), число передач в статусе «скоро срок» (`due_soon_total`), просроченных (`overdue_total`), перенесённых (`extended_total`) и длительность ожидания в часах на `as_of` с разбивкой по подразделениям. При отсутствии ожиданий возвращает нули (`total: 0`, `by_department: []`).
- Ошибки: `404 VACANCY_NOT_FOUND`, `404 POSITION_NOT_FOUND`, `422 INVALID_PERIOD` (`period_from` позже `period_to`).
- Годовой отчёт (`/api/v1/reports/annual/…`, `reporting.md`) строится из выгрузки и базу не читает. Эта воронка — оперативный срез живых записей.

### 3.6. Запланировано и связанные контракты

- Разрешение публикаций и снимки `T-13` (`requirements-03`) — [posting-position-register.md](posting-position-register.md#http-и-совместимость).
- Передача руководителю, очередь ожиданий, сроки/переносы, версионный ответ департамента и права `department` — [workflow.md](workflow.md).
- `POST /api/v1/search/candidates` с фильтром действующего резерва — `search-01` ([search.md](search.md)).

## 4. Гайд интервью, ответы, подтверждение требования [v0.6, interview-01]

Полный контракт — [interview.md](interview.md) v0.4 §4: тела запросов, `InterviewGuideOut`, `InterviewQuestionOut`, статусы вопросов, матрица оснований. Здесь — маршруты, права и коды ошибок в общем формате п. 1.

| Маршрут | Ответ | Права |
|---|---|---|
| `POST /api/v1/applications/{application_id}/interview-guide` | `201` новая версия; `200` существующая (без `regenerate`, основание не изменилось, гонка); повтор `request_id` — тот же гайд и тот же код | `hr`, `admin` |
| `GET /api/v1/applications/{application_id}/interview-guide?kind=phone[&guide_version=N]` | `200` снимок версии и то, что считается по текущей оценке: `is_stale`, `stale_reason`, `status` вопросов, `document_requests` | `hr`, `admin` |
| `POST /api/v1/interviews/{interview_id}/questions/{question_id}/answers` | `201` новая ревизия; `200` повтор `request_id` | `hr`, `admin` |
| `GET /api/v1/interviews/{interview_id}/questions/{question_id}/answers` | `200` все ревизии по возрастанию | `hr`, `admin` |
| `POST /api/v1/assessments/{assessment_id}/formal-checks/{requirement_id}/confirm` | `201` новая версия оценки (`AssessmentOut`); `200` повтор `request_id` | `hr`, `admin` |

Роль `department` получает `403 FORBIDDEN_ROLE` на всех маршрутах до workflow-01. Без заголовка — `401 USER_REQUIRED`.

**Ошибки.**
- **Гайд:**
  - `404 APPLICATION_NOT_FOUND`, `GUIDE_NOT_FOUND`;
  - `409` `NOT_WORKING_APPLICATION`, `ASSESSMENT_REQUIRED`, `ASSESSMENT_STALE` (`details.stale_reason`), `NOT_APPLICABLE`, `MAPPING_REQUIRED`, `NO_APPROVED_PROFILE`, `ASSESSMENT_CHANGED` (оценка или рубрика сменилась за время вызова модели), `REQUEST_ID_REUSED`;
  - `503 LLM_UNAVAILABLE` — модель недоступна;
  - `502 LLM_INVALID_RESPONSE` — ответ модели не прошёл схему после исправления.

  При `503` и `502` новая версия не создаётся, прежняя читается по `GET`.
- **Ответ:**
  - `404 INTERVIEW_NOT_FOUND`, `QUESTION_NOT_FOUND` (в том числе вопрос чужого отклика);
  - `409 REVISION_CONFLICT` (`details.current_revision`, `current_answer_id`), `GUIDE_SUPERSEDED` (`details.guide_version`), `REQUEST_ID_REUSED`;
  - `422` `VALIDATION_ERROR` (пустой текст, длиннее 4000 символов, `source` вне `phone`/`in_person`/`written`), `ANSWER_REJECTED`.
- **Подтверждение:**
  - `404 ASSESSMENT_NOT_FOUND`, `REQUIREMENT_NOT_IN_PROFILE`;
  - `409` `ASSESSMENT_NOT_CURRENT` (`details.current_assessment_id`), `BASIS_NOT_ALLOWED` (`details.verification`, `allowed_bases`), `ANSWER_REQUIRED` (`basis = interview` без `answer_id`), `ANSWER_NOT_FOR_REQUIREMENT`, `REQUEST_ID_REUSED`;
  - `422` `VALIDATION_ERROR` (`basis = resume`, пустой `comment`), `CONFIRM_REJECTED` (профиль в архиве и другие правила оценки).

Проверки прав, принадлежности и ревизии выполняются до записи. При отказе строк не появляется.
