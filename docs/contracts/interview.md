# Контракт гайда интервью и ответов

**Версия:** v0.1 · **проект на согласовании** (Илья предлагает, Денис подтверждает хранение, права и HTTP; Давид — рубрику; Ася — DTO экрана). До подтверждения код по этому файлу не пишется.
**Постановка:** `interview-01` в штабе (`hq/tasks/interview-01-guide-and-answers.md`). **Опирается на:** [database.md](database.md) v1.7 (оценки, `competency_scores.details`, `confirm_formal_check`), [assessment.md](assessment.md) v0.3, [api.md](api.md) v0.3.
**Пометки происхождения:** [задача] — из постановки `interview-01`; [иссл.] — из `research/notes/problem-mechanisms-screening-and-interview.md` штаба; [предл.] — предложение Ильи, требует подтверждения.

## 1. Что получает кадровик

Открыв отклик, кадровик нажимает «Подготовить звонок» и получает гайд из двух списков [задача]:

- **`core[]` — общее ядро должности.** Вопросы по строкам профиля с `check_stage = interview` (знание законов, качества из матрицы). Одинаковы для всех кандидатов одной версии профиля, у каждого вопроса критерий ответа. Модель не персонализирует ядро [иссл.: у `HR_recruiter_assistant` генератор персонализирует даже обязательные навыки — этого избегаем].
- **`clarifications[]` — уточнения именно для этого человека.** По значимым пробелам его оценки: `unknown` по обязательному требованию, отсутствие свидетельства по индикатору, противоречие, требующее ручной сверки. Не больше бюджета (по умолчанию 6); остальные пробелы видны списком `uncovered_gaps`.
- **`document_requests[]` — что попросить документом** [предл.]. Предварительный вывод по резюме (`is_preliminary`, `verification = documents`) — не вопрос на звонке, а просьба принести диплом или справку. Модель не вызывается.

Ответ записывается под конкретным вопросом с автором, временем и источником. Формальный итог меняет только отдельное действие «подтвердить требование» (`confirm_formal_check`), а не сам ответ [задача].

## 2. Сборка пробелов — код, без модели

`GapAssembler` получает текущую оценку отклика, карточку той же версии текста и профиль оценки.

| Источник | Что становится пробелом | Приоритет |
|---|---|---|
| `formal_checks`, `check_stage = screening`, `result = unknown` | одно требование — один пробел; заголовок из `explanation.gap` или описания требования | 1 — обязательное, 3 — желательное |
| `formal_checks`, `is_preliminary`, `verification = documents` | не пробел, а элемент `document_requests[]` | — |
| `competency_scores.details.indicators`, `status = no_info`, `check_stage = screening` | индикаторы одной компетенции объединяются в один пробел [предл.]; группа `same_as` — одна единица | 2 — есть обязательный, 4 — только желательные |
| `details.groups`, `manual_review = true` | противоречие «подтверждено + опровергнуто» — пробел «сверить» | 2 |
| `card.missing` | слово из словаря `MISSING_VOCABULARY` сопоставляется с требованием (`длительность коммерческого опыта`, `опыт работы` → `experience`; `образование` → `education_level`; `направление подготовки` → `education_field`). Совпало с уже найденным пробелом — добавляется источником, отдельного вопроса нет. Не совпало ни с одним требованием профиля — не пробел | как у требования |

- `level = null` сам по себе не пробел [задача].
- Исключённые индикаторы (`excluded_from_scoring`) и строки `interview` в уточнения не попадают: последние — это `core[]`.
- **`gap_ref_id`** = `gap:` + первые 12 символов SHA-256 от отсортированных ключей источников (`formal:<requirement_key>`, `indicator:<key>`, `group:<same_as>`). Зависит только от строк профиля, поэтому при повторной оценке той же пары пробел сохраняет идентификатор и уже записанный ответ остаётся при нём [предл.].
- Порядок: приоритет, затем `sort_order` строки профиля. Первые `budget` идут в генерацию, остальные — в `uncovered_gaps[]`.
- **Пробелов нет → `clarifications = []`, вызовов модели — 0** [задача].

## 3. Генерация вопросов — модель с проверкой кодом

**Уточнения.** Один вызов на гайд: пробелы с заголовком, критериями `acceptance` исходных строк (`met` / `unknown`) и цитатами уже найденного. Модель возвращает `[{gap_ref_id, question, good_answer, insufficient_answer}]`.

