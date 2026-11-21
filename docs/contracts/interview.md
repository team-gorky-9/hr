# Контракт гайда интервью и ответов

**Версия:** v0.4 · **проект на согласовании; хранение, права и HTTP подтверждены Денисом** (Илья предлагает, Денис подтверждает хранение, права и HTTP; Давид — рубрику; Ася — DTO экрана). v0.2 — правки Дениса в §4–5: встреча и версия гайда разделены, базовая оценка для устаревания, матрица оснований `confirm`, `request_id` у подтверждения, права по ролям, коды ошибок по `api.md`, миграция 0006; пометка [Денис]. v0.3 — статус вопроса `answered` для строк, которые `confirm` не закрывает (Илья). v0.4 — Денис подтверждает хранение, права и HTTP (§4–5) с правками: миграция `0009` и БД v2.1 (номера `0006`–`0008` заняли backend-02, requirements-03 и workflow-01), роль `department` до workflow-01 получает 403, гонка создания встречи, ревизии перенесённого ответа, `ON DELETE NO ACTION` у `source_answer_id`, основание `resume` в матрице, чтение для сборки гайда может держать соединение на время вызова модели. Хранение и HTTP по §4–5 пишутся; рубрику (Давид) и DTO экрана (Ася) подтверждают они.
**Постановка:** `interview-01` в штабе (`hq/tasks/interview-01-ilya-denis-guide-and-answers.md`). **Опирается на:** [database.md](database.md) v2.0 (оценки, `competency_scores.details`, `confirm_formal_check`; v1.7 — §18, v1.8 — §19 backend-02), [assessment.md](assessment.md) v0.3, [api.md](api.md) v0.6.
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

Промпт и версия — `GUIDE_PROMPT_VERSION = "guide-v2"` (v2 — критерии описанием, а не репликой кандидата; не больше трёх навыков на вопрос). В журнал `llm_call` — без текста резюме.

## 4. HTTP

Общие соглашения — [api.md](api.md) §1: формат ошибки `{"error": {"code", "message", "details"}}`, коды ошибок в `UPPER_SNAKE_CASE`. Маршруты записи требуют заголовок `X-User-Login` (учебная авторизация `backend-02`): без него или с неизвестным логином — `401 USER_REQUIRED` / `UNKNOWN_USER`, роль без допуска — `403 FORBIDDEN_ROLE`. [Денис: согласовано с `app/api/auth.py` ветки `backend-02`]

**Кто что может** [Денис; формулировки допуска подтверждают Маша и Давид с HR]:

| Действие | `hr` | `admin` | `department` |
|---|---|---|---|
| сформировать / перечитать гайд | да | да | нет (403) |
| записать ответ, `kind=phone` | да | да | нет (403) |
| записать ответ, `kind=department` | да | да | нет (403) до workflow-01 |
| подтвердить требование | да | да | нет (так проверяет и `confirm_formal_check`) |

Роль `department` в v0.4 не получает доступа ни к одному маршруту гайда [Денис, v0.4]. Причина: область департамента (какие отклики переданы именно этому получателю) появляется только в workflow-01. Без неё `GET` по известному UUID отдал бы гайд и ответы по любому отклику, а постановка требует проверять область и при прямом обращении по ID. Так же поступает backend-02 (`app/api/auth.py`). Когда workflow-01 введёт назначение получателя, `department` получит `GET` гайда и запись ответов `kind=department` только по откликам, переданным ему; до этого ответы департамента вносит кадровик.

**Интервью и гайд — разные записи** [Денис]. `interviews` — это встреча (кто, когда, итог `result`), её считают отчёты о звонках. Гайд — набор вопросов к встрече, у одной встречи может быть несколько версий гайда. Если хранить версию гайда строкой `interviews`, каждое `regenerate` создавало бы ещё один «звонок» в отчётности, а `held_at` / `result` расходились бы по версиям. Поэтому:

- на пару (отклик, `kind`) открыта не больше чем одна встреча с `result = pending`; `POST` гайда находит её или создаёт. Создание идёт через `INSERT … ON CONFLICT DO NOTHING` по частичному UNIQUE с перечтением [Денис, v0.4]: два одновременных первых `POST` получают одну встречу, а не ошибку уникальности;
- версии гайда — строки `interview_guides` этой встречи (§5);
- после записи итога встречи (`result ≠ pending`) следующий `POST` открывает новую встречу.

