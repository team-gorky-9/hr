# Контракт: HTTP API (`app/api/`)

**Версия:** 0.2 (проект к Этапу 1 + контур Этапа 2) · **Дата:** 2026-11-20 · **Владелец:** Денис · **Потребители:** фронтенд (`frontend/`, Ася).

Опирается на [database.md](database.md) v1.5 и [assessment.md](assessment.md) v0.2.

**Изменения v0.2:** учебный и рабочий контуры (п. 1.1), признаки `is_training`, `is_preliminary`, `formal_preliminary`, основание `basis` и альтернативы в блоке формальных требований.

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

Коды HTTP: `400` (некорректный запрос), `403` (нет прав), `404` (сущность не найдена), `409` (конфликт состояния/перехода этапа), `422` (ошибка валидации схемы).

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
Список откликов выбранной вакансии. Query-параметры (опциональные): `contour` (`working` по умолчанию | `training`), `stage_code`, `formal_result` (`met` | `not_met` | `unknown`), `formal_preliminary` (`true` | `false`), `assessment_status` (`ready` | `not_assessed` | `stale` | `no_approved_profile`). В элементе списка добавлены `is_training` и `formal_preliminary` («допуск выполнен по резюме, нужен документ»).

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
      "assessment_status": "ready",
      "formal_result": "unknown",
      "overall_score": 85,
      "missing_count": 1
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

## 3. Запланированные маршруты Этапа 2 (контур наперёд)

Фиксируются названиями и семантикой; подробные DTO уточняются перед выдачей `backend-02`:
- `GET /api/v1/candidates/{candidate_id}/cross-assessments` — оценки кандидата по другим утверждённым профилям (`M-02`).
- `POST /api/v1/applications/{application_id}/stage` — ручной перевод этапа кадровиком (`move_application`), возвращает `StageEvent`; `409` при попытке перевода из финального этапа.
- `GET /api/v1/applications/{application_id}/history` — журнал `stage_history` по `seq`.
- `POST /api/v1/applications/{application_id}/feedback` — сохранение обратной связи департамента (`record_department_feedback`, **не** меняет этап).
- `GET /api/v1/applications/{application_id}/handoff-summary` — чистая обезличенная сводка кандидата (формальный итог, цитаты, пробелы, заметки кадровика) в JSON + готовом тексте для передачи руководителю «наверх».
- `GET/POST /api/v1/applications/{application_id}/interview-guide` — чтение и генерация вопросов по пробелам (`A-11`/`M-09`).
- `POST /api/v1/reserve` и `GET /api/v1/positions/{position_id}/reserve` — рабочий кадровый резерв (`M-05`/`A-05`).
- `GET /api/v1/analytics/funnel` — сводка воронки по фактическим `stage_events` (`O-01`).
- `POST /api/v1/search/candidates` — смысловой и навыковый поиск по очищенным текстам (`M-03`).