Код проверяет:
- `gap_ref_id` — только из переданных, каждый ровно один раз (схема с проверкой ключей, как в оценщике: неизвестный ключ уходит на одно исправление, затем `LLMInvalidResponseError`);
- вопрос не длиннее 300 символов, без ПДн из `candidate_pii`;
- пропущенный пробел переносится в `uncovered_gaps` с причиной `not_generated`.

**Ядро.** Вопросы по строкам `interview` генерируются **один раз на версию профиля** и хранятся как рубрика `rubric_status = draft`, `author = model`. Все кандидаты этой версии получают одни и те же вопросы. После правки и утверждения Давидом или кадровиком — `rubric_status = approved`, `author = human` [предл.].

Промпт и версия — `GUIDE_PROMPT_VERSION = "guide-v1"`. В журнал `llm_call` — без текста резюме.

## 4. HTTP

### `POST /api/v1/applications/{application_id}/interview-guide`

Тело: `{"kind": "phone", "regenerate": false, "request_id": "<uuid>"}`.

- `kind`: `phone` | `department` [задача: «раздельные сессии нужны, если участники и время различаются»].
- Повтор с тем же `request_id` возвращает ранее созданный гайд.
- `regenerate = true` создаёт новую версию гайда при новой оценке; ответы переносятся по `gap_ref_id` и ключу строки ядра.

Ответ `200` — `InterviewGuideOut`.

### `GET /api/v1/applications/{application_id}/interview-guide?kind=phone`

Последний гайд или `404 guide_not_found`. Повторное чтение возвращает тот же набор и порядок.

### `InterviewGuideOut`

```json
{
  "interview_id": "uuid", "application_id": "uuid", "kind": "phone", "guide_version": 1,
  "is_training": true,
  "assessment_id": "uuid", "assessment_version": 1, "profile_id": "uuid", "profile_version": 1,
  "rubric_status": "draft",
  "is_stale": false, "stale_reason": null,
  "prompt_version": "guide-v1", "model_calls": 1, "created_at": "2026-11-20T15:00:00+03:00",
  "core": [ "InterviewQuestionOut" ],
  "clarifications": [ "InterviewQuestionOut" ],
  "document_requests": [ {"requirement_id": "uuid", "requirement_key": "py.education", "title": "Диплом о высшем образовании", "reason": "по резюме: Высшее, Прикладная информатика; подтверждается документом"} ],
  "uncovered_gaps": [ {"gap_ref_id": "gap:…", "title": "…", "reason": "over_budget"} ]
}
```

`stale_reason`: `assessment_changed` (у пары появилась новая оценка) | `profile_changed` | `rubric_changed`. Устаревший гайд читается по своей версии; ответы в нём не теряются.

### `InterviewQuestionOut`

```json
{
  "question_id": "uuid", "kind": "clarification", "sort_order": 1,
  "question": "С какого по какой месяц длился проект с API-тестами и в каком качестве вы в нём работали?",
  "criterion": {
    "good_answer": "Месяц и год начала и окончания; работа по найму или договору; собственные задачи.",
    "insufficient_answer": "«Около года», без дат или без указания характера работы."
  },
  "author": "model",
  "gap_ref_id": "gap:3f1c…",
  "sources": [
    {"type": "formal_check", "requirement_id": "uuid", "key": "py-train/requirement/experience-commercial-24m", "result": "unknown"},
    {"type": "card_missing", "value": "длительность коммерческого опыта"}
  ],
  "answer": null
}
```

У вопроса ядра `kind = "core"`, `gap_ref_id = null`, в `sources` — строка профиля (`type = "profile_row"`, `key`, `competency_id`).

### `POST /api/v1/interviews/{interview_id}/questions/{question_id}/answers`

Тело: `{"text": "С 03.2023 по 12.2024 по договору, писал API-тесты", "source": "phone", "expected_revision": 0, "request_id": "<uuid>"}`.

- `source`: `phone` | `in_person` | `written`.
- Ответ `201` — `AnswerOut`: `{answer_id, revision, text, source, author: {user_id, login}, created_at, previous_answer_id}`.
- Исправление создаёт новую ревизию, предыдущая читается.
- Повтор с тем же `request_id` возвращает ту же запись, второй строки нет.

Ошибки:
- `409 revision_conflict` — `expected_revision` не текущая, нужно перечитать гайд;
- `404 question_not_found` — вопрос не из этого интервью, сюда же подстановка вопроса чужого отклика;
- `403 forbidden` — не активный `hr` или `admin`.