### `POST /api/v1/applications/{application_id}/interview-guide`

Тело: `{"kind": "phone", "regenerate": false, "request_id": "<uuid>"}`.

- `kind`: `phone` | `department` [задача: «раздельные сессии нужны, если участники и время различаются»].
- Гайда у открытой встречи ещё нет → создаётся версия 1: `201`.
- Гайд есть, `regenerate = false` → возвращается последняя версия без вызова модели: `200`.
- `regenerate = true`:
  - основание не изменилось (та же базовая оценка, версия профиля и рубрики, см. «Устаревание») → возвращается текущая версия, `model_calls = 0`: `200`;
  - основание изменилось → новая версия `guide_version + 1`: `201`. Ответы не копируются: новый вопрос с тем же `gap_ref_id` или той же строкой ядра ссылается на прежний (`carried_from_question_id`) и показывает его последний ответ с `carried_over = true`.
- Повтор с тем же `request_id` возвращает результат первого запроса (тот же гайд и тот же статус). Тот же `request_id` с другим `application_id` или `kind` → `409 REQUEST_ID_REUSED`.
- Два параллельных `POST` с разными `request_id`: вторую вставку отклоняет `UNIQUE(interview_id, guide_version)`, сервер перечитывает и возвращает гайд первого запроса (`200`). Вторая версия не появляется.
- **Транзакция и вызов модели** [Денис, v0.4]. Сборка пробелов и вызов модели (`build_guide`) идут в сессии **только для чтения**: она ничего не пишет и не берёт блокировок. Затем отдельная короткая транзакция записи: проверить, что текущая оценка пары и рубрика те же, что при сборке, и записать гайд. Если за время вызова оценка сменилась → `409 ASSESSMENT_CHANGED`, клиент повторяет запрос. Так гайд не записывается по устаревшей оценке, а блокировки записи не держатся на время ответа модели.
  - **Допущение.** Сессия чтения держит соединение пула открытым (idle in transaction) всё время вызова модели, до десятков секунд. Для стенда с несколькими кадровиками это допустимо. Цена: каждая одновременная генерация занимает одно соединение пула, и снимок данных не даёт VACUUM чистить строки, пока идёт вызов. Если генераций станет больше, чем соединений в пуле, `build_guide` делится на чтение в обычные данные и генерацию без сессии; контракт HTTP при этом не меняется.

Ответ — `InterviewGuideOut`.

### `GET /api/v1/applications/{application_id}/interview-guide?kind=phone[&guide_version=N]`

Без `guide_version` — последняя версия гайда последней встречи этого `kind`. Нет гайда → `404 GUIDE_NOT_FOUND`. Повторное чтение возвращает тот же набор и порядок вопросов. Чтение не вызывает модель и не пишет в БД.

### `InterviewGuideOut`

```json
{
  "interview_id": "uuid", "guide_id": "uuid", "application_id": "uuid", "kind": "phone", "guide_version": 1,
  "is_training": true,
  "assessment_id": "uuid", "assessment_version": 1, "current_assessment_id": "uuid",
  "profile_id": "uuid", "profile_version": 1,
  "rubric_status": "draft",
  "is_stale": false, "stale_reason": null,
  "prompt_version": "guide-v1", "model_calls": 1, "created_at": "2026-11-20T15:00:00+03:00",
  "created_by": {"user_id": "uuid", "login": "hr_demo"},
  "core": [ "InterviewQuestionOut" ],
  "clarifications": [ "InterviewQuestionOut" ],
  "document_requests": [ {"requirement_id": "uuid", "requirement_key": "py.education", "title": "Диплом о высшем образовании", "reason": "по резюме: Высшее, Прикладная информатика; подтверждается документом"} ],
  "uncovered_gaps": [ {"gap_ref_id": "gap:…", "title": "…", "reason": "over_budget"} ]
}
```

**Что снимок, а что считается при чтении** [Денис]:

- снимок версии гайда: `core`, `clarifications` (текст, критерий, `sources`), `uncovered_gaps`, `assessment_id` — оценка, по которой собраны пробелы;
- считается при каждом `GET` по **текущей** оценке пары: `current_assessment_id`, `is_stale` / `stale_reason`, `document_requests`, `status` вопросов (ниже). Поэтому после подтверждения требования гайд не надо перегенерировать: вопрос показывает, что требование закрыто.

**Устаревание.** `confirm_formal_check` тоже создаёт новую версию оценки. Если считать любую новую версию «оценка изменилась», гайд устаревал бы после каждого подтверждения из самого гайда. Поэтому сравнивается **базовая** оценка — последняя версия, записанная `save_assessment` (вывод модели по резюме); версии из `confirm_formal_check` ссылаются на неё (`assessments.base_assessment_id`, §5).

`stale_reason`:
- `assessment_changed` — у пары новая базовая оценка (переоценка резюме);
- `assessment_stale` — сама текущая оценка устарела по правилам [api.md](api.md) (`stale_reason` оценки: текст, профиль, `algorithm_changed`);
- `profile_changed` — у вакансии утверждена другая версия профиля;
- `rubric_changed` — после создания гайда утверждена или изменена рубрика ядра.

Устаревший гайд читается по своей версии, ответы в нём не теряются. Писать ответы можно только в последнюю версию гайда (см. ниже).

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
  "status": "open",
  "resolved_by": null,
  "carried_from_question_id": null,
  "answer": null
}
```

- `status` [Денис; `answered` — Илья, v0.3]: считается при чтении.
  - `open` — ответа нет, требования из `sources` в текущей оценке всё ещё `unknown` или без свидетельства;
  - `answered` — есть ответ, но подтверждения нет или для строки оно не предусмотрено. `confirm_formal_check` работает только для формальных требований, поэтому уточнения по индикаторам компетенций и вопросы ядра по строкам матрицы после ответа остаются в этом статусе;
  - `resolved` — по всем формальным требованиям из `sources` есть результат с `basis ≠ resume`; тогда `resolved_by = {"assessment_id", "assessment_version", "requirement_id", "result", "basis", "confirmed_by": {"user_id", "login"}}`.
  - Статус не меняет оценку: итог меняет только `confirm`. Для вопроса ядра статус считается по той же строке профиля.
- `answer` — последняя ревизия: `AnswerOut` (ниже) или `null`; у перенесённого ответа дополнительно `carried_over: true`.
- У вопроса ядра `kind = "core"`, `gap_ref_id = null`, в `sources` — строка профиля (`type = "profile_row"`, `key`, `requirement_id` или `indicator_key`, `competency_id`) и `rubric_question_id`.

### `POST /api/v1/interviews/{interview_id}/questions/{question_id}/answers`

Тело: `{"text": "С 03.2023 по 12.2024 по договору, писал API-тесты", "source": "phone", "expected_revision": 0, "request_id": "<uuid>"}`.

- `source`: `phone` | `in_person` | `written`. Значение `unknown` — только у ответов, перенесённых миграцией из `answer_notes`; через API его не передают.
- `text`: непустой, не длиннее 4000 символов. В текст не пишут номера документов и контакты — это ПДн; сводка руководителю показывает ответы только после той же очистки, что и резюме [Денис, предл.].
- `expected_revision` — номер последней ревизии, которую видел клиент; `0`, если ответа ещё нет. Ревизии нумеруются с 1.
- Ответ `201` — `AnswerOut`: `{answer_id, question_id, revision, text, source, author: {user_id, login}, created_at, previous_answer_id}`. `previous_answer_id` — ревизия, которую исправили (`null` у первой); это та же цепочка, что и `revision`, оставлена для удобства чтения истории.
- `GET /api/v1/interviews/{interview_id}/questions/{question_id}/answers` — все ревизии по возрастанию [Денис: история нужна экрану и сводке, в гайде только последняя].
- Исправление создаёт новую ревизию, предыдущая читается.
- **Перенесённый ответ** [Денис, v0.4]. Ревизии считаются по вопросу. У нового вопроса после `regenerate` своих ревизий нет, даже если он показывает ответ прежнего вопроса с `carried_over = true`. Поэтому клиент передаёт `expected_revision = 0`. Первая ревизия нового вопроса получает `revision = 1` и `previous_answer_id` = последняя ревизия вопроса из `carried_from_question_id`. Цепочка `previous_answer_id` в этом месте переходит к прежнему вопросу, а `revision` начинается заново. `GET …/answers` нового вопроса возвращает только его ревизии; историю до переноса клиент читает по `carried_from_question_id`.
- Повтор с тем же `request_id` возвращает ту же запись (`201` → повтор `200`), второй строки нет. Тот же `request_id` с другим текстом или вопросом → `409 REQUEST_ID_REUSED`.

Ошибки:
- `409 REVISION_CONFLICT` — `expected_revision` не текущая; `details: {"current_revision": N, "current_answer_id": "uuid"}`, клиент перечитывает и показывает принятый ответ с автором;
- `409 GUIDE_SUPERSEDED` — вопрос из не последней версии гайда; `details: {"guide_version": N}`;
- `404 QUESTION_NOT_FOUND` — вопрос не из этого интервью, сюда же подстановка вопроса чужого отклика;
- `403 FORBIDDEN_ROLE` — роль без допуска к этому `kind` (таблица выше).

Проверки прав и принадлежности выполняются до записи; при отказе строк не появляется.

### `POST /api/v1/assessments/{assessment_id}/formal-checks/{requirement_id}/confirm`

Тело: `{"result": "met", "basis": "documents", "comment": "Диплом 2015 г. проверен", "answer_id": "uuid|null", "request_id": "<uuid>"}`.

- Вызывает `confirm_formal_check`; ответ `201` — новая версия оценки в формате `AssessmentOut` ([api.md](api.md)).
- `assessment_id` служит и оптимистической блокировкой: подтверждать можно только текущую версию, иначе `409 ASSESSMENT_NOT_CURRENT` с `details.current_assessment_id`. Два кадровика, подтверждающие одновременно, не перезапишут друг друга молча.
- `request_id` [Денис]: без него двойное нажатие создаёт две версии оценки. Повтор возвращает ту же версию (`200`). Хранится в `assessments.confirm_request_id` (§5) [Денис, v0.4]. Тот же `request_id` с другой оценкой, требованием или результатом → `409 REQUEST_ID_REUSED`.
- `comment` обязателен и непуст (так проверяет функция).
- **Допустимое основание** зависит от `verification` требования. Предложение Ильи («`interview` только при `verification = interview`») не закрывает контрольный пример: в `python-dev.v5` и учебном профиле стаж — `verification = resume`, `check_stage = screening`, и ответ на уточняющий вопрос про стаж нельзя было бы внести вообще, а `documents` дал бы `is_preliminary = true`. Вместо этого [Денис, предл.; итоговую матрицу подтверждают Маша и Давид с HR, задача п. «Предметное согласование»]:

  | `verification` требования | Допустимый `basis` в `confirm` | `is_preliminary` после подтверждения |
  |---|---|---|
  | `resume` (только `screening`) | `interview`, `documents` (`resume` пишет только `save_assessment`) | `false` |
  | `documents` (только `screening`) | `documents` | `false` |
  | `interview` (только `interview`) | `interview` | `false` |
  | `test` | `test` | `false` |

  Иное основание → `409 BASIS_NOT_ALLOWED`, `details: {"verification", "allowed_bases"}`. Устный ответ по документальному требованию поэтому не подтверждает его: требование остаётся `is_preliminary`, элемент `document_requests` виден [задача, п. 4].
  Для этого меняются две функции продукта (часть Дениса): `confirm_formal_check` проверяет матрицу; `is_preliminary` считает предварительным результат, основание которого не входит в допустимые для `verification` (сейчас `basis ≠ verification`, и `interview` по требованию `resume` стал бы «предварительным»).
  - Обе берут допустимые основания из одной функции `allowed_bases(verification)` [Денис, v0.4]. Для `is_preliminary` к ним добавляется основание `resume` у требования `verification = resume`: вывод модели по резюме там — штатный способ проверки, а не предварительный. Остальные строки матрицы на путь `save_assessment` не влияют: его основание всегда `resume`, и по требованиям `documents`, `interview`, `test` результат «по резюме» остаётся предварительным, как сейчас.
  - Уже сохранённые строки `formal_checks` не пересчитываются. Строка, где кадровик до v0.4 подтвердил требование `verification = resume` основанием `interview`, остаётся с `is_preliminary = true` до следующего подтверждения. Новая версия оценки пересчитывает признак по новой функции.
- `answer_id`:
  - при `basis = interview` обязателен, при других основаниях необязателен;
  - ответ должен принадлежать вопросу отклика того же кандидата, а в `sources` этого вопроса должно быть это требование; иначе `409 ANSWER_NOT_FOR_REQUIREMENT`;
  - сохраняется в строке требования новой версии (`formal_checks.source_answer_id`, §5), поэтому сводка показывает, на какой ответ опирался кадровик.
- Этап отклика не меняется.

### Ошибки формирования гайда

| Код | Когда | Кадровик видит |
|---|---|---|
| `409 ASSESSMENT_REQUIRED` | у отклика нет текущей оценки | «Сначала оцените отклик» |
| `409 NOT_APPLICABLE` / `MAPPING_REQUIRED` | отклик не к этому профилю (`profile-applicability.md`) | статус применимости, гайда нет |
| `409 ASSESSMENT_STALE` | оценка устарела (`api.md`, `stale_reason`) | «Переоценить» |
| `409 NO_APPROVED_PROFILE` | у вакансии нет утверждённого профиля нужного контура | «Нет утверждённого профиля» |
| `409 ASSESSMENT_CHANGED` | оценка сменилась, пока шёл вызов модели | повторить запрос |
| `503 LLM_UNAVAILABLE` | модель недоступна, а она нужна (есть пробелы или нет рубрики ядра) | ранее сохранённый гайд с ответами остаётся доступен по `GET`; новый не создан |

### Итог телефонной встречи (wave-2, миграция 0010)

Операции заданы [wave-2-stage-1](wave-2-stage-1.md), раздел «Илья». Реализация — `app/api/interview.py` (`list_interviews`, `record_outcome`), итог — [docs/reports/wave-2-interview-outcome.md](../reports/wave-2-interview-outcome.md). Права прежние: `X-User-Login`, кадровик или администратор (`department` — 403).

- `GET /api/v1/applications/{application_id}/interviews` → `{application_id, items: [Interview]}`. Встречи отклика в порядке создания. Этот маршрут интерфейс читает для факта проведения. `Interview` = `{id, application_id, kind, scheduled_at, held_at, attempt_at, result, summary, interviewer_user_id, outcome_recorded_at, revision}`.
- `POST /api/v1/interviews/{interview_id}/outcome` с телом `{expected_revision, result: continue|stop|no_answer, occurred_at, summary}` → `200 Interview`.
  - Только `kind = phone` в состоянии `pending`.
  - `continue`/`stop`: `held_at = attempt_at = occurred_at`.
  - `no_answer`: `attempt_at = occurred_at`, `held_at = null`.
  - `interviewer_user_id` — текущий пользователь, `outcome_recorded_at` — время сервера, `revision + 1`.
  - Этап отклика, отказ и резерв не меняются.
  - Повтор той же команды того же пользователя возвращает прежний результат.
- Ошибки:
  - `409 INTERVIEW_ALREADY_COMPLETED` — иной итог завершённой встречи;
  - `409 STALE_REVISION` — устаревшая `expected_revision`;
  - `409 UNSUPPORTED_INTERVIEW_KIND` — встреча не телефонная;
  - `404 INTERVIEW_NOT_FOUND` — встречи нет;
  - `422` — неверный вход: время без зоны или в будущем (`INVALID_OCCURRED_AT`), пустое пояснение, лишнее поле.
- Генерация гайда после завершённой встречи открывает следующую `pending` штатным путём (`open_interview`). Гайд и ответы прошлой встречи остаются доступны по её `interview_id`.

## 5. Хранение — миграция 0009 (часть Дениса)

База — [database.md](database.md) v2.0 на `main`: миграции `0007_posting_sources` (v1.9, requirements-03) и `0008` (v2.0, workflow-01). Миграция гайда — `0009` с `down_revision = '0008'`, описание — database.md v2.1, раздел 22 [Денис, v0.4; в v0.2–v0.3 здесь стоял номер `0006`, затем `0007`; номера заняли backend-02, requirements-03 и workflow-01].

Сейчас есть `interviews` (встреча) и `interview_questions` (`interview_id`, `competency_id`, `gap`, `question`, `author`, `answer_notes`, `score`, `sort_order`). Изменения [Денис, предл.]:

| Таблица | Изменение |
|---|---|
| `interview_guides` (новая) | `id`, `interview_id` FK, `guide_version`, `assessment_id` FK ON DELETE CASCADE (базовая оценка сборки), `profile_id` FK ON DELETE CASCADE [Денис, v0.4: без CASCADE удаление кандидата падало — ссылка из гайда на оценку проверялась раньше, чем каскад от отклика доходил до гайда], `rubric_version`, `prompt_version`, `model_calls`, `uncovered_gaps` jsonb, `request_id` UNIQUE, `is_migrated`, `created_by_user_id`, `created_at`; UNIQUE(`interview_id`, `guide_version`); CHECK: `assessment_id IS NULL` только при `is_migrated` |
| `interviews` | частичный UNIQUE(`application_id`, `kind`) WHERE `result = 'pending'` — одна открытая встреча на тип |
| `interview_questions` | `guide_id` FK (NOT NULL после переноса), `kind` (`core` / `clarification`), `gap_ref_id`, `sources` jsonb, `criterion` jsonb, `requirement_id` FK null, `indicator_key` null, `rubric_question_id` FK null, `carried_from_question_id` FK null; UNIQUE(`guide_id`, `gap_ref_id`) WHERE `gap_ref_id IS NOT NULL`; CHECK: `kind = 'core'` ⇔ `rubric_question_id IS NOT NULL` и `gap_ref_id IS NULL`. `interview_id` остаётся для обратной совместимости и маршрута ответа. `gap` хранит заголовок пробела |
| `interview_answers` (новая) | `id`, `question_id` FK, `revision` (≥ 1), `text`, `source` (`phone` / `in_person` / `written` / `unknown`), `author_user_id` FK null, `previous_answer_id` FK null, `request_id` UNIQUE null, `created_at`; UNIQUE(`question_id`, `revision`); CHECK: `author_user_id IS NULL` и `request_id IS NULL` только при `source = 'unknown'`. Строки только добавляются |
| `interview_rubric_questions` (новая) | `id`, `profile_id` FK, `row_key`, `requirement_id` FK null, `indicator_key` null (ровно одно из двух), `question`, `criterion` jsonb, `author`, `status` (`draft` / `approved`), `version`, `approved_by_user_id` null, `approved_at` null; UNIQUE(`profile_id`, `row_key`). Первую генерацию ядра двумя запросами одновременно разрешает `INSERT … ON CONFLICT DO NOTHING` с перечтением. Маршрут утверждения рубрики в этот контракт не входит: до решения §7 — скрипт, как утверждение профиля |
| `assessments` | `base_assessment_id` FK null: `null` у версии из `save_assessment`; у версии из `confirm_formal_check` — базовая версия, от которой она произошла (копируется по цепочке). `confirm_request_id` uuid UNIQUE null — `request_id` подтверждения, создавшего эту версию [Денис, v0.4]; CHECK: не `null` только вместе с `base_assessment_id` |
| `formal_checks` | `source_answer_id` FK `interview_answers` null, ON DELETE NO ACTION; CHECK: не `null` только при `basis <> 'resume'`; при копировании строк в новую версию копируется |
| запросы документов | не храним: вычисляются из текущей оценки при чтении |

**Почему `NO ACTION`, а не `RESTRICT`** [Денис, v0.4]. Ответы удаляются каскадом от отклика (`applications` → `interviews` → `interview_questions` → `interview_answers`), строки оценки — каскадом от кандидата (`assessments` → `formal_checks`). При удалении кандидата целиком PostgreSQL удаляет обе ветки одним оператором. `RESTRICT` проверяется сразу и может отклонить удаление ответа, если строка оценки со ссылкой на него ещё не удалена. `NO ACTION` проверяется в конце оператора, когда обе ветки уже удалены. Удаление одного отклика или ответа, на который ссылается подтверждение, по-прежнему отклоняется.

**Перенос старых данных** (в той же миграции):
- для каждой существующей `interviews` создаётся `interview_guides` версии 1 без оценки (`is_migrated = true`, `assessment_id = null`), вопросы привязываются к ней с `kind = clarification`;
- непустой `answer_notes` переносится в `interview_answers` ревизией 1 с `source = unknown`, `author_user_id = null`; экран показывает «происхождение неизвестно» [задача]. Ответ получает `answer_id`, поэтому на него можно сослаться в `confirm`. Колонка `answer_notes` после переноса не пишется и удаляется в следующей версии;
- `score` в контракт не входит: колонка остаётся, API её не возвращает, судьба решается со сводкой руководителю.

**Функции `app/db/repository.py`** (сигнатуры — database.md v2.1, раздел 22): `create_interview_guide(...)`, `get_interview_guide(...)`, `add_interview_answer(..., expected_revision, request_id)`, `confirm_formal_check(..., answer_id=None)` с матрицей оснований из §4, `is_preliminary(...)` по той же матрице.

## 6. Контрольный пример (критерии приёмки `interview-01`)

1. **`py-9001`, учебный профиль.** Стаж `unknown`, в карточке `missing: ["длительность коммерческого опыта"]`, индикатор API-тестов подтверждён.
   - Ожидание: `clarifications` — **один** вопрос про сроки и характер работы, оба источника в `sources`; `uncovered_gaps = []`, `document_requests = []`, `model_calls = 1`.
   - У учебного профиля нет строк `interview`, поэтому `core = []`.
   - После ответа «с 03.2023 по 12.2024 по договору» кадровик подтверждает стаж: `confirm` с `basis = interview` и `answer_id` → новая версия оценки, стаж `met`, `is_preliminary = false`. `GET` гайда: `is_stale = false`, вопрос `status = resolved`, `resolved_by.basis = interview`.
2. **Второй кандидат того же профиля, стаж `met`, индикатор подтверждён.**
   - Ожидание: `clarifications = []`, `model_calls = 0`.
   - `core` совпадает с первым кандидатом побайтно; на профиле с ядром проверяется на Python v5 или консультанте v4.
3. **Ответ и повтор.**
   - Ответ записывается под вопросом 1.
   - Повтор запроса с тем же `request_id` даёт ту же запись.
   - Вопрос чужого отклика — `404 QUESTION_NOT_FOUND`; роль `department` по `kind = phone` — `403 FORBIDDEN_ROLE`; в обоих случаях строк не добавилось.
   - Параллельная правка той же ревизии — `409 REVISION_CONFLICT`, сохранён первый ответ с его автором.
   - Ответ в версию гайда, вытесненную `regenerate`, — `409 GUIDE_SUPERSEDED`.
4. **Документальное требование** (образование `is_preliminary`).
   - До звонка — в `document_requests`.
   - После устного ответа — всё ещё там; `confirm` с `basis = interview` — `409 BASIS_NOT_ALLOWED`.
   - После `confirm` с `basis = documents` — новая версия оценки, `is_preliminary = false`; ответ и прежняя версия читаемы.
5. **Сбой модели.** При `503` прежний гайд с ответами возвращается по `GET`.

## 7. Открытые вопросы

| Вопрос | Кто решает | Пока до решения |
|---|---|---|
| Ядро в телефонном звонке или только на собеседовании в департаменте (у консультанта 33 строки `interview`) | Маша и Давид с HR | `phone` показывает ядро свёрнутым блоком «для собеседования» |
| Кто утверждает рубрику ядра | Давид, HR | `draft` с пометкой на экране |
| Бюджет уточнений | HR (звонок 15–40 мин) | 6 |
| Объединение индикаторов одной компетенции в один вопрос | Илья по живому прогону | объединяем |
| Матрица допустимых оснований `confirm` (§4), в частности принимает ли HR устный ответ по требованию `verification = resume` | Маша и Давид с HR | предложение Дениса из §4 |
| Пишет ли департамент ответы в `kind = department` сам или через кадровика | Маша с HR | до workflow-01 вносит кадровик, роль `department` получает 403 (§4) |