### `POST /api/v1/assessments/{assessment_id}/formal-checks/{requirement_id}/confirm`

Тело: `{"result": "met", "basis": "documents", "comment": "Диплом 2015 г. проверен", "answer_id": "uuid|null"}`.

- Вызывает `confirm_formal_check`, ответ — новая версия оценки в формате `api.md`.
- `basis = interview` разрешён, только если `verification` требования — `interview` [предл.: сейчас `confirm_formal_check` принимает любое основание кроме `resume`]. Устный ответ на звонке по документальному требованию оставляет `is_preliminary` и элемент `document_requests` [задача, п. 4].
- `answer_id` связывает подтверждение с ответом, на который опирался кадровик.
- Этап отклика не меняется.

### Ошибки формирования гайда

| Код | Когда | Кадровик видит |
|---|---|---|
| `409 assessment_required` | у отклика нет текущей оценки | «Сначала оцените отклик» |
| `409 not_applicable` / `mapping_required` | отклик не к этому профилю (`profile-applicability.md`) | статус применимости, гайда нет |
| `409 assessment_stale` | оценка устарела (`api.md`, `stale_reason`) | «Переоценить» |
| `503 llm_unavailable` | модель недоступна | ранее сохранённый гайд с ответами остаётся доступен; новый не создан |

## 5. Хранение — предложение для Дениса

Сейчас есть `interviews` и `interview_questions` (`gap`, `question`, `author`, `answer_notes`, `score`). Для контракта не хватает:

| Что | Предложение [предл.] |
|---|---|
| версия гайда и её основание | `interviews`: `assessment_id`, `profile_id`, `guide_version`, `prompt_version`, `request_id` (уникален) |
| тип и происхождение вопроса | `interview_questions`: `kind` (`core` / `clarification`), `gap_ref_id`, `sources` jsonb, `criterion` jsonb, `requirement_id` / `indicator_key` null |
| ответы с историей | новая `interview_answers`: `question_id`, `revision`, `text`, `source`, `author_user_id`, `created_at`, `previous_answer_id`, `request_id` уникален; UNIQUE(`question_id`, `revision`) |
| рубрика ядра | новая `interview_rubric_questions`: `profile_id`, `row_key`, `question`, `criterion`, `author`, `status` (`draft` / `approved`), `approved_by_user_id`; одна строка на строку профиля |
| запросы документов | не храним отдельно: вычисляются из текущей оценки при чтении |

Старые `answer_notes` читаются как ответ ревизии 0 с `source = unknown` и пометкой «происхождение неизвестно» [задача].

## 6. Контрольный пример (критерии приёмки `interview-01`)

1. **`py-9001`, учебный профиль.** Стаж `unknown`, в карточке `missing: ["длительность коммерческого опыта"]`, индикатор API-тестов подтверждён.
   - Ожидание: `clarifications` — **один** вопрос про сроки и характер работы, оба источника в `sources`; `uncovered_gaps = []`, `document_requests = []`, `model_calls = 1`.
   - У учебного профиля нет строк `interview`, поэтому `core = []`.
2. **Второй кандидат того же профиля, стаж `met`, индикатор подтверждён.**
   - Ожидание: `clarifications = []`, `model_calls = 0`.
   - `core` совпадает с первым кандидатом побайтно; на профиле с ядром проверяется на Python v5 или консультанте v4.
3. **Ответ и повтор.**
   - Ответ записывается под вопросом 1.
   - Повтор запроса с тем же `request_id` даёт ту же запись.
   - Вопрос чужого отклика — `404`.
   - Параллельная правка той же ревизии — `409`.
4. **Документальное требование** (образование `is_preliminary`).
   - До звонка — в `document_requests`.
   - После устного ответа — всё ещё там.
   - После `confirm` с `basis = documents` — новая версия оценки, `is_preliminary = false`; ответ и прежняя версия читаемы.
5. **Сбой модели.** При `503` прежний гайд с ответами возвращается по `GET`.

## 7. Открытые вопросы

| Вопрос | Кто решает | Пока до решения |
|---|---|---|
| Ядро в телефонном звонке или только на собеседовании в департаменте (у консультанта 33 строки `interview`) | Маша и Давид с HR | `phone` показывает ядро свёрнутым блоком «для собеседования» |
| Кто утверждает рубрику ядра | Давид, HR | `draft` с пометкой на экране |
| Бюджет уточнений | HR (звонок 15–40 мин) | 6 |
| Объединение индикаторов одной компетенции в один вопрос | Илья по живому прогону | объединяем |
