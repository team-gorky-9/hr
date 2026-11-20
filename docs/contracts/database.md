# Контракт: база данных

**Дополнение v1.9 (interview-01):** миграция `0007`, раздел 20 — версии гайда интервью, ревизии ответов, рубрика ядра, базовая оценка и ответ в подтверждении требования. Ждёт утверждения.

**Дополнение v1.8 (backend-02):** миграция `0006`, раздел 19 — периоды кадрового резерва, одна действующая запись на цель, статус `expired`. Ждёт утверждения.

**Интеграционное дополнение v1.7:** ветка `feature/profile-assessment-integration`, миграция `0005`, раздел 18. Реализацию по архитектурному плану разрешил Давид; исторические статусы утверждения версий ниже не переписываются и согласие коллег не подразумевается.

**Версия:** 1.6 (проект) · **Дата:** 2026-11-20 · **Статус:** v1.0 утверждена Родионом 19.11.2026; v1.1 принята решением Родиона 20.11 (Р1); изменения v1.2 (раздел 13), v1.3 (раздел 14), v1.4 (раздел 15), v1.5 (раздел 16) и v1.6 (раздел 17) ждут утверждения
**Автор:** Денис (бэкенд и база) · **Реализация:** v1.0 — team-gorky-9/hr#1, миграция `0001`; v1.1 — team-gorky-9/hr#4, миграция `0002`; v1.2 — team-gorky-9/hr#5, без миграции; v1.3 — team-gorky-9/hr#6, без миграции; v1.4 — team-gorky-9/hr#8, без миграции; v1.5 — ветка `feature/profile-contours-and-basis`, миграция `0003`; v1.6 — ветка `feature/ingest-02-full-corpus-and-pii-audit`, миграция `0004`

Контракт описывает, как платформа хранит данные и как другие модули их пишут и читают. По правилам команды схема базы входит в контракт и меняется только по согласованию с Родионом. Версия 1.0 утверждена, модули опираются на неё; v1.1 принята, правки v1.2–v1.5 ждут утверждения. Каждая правка вносится этим же файлом вместе с кодом, тестами и, если меняется схема, миграцией (раздел 9).

**Происхождение пунктов:** **[Д]** — решение Дениса (обсуждение 19.11); **[Ч]** — из черновика контракта в `docs/project-context.md` штаба; **[А]** — предложение агента, выбор делегирован Денисом. Пометка стоит у решений, а не у очевидных полей.

## 1. Кто пользуется

| Модуль | Пишет | Читает |
|---|---|---|
| Импорт | `source_documents`, `candidates`, `candidate_pii`, `candidate_texts`, `applications` | справочники, `positions`, `vacancies` |
| Извлечение карточки, скоринг (Илья) | `candidate_cards`, `candidate_skills`, `assessments`, `formal_checks`, `competency_scores`, `interview_questions` | `candidate_texts`, требования должности — действующий профиль через `get_approved_profile` [v1.5] |
| Матрицы компетенций (Давид) | `requirement_profiles`, `requirement_profile_sources`, `formal_requirements`, `competencies`, `competency_indicators` — через `create_requirement_profile` | `positions`, `source_documents` (ДИ, матрица, вакансия) |
| Поиск (Родион) | `embeddings` | `candidate_texts`, `candidate_cards`, `candidate_skills`, `reserve_entries` |
| API и интерфейс (Ася, Денис) | `stage_events`, `interviews`, `department_feedback`, `reserve_entries`, `users`, `audit_log`, утверждение требований (`approve_requirement_profile`), подтверждение требования документом, интервью или тестом (`confirm_formal_check`) [v1.5] | всё, ПДн — только через `get_candidate_pii`; действующий профиль — через `get_approved_profile` [v1.5] |

Модули пишут в базу через функции доступа (раздел 7), а не прямыми `INSERT`: функции держат правила раздела 2. Читать таблицы напрямую можно, правила чтения ПДн — в п. 2.2.

**Таблицы без функции записи [v1.3].** Для части записей из таблицы выше функции пока нет:

| Что записать | Чья задача добавит функцию |
|---|---|
| `interviews` (назначить, внести итог), `interview_questions` | первая задача, где интервью появляются в интерфейсе или их генерирует модель (Ася, Илья) |
| `users` (завести, отключить) | задача авторизации (Ася) |
| `embeddings` | задача поиска (Родион), вместе с выбором модели и индекса (п. 11.4) |
| смена `reserve_entries.status` (`withdrawn`, `hired`) | первая задача, где резервом управляют из интерфейса (Ася) |
| `positions`, `vacancies` (новая должность, закрытие вакансии) | сейчас пишет только `python -m app.db.seed`; функция — когда должности заводят из интерфейса |

Пока функции нет, модуль в эту таблицу не пишет. Функцию добавляет потребитель вместе с задачей, где запись нужна, по правилам раздела 9 (контракт, код и тест в одном PR, утверждает Родион). Обходной `INSERT` из модуля не допускается.

## 2. Обязательные правила

**2.1. Три слоя данных о кандидате [Д].** `source_documents.raw_text` — исходный файл, после импорта не меняется. `candidate_texts.text` — текст, из которого вычищены ПДн по п. 11.7; город и гражданство в нём остаются (п. 11.8). `candidate_cards.card` — карточка, извлечённая из очищенного текста.

**2.2. Персональные данные отдельно [Д].** ФИО, пол, дата рождения, возраст, контакты и ссылки на профили лежат только в `candidate_pii`. Город и гражданство тоже персональные данные, но из текста не вычищаются и остаются в `candidate_texts.text` (п. 11.8). Есть одно исключение: `raw_text`, исходник хранится как есть. Чтение `candidate_pii` идёт только через `get_candidate_pii`, который пишет запись `view_pii` в `audit_log` с целью. `raw_text` в модель и в интерфейс не передаётся.

**2.3. Модель видит только очищенный текст [Д][Ч].** В вызовы модели уходит `candidate_texts.text` текущей версии, а не `raw_text` и не `candidate_pii`.

**2.4. Доказательства проверяемы [Д][Ч].** У каждого вывода оценки есть доказательство `Evidence` (п. 3.2): дословная цитата, `id` текста и позиция в нём. `save_assessment` отклоняет цитату, если `text[start:end] != quote` или текст принадлежит другому кандидату.

**2.5. Версии результатов ИИ хранятся [Д].** Для `candidate_texts`, `candidate_cards` и `assessments` новая запись получает `version = max + 1` и `is_current = true`, а предыдущая — `is_current = false`. Текущая версия всегда одна: частичный уникальный индекс `... WHERE is_current`. Удалять старые версии нельзя.

**2.6. Формальные требования отдельно от компетенций [Д][Ч].** Образование, направление подготовки и стаж проверяются в `formal_checks` и не «добираются» баллами компетенций. Итог `assessments.formal_result` считает код, а не модель, по обязательным требованиям (`is_mandatory`):
- хотя бы одно `not_met` → `not_met`;
- иначе хотя бы одно `unknown` или не проверенное → `unknown`;
- иначе → `met`.

`unknown` означает «в резюме нет сведений». Это повод уточнить на интервью, а не отказать.

**В итог входят только требования этапа `screening` [v1.5].** Обязательное требование с `check_stage = interview` (знание закона) по резюме не проверяется и итог не делает `unknown`.

В одной оценке каждое требование и каждая компетенция встречаются не больше одного раза: повтор `save_assessment` отклоняет [v1.3].

**План и факт проверки разделены [Родион, Р4; v1.5; заменяет правило v1.3 «met → unknown»].** `verification` требования — где его *положено* подтверждать (резюме, документы, интервью, тест). `formal_checks.basis` — на чём результат *фактически* основан. Модель видит только резюме, поэтому `save_assessment` пишет `basis = resume` и сохраняет результат как есть. Результат **предварительный** (`formal_checks.is_preliminary`, считает код), если он не `unknown`, а `basis ≠ verification` — как в контракте оценки п. 4.4: «по резюме да, нужен документ» или «по резюме нет, сверить с документом». В итоге `formal_result` предварительный результат считается как обычный — на первичном отборе это и есть вывод по резюме. `assessments.formal_preliminary = true`, если итог `met`, а хоть одно обязательное требование этапа `screening` в нём предварительное: в списке это «допуск выполнен по резюме, нужен документ». Подтверждение документом, интервью или тестом вносит человек через `confirm_formal_check` — это новая версия оценки (п. 2.5), прежняя «по резюме» остаётся в истории. Пример: «Направление: юриспруденция» с `verification = documents`, в резюме «Юриспруденция» → `met`, `basis = resume`, предварительный, итог `met`; кадровик проверил диплом → версия 2, `met`, `basis = documents`; в дипломе другое направление → версия 2, `not_met`, итог `not_met`.

**2.6.1. Учебный и рабочий контуры [v1.5].** У кандидата и профиля есть признак `is_synthetic`: `false` — рабочий контур (реальные резюме, профили из ДИ), `true` — учебный (выдуманные тексты `py-9001`, учебное правило «стаж ≥ 24 мес.»). Признак ставится при создании и не меняется (триггер базы). Правила:
- **утверждение по контуру:** утверждённая версия — одна на должность в каждом контуре; утверждение архивирует прежнюю утверждённую только своего контура. Учебный профиль утверждается по тем же правилам, что рабочий (решение Родиона 20.11 — снять запрет);
- **нумерация по контуру:** версия уникальна в (`position_id`, `is_synthetic`, `version`): учебный `python-dev` v2 и рабочий v2 — разные профили;
- **выбор действующего профиля — только `get_approved_profile`:** по умолчанию рабочий, учебный — явным `synthetic=True`. Потребители не пишут свой `WHERE status = 'approved'`;
- **кого по чему оценивать — правило базы (`save_assessment`):** реального кандидата — только по утверждённому рабочему профилю; учебного — по любому не архивному профилю (так учебные случаи проверяют и правила реальных профилей);
- **учебная оценка** — у которой учебный кандидат или учебный профиль (`is_training_assessment`). Рабочая рекомендация — только реальный кандидат × рабочий профиль. Отдельного столбца нет: признак выводится из двух неизменяемых полей. Рабочие списки и поиск не показывают учебных кандидатов; учебные результаты показываются только с пометкой «учебный пример — не рабочая рекомендация».

**2.7. Решение принимает человек [Д][Ч].** Оценка ИИ не меняет этап отбора. Этап меняет только `move_application`, а в журнал пишется, кто это сделал. Обратная связь департамента (`record_department_feedback`) этап тоже не меняет.

**Перескок этапа подтверждает человек [Д, v1.3].** Обычный шаг: на следующий этап по `sort_order`; в `rejected` или `withdrawn` — с любого этапа; в `hired` — только с последнего нефинального этапа (`documents`). Любой другой переход (перескок вперёд, возврат назад, `hired` раньше времени) выполняется только с `confirm_skip=True`, `actor_user_id` и непустым `comment` с причиной, иначе `StageTransitionError`. Подтверждение остаётся в `stage_events`: кто перевёл и почему. Причина отказа при `rejected` необязательна [Д, v1.3].

**2.8. Транзакции [А].** Функции доступа не делают `commit`. Транзакцией управляет вызывающий (скрипт импорта, обработчик запроса), поэтому несколько шагов сохраняются вместе или не сохраняются вовсе.

**2.9. Идентификаторы [Д].** Первичный ключ — UUID v4. Его ставит приложение, а при вставке через SQL — база (`gen_random_uuid()`). У кандидата есть читаемый `code`, уникальный, до 32 символов. Формат: `<префикс должности>-<номер отклика из 4 цифр>`, например `py-0005` (п. 11.2).

**2.10. Даты и время.** Момент времени — `timestamptz`, в JSON ISO 8601 со смещением: `2026-11-19T15:03:24+03:00`. Дата — `date`, `2026-08-25`. Даты периодов в карточке — строка той точности, что в резюме: `2019`, `2024-05` или `2024-05-17` [v1.4]. Такая дата означает диапазон дней (`2019` — с 1 января по 31 декабря), месяц и день не выдумываются.

**2.11. Позиции цитат — в символах [А].** `start`/`end` — индексы символов Unicode (кодовых точек), как срез строки Python `text[start:end]`, а не байты UTF-8. Кириллица лежит в BMP, поэтому индексы в JavaScript (UTF-16) совпадают, пока в тексте нет эмодзи и символов вне BMP.

**2.12. Перечисления хранятся строками [А]** с CHECK-ограничением в базе (значения — раздел 5). Справочники, которые пополняет кадровик (этапы, причины отказа), — это таблицы (раздел 6).

**2.13. Порядок журналов — по `seq` [А].** `stage_events.seq` и `audit_log.seq` растут монотонно. `created_at` равен времени начала транзакции и внутри одной транзакции совпадает, поэтому для сортировки не годится.

**2.14. Пути и имена файлов — в Unicode NFC [Ч].** Архив организаторов использует NFD (macOS): «й» записано как «и» и отдельный знак. `add_source_document` приводит путь к NFC сам.

## 3. Форматы JSON

Все объекты строгие: лишнее поле — ошибка проверки (Pydantic `extra="forbid"`), а не молча потерянные данные. Пробелы по краям строк обрезаются.

### 3.1. Карточка кандидата — `candidate_cards.card` [Ч, изменено — п. 10]

| Поле | Тип | Обязательно | Смысл |
|---|---|---|---|
| `headline` | строка \| null | нет | заголовок резюме |
| `applied_to` | список строк | нет, `[]` | должности, на которые откликнулся |
| `education` | список `Education` | нет, `[]` | образование, первым идёт основное |
| `courses` | список `Course` | нет, `[]` | повышение квалификации, переподготовка |
| `experience_years` | число \| null, 0–80 | нет | общий стаж в годах, как заявлен в резюме («Опыт работы: 13 лет 4 месяца» → 13.3); стаж по периодам считает `experience_bounds` (п. 3.1.1) |
| `experience` | список `Experience` | нет, `[]` | места работы |
| `skills` | список `Skill` | нет, `[]` | навыки |
| `languages` | список `Language` | нет, `[]` | языки |
| `about` | строка \| null | нет | раздел «Обо мне» |
| `cover_letter` | строка \| null | нет | сопроводительное письмо |
| `missing` | список строк | нет, `[]` | каких сведений не хватает для оценки |
| `pii_hidden` | bool | нет, `true` | ПДн из п. 11.7 убраны из карточки и текста; город и гражданство могут остаться (п. 11.8) |

- `Education`: `level` — словарь `высшее` | `неоконченное высшее` | `среднее профессиональное` | `среднее общее` или null [v1.4]; `level_raw` — формулировка уровня из резюме как написано [v1.4]; `degree` — ступень (`бакалавр`, `магистр`, `специалист`, `кандидат наук`); `status` — `completed` | `in_progress` | `incomplete` или null [v1.4]; `course` — курс 1–6 или null [v1.4]; `institution`, `faculty`, `field` (строки или null); `field_code` — код ОКСО `09.03.03` или null [v1.4]; `year` (целое 1950–2100 или null).
- `Course`: `title` (обязательно), `organization`, `year`; `kind` — `retraining` (переподготовка) | `qualification_upgrade` (повышение квалификации) | `other` или null; `field` — направление переподготовки; `completed` — bool или null; `hours` — число ≥ 0 или null, порог часов нормой не задан [все v1.4].
- `Experience`: `position`, `organization`, `start`, `end` (дата `YYYY`, `YYYY-MM` или `YYYY-MM-DD`, п. 2.10, или null), `is_current` (bool, по умолчанию false), `kind` — `work` | `internship` | `contract` | `project` или null [v1.4], `duties` (список строк). Правила: конец не раньше начала с учётом точности — ошибка, только если конец точно раньше (`2024-05` → `2024` допустимо, `2024-05` → `2023` нет); при `is_current = true` поле `end` пустое.

**Уровень образования не из словаря [Д, v1.4].** Не ошибка: это сведения о кандидате, а не сбой правила. Строка, которая не совпала со словарём (ответ модели или карточка до v1.4), нормализуется при чтении (`normalize_education_level`): `бакалавр`, `магистр`, `специалист`, `кандидат наук`, `Высшее образование (Бакалавр)` → `высшее`; `Неоконченное высшее…` → `неоконченное высшее`; `Среднее специальное…`, `колледж`, `техникум` → `среднее профессиональное`; `Среднее образование` → `среднее общее`. Нераспознанная → `level = null`. Исходная строка в обоих случаях сохраняется в `level_raw`. В оценке `level = null` — `unknown` с вопросом на интервью. Нормализация покрывает все 7 формулировок уровня из TXT-откликов архива «Кадры».

#### 3.1.1. Стаж по периодам — `experience_bounds` (`app/schemas/periods.py`) [v1.4]

Реализует правила контракта оценки (`docs/contracts/assessment.md`, п. 4.3). Месяцы считаются включительно, как на hh.ru: май 2024 — май 2025 = 13 мес. Пересекающиеся периоды сливаются. Текущее место работы считается до месяца `as_of`. Неполная дата даёт две границы: `lower` — самое позднее начало и самый ранний конец, `upper` — самое раннее начало и самый поздний конец. Период без начала или конца даёт `upper = None`, то есть верхней границы нет. Для общего стажа: `work` и `contract` идут в обе границы, `internship` и период без `kind` — только в `upper`, `project` не считается.

| Периоды | `lower` | `upper` | `estimate` | Порог 24 мес. |
|---|---|---|---|---|
| `2019` — `2021`, `work` | 14 | 36 | 25 | `unknown` |
| `2024-05` — `2025-05`, `work` | 13 | 13 | 13 | `not_met` |
| `2024-05-17` — `2025-05-03`, `work` | 13 | 13 | 13 | `not_met` |
| `2025-01` — `2025-12` + `2025-06` — сейчас (`as_of` = 2026-11) | 23 | 23 | 23 | `not_met` |

`verdict(min_months)`: `met` при `lower ≥ T`, `not_met` при `upper < T`, иначе `unknown`. `estimate = (lower + upper) / 2` нужен только для показа и сортировки. Решение по порогу принимается по границам, а не по `estimate`. День в дате принимается, но считается до месяца. Заявленный стаж (`experience_years`) и его сверку с периодами учитывает скоринг по контракту оценки.
- `Skill`, `Language`: `name` (непустая строка), `level` (строка или null).

### 3.2. Доказательство — `Evidence`

```json
{"candidate_text_id": "<uuid>", "quote": "<дословная цитата>", "start": 473, "end": 511}
```

Правила: `quote` непустая строка; `start >= 0`; `end - start == len(quote)`. `candidate_text_id` цитаты должен совпадать с текстом, из которого извлечена карточка оценки (`candidate_cards.candidate_text_id`), иначе `EvidenceError` [Д, v1.3]: карточка, цитаты и подсветка относятся к одной версии резюме. Если карточка извлечена из старой версии текста, цитаты берутся из неё же.

### 3.3. Персональные данные — `PiiData` (вход `create_candidate`)

`full_name`, `gender`, `phone`, `email`, `city`, `citizenship` — строки или null; `birth_date` — дата или null; `age` — целое 14–100 или null; `links` — список строк; `extra` — объект для прочего персонального (например, желаемая зарплата). `city` и `citizenship` необязательны: импорт их не заполняет, потому что город и гражданство остаются в очищенном тексте (п. 11.8). Поля сохранены, чтобы не менять схему.

### 3.4. Результат оценки (вход `save_assessment`)

- `FormalCheckIn`: `requirement_id` (uuid), `result` (`met` | `not_met` | `unknown`), `explanation` (строка или null), `evidence` (список `Evidence`), `alternatives` (список `AlternativeResultIn`, по умолчанию пустой) [v1.5]. Основания во входе нет: `save_assessment` всегда пишет `basis = resume`.
- `AlternativeResultIn` [v1.5]: `key` (ключ альтернативы из `params.alternatives`), `result`, `evidence`. Список либо пуст, либо содержит **все** альтернативы требования по одному разу. Итог строки им не противоречит: `met` — только если хоть одна альтернатива `met`; `not_met` — только если все `not_met`; `unknown` допустим всегда (направление проверяется только при подтверждённом уровне, `requires_requirement`, поэтому при найденном дипломе по направлению итог бывает `unknown`). Итог строки база не пересчитывает: зависимость между требованиями — правило оценщика (контракт оценки п. 4.2). Цитаты альтернатив проверяются так же, как цитаты строки.
- `CompetencyScoreIn`: `competency_id` (uuid), `level` (целое 0–100 или null, где null значит «нет сведений»), `explanation`, `evidence`.

### 3.5. Прочие JSONB-поля

| Поле | Формат |
|---|---|
| `formal_requirements.params` | правило в формате **params 0.1** (решение Родиона, Р1): формат пакета профилей stage-0b-01, схемы — `app/schemas/requirements.py` (п. 3.5.1). Проверяется при `create_requirement_profile` [v1.5] |
| `formal_checks.alternatives` [v1.5] | список `{key, result, evidence}` (п. 3.4) |
| `formal_checks.evidence`, `competency_scores.evidence` | список `Evidence` |
| `department_feedback.confirmed_competencies` | список кодов компетенций: `["ИТК", "РК"]` |
| `candidate_pii.links` | список строк; `candidate_pii.extra` — объект |
| `audit_log.details` | объект, для `view_pii` — `{"purpose": "<цель>"}` |

#### 3.5.1. `params` 0.1 [v1.5]

Общее: `schema_version = "0.1"` обязателен; лишний ключ, другая версия или неверная форма → ошибка проверки при создании профиля (до оценки). Внутри альтернативы условия соединяются AND, между альтернативами — OR. Ключи альтернатив уникальны в требовании.

| `kind` | Ключи |
|---|---|
| `education_level` | `alternatives[]` (≥ 1): `key`; `level` — значение словаря карточки v1.4 (`высшее`, `неоконченное высшее`, `среднее профессиональное`, `среднее общее`); `field_group` (`technical`), `field_examples[]`, `field_exclusions[]`; `enrollment_status` (`senior_student`). Нужен `level` или `enrollment_status` |
| `education_field` | `alternatives[]` (≥ 1): `key` + ровно одно из `degree_fields[]`, `retraining_fields[]`; `requires_requirement` — ключ требования `education_level` того же профиля (проверяет `create_requirement_profile`) |
| `experience` | `scope` (`total_commercial` \| `relevant_role`), `minimum_defined`; `min_months` > 0 — тогда и только тогда, когда `minimum_defined = true`; `relevance_hint` — обязателен для `relevant_role` |
| `knowledge`, `other` | правила нет: `{}` или `{"schema_version": "0.1"}`; проверяет человек |

Пример (Python, пакет v3): `{"schema_version": "0.1", "alternatives": [{"key": "py.education.alt1", "level": "высшее", "field_group": "technical", "field_examples": [], "field_exclusions": []}, {"key": "py.education.alt2", "enrollment_status": "senior_student"}]}`.

### 3.6. Профиль требований (вход `create_requirement_profile`) [v1.1]

Один формат для всех должностей: условия допуска + компетенции с индикаторами. Схемы — `app/schemas/requirements.py`.

- Ключ и происхождение строки (общие поля `FormalRequirementIn`, `CompetencyIn`, `IndicatorIn`): `key` — устойчивый ключ строки в пакете (до 64 символов без пробелов: `hr.education.level`, `py.di.P106`), уникален в профиле и не меняется между версиями; `origin` — `source` | `team`; `source_refs` — список `SourceRefIn`; `note`. Правило: при `source` нужна хотя бы одна ссылка; при `team` — обоснование в `note`.
- `SourceRefIn`: `source_document_id` (uuid, документ из `sources` профиля), `address` (до 256 символов: `п. 2.2.1`, `разд. 7, второй критерий; OOXML P201`, `ИТК, инд. 2`), `quote` (дословно). Строка может ссылаться на несколько документов: строка матрицы и пункт ДИ.
- `AcceptanceIn` (поле `acceptance` условия и индикатора): `met`, `not_met`, `unknown`, `limit` — строки или null: что считать выполнением, явным невыполнением, нехваткой сведений и чем ограничен вывод.
- `ProfileSourceIn`: `source_document_id`, `role` (`job_description` | `competency_matrix` | `vacancy_posting` | `regulation` | `other`), `observed_revision` (строка или null: `1.2 от 01.02.2024`), `is_primary` (bool).
- `FormalRequirementIn`: `kind`, `description`, `params` (п. 3.5.1; `{}` допустим только для `knowledge`, `other`), `is_mandatory` (по умолчанию true), `verification`, `check_stage` [v1.5], `acceptance`.
- `CompetencyIn`: `code` (до 32), `name`, `rank` (или null), `target_level_min`, `target_level_max` (оба null или оба 0–100, min ≤ max), `indicators` — не пустой список `IndicatorIn`.
- `IndicatorIn`: `text`, `is_mandatory` (по умолчанию true; false — «будет преимуществом»), `verification`, `check_stage` [v1.5], `acceptance`, `excluded_from_scoring` (по умолчанию false: строка хранится ради прослеживаемости, но в оценку не входит).

`verification` — где подтверждается требование: `resume`, `documents` (диплом, трудовая книжка), `interview` (личные качества, знание законов), `test` (практическое задание).

`check_stage` [v1.5] — на каком этапе отбора проверяется строка: `screening` (разбор резюме; входит в `formal_result` и счётчики) или `interview`. Без значения: `interview`/`test` → `interview`, `resume`/`documents` → `screening`. `screening` при `verification` = `interview` или `test` — ошибка (и CHECK базы).

## 4. Таблицы

`id` — UUID, первичный ключ. `created_at` — `timestamptz`, ставит база. «→» означает внешний ключ и поведение при удалении родителя.

**Удаление [v1.3].** Функций удаления нет, и в рабочей базе записи не удаляют: старые версии (п. 2.5) и журналы (`stage_events`, `audit_log`) хранятся всегда. Вместо удаления меняют статус: профиль → `archived`, вакансия → `closed`, запись резерва → `withdrawn`. Правила `CASCADE` в схеме нужны для очистки тестовой базы. В рабочей базе удаление родителя молча сотрёт историю: удаление профиля сотрёт его оценки, удаление вакансии — отклики вместе с журналом этапов. Особый случай — `reserve_entries.position_id` (SET NULL): у записи резерва без `competency_area` обнуление нарушает CHECK «должность или направление», поэтому удалить должность с таким резервом база не даст (`IntegrityError`, проверено тестом).

### 4.1. Источники

**`source_documents`** — исходный документ без изменений.
| Столбец | Тип | Null | Смысл |
|---|---|---|---|
| `kind` | перечисление `DocumentKind` | нет | резюме, ДИ, текст вакансии… |
| `channel` | `Channel` | нет | откуда пришёл |
| `file_format` | `FileFormat` | нет | формат файла |
| `original_path` | text | нет | путь в архиве, NFC: `Python-разработчик/отклик 5.txt` |
| `file_name` | varchar(512) | нет | имя файла |
| `sha256` | varchar(64), **unique** | нет | хеш содержимого, защита от повторного импорта |
| `raw_text` | text | нет | текст как есть, содержит ПДн |
| `import_batch` | varchar(64), индекс | да | метка запуска импорта |
| `imported_at` | timestamptz | нет | |

### 4.2. Кандидат

**`candidates`** — одно резюме — одна запись [Д]. Склейка дублей одного человека — позже, отдельной таблицей.
| Столбец | Тип | Null | Смысл |
|---|---|---|---|
| `code` | varchar(32), **unique** | нет | читаемый код (п. 2.9) |
| `source_document_id` | → `source_documents` (RESTRICT), **unique** | нет | резюме |
| `headline` | varchar(512) | да | заголовок резюме |
| `is_synthetic` [v1.5] | bool, по умолчанию false | нет | учебный кандидат (п. 2.6.1); не меняется (триггер) |
| `created_at`, `updated_at` | timestamptz | нет | |

**`candidate_pii`** — ПДн, первичный ключ `candidate_id` → `candidates` (CASCADE). Столбцы по п. 3.3: `full_name` varchar(512), `gender` varchar(16), `birth_date` date, `age` smallint, `phone` varchar(64), `email` varchar(256), `city`, `citizenship` varchar(256) — все nullable; `links` jsonb `[]`, `extra` jsonb `{}`.

**`candidate_texts`** — очищенный текст, версии.
| Столбец | Тип | Null | Смысл |
|---|---|---|---|
| `candidate_id` | → `candidates` (CASCADE) | нет | |
| `version` | integer | нет | unique вместе с `candidate_id` |
| `is_current` | bool | нет | одна текущая на кандидата |
| `redaction_method` | varchar(128) | нет | чем очищали: имя и версия функции |
| `text` | text | нет | текст для модели и цитат |

**`candidate_cards`** — карточка, версии.
| Столбец | Тип | Null | Смысл |
|---|---|---|---|
| `candidate_id` | → `candidates` (CASCADE) | нет | |
| `candidate_text_id` | → `candidate_texts` (CASCADE) | нет | из какого текста извлечена |
| `version`, `is_current` | integer, bool | нет | как в п. 2.5 |
| `extractor` | varchar(128) | нет | `yandexgpt-lite/latest`, `parser-hh-txt v1`, `manual` |
| `prompt_version` | varchar(64) | да | |
| `card` | jsonb | нет | `CandidateCard` (п. 3.1) |
| `experience_years` | numeric(4,1) | да | копия из карточки для фильтров |
| `education_level` | varchar(64) | да | `education[0].level`: значение словаря (п. 3.1) или null. Копия для фильтров без разбора JSONB; пишет только `add_candidate_card`, карточка после записи не меняется, поэтому копия не расходится с `card` |
| `missing_count` | smallint, по умолчанию 0 | нет | `len(missing)` |

**`candidate_skills`** — навыки карточки строками [Д].
| Столбец | Тип | Null | Смысл |
|---|---|---|---|
| `card_id` | → `candidate_cards` (CASCADE) | нет | версия карточки |
| `candidate_id` | → `candidates` (CASCADE) | нет | для поиска без лишнего соединения |
| `name` | varchar(256) | нет | как написано в резюме |
| `normalized` | varchar(256), индекс | нет | нижний регистр, ё→е, NFKC, без мягких переносов, одиночные пробелы; unique вместе с `card_id` |
| `level` | varchar(64) | да | |

Искать навыки нужно только по текущей карточке: `JOIN candidate_cards ON ... WHERE is_current`.

### 4.3. Должности и требования [Д]

**`positions`**: `code` varchar(64) unique; `title`, `employer` varchar(512); `is_municipal_service` bool; `service_group` varchar(256) null; `job_description_document_id` → `source_documents` (SET NULL) null.

**`vacancies`** — публикация должности: `position_id` → `positions` (CASCADE); `channel` `Channel`; `title`; `posting_document_id` → `source_documents` (SET NULL) null; `status` `open` | `closed`, по умолчанию `open`; `opened_at`, `closed_at` date null.

**Единый формат профиля [v1.1].** У всех должностей профиль устроен одинаково: условия допуска (`formal_requirements`) и компетенции (`competencies`) с индикаторами (`competency_indicators`). У каждого условия и индикатора указано, обязательно ли оно и где его подтверждать; у каждой строки — откуда она. Ранг и эталонный уровень из матрицы заказчика хранятся справочно и заполняются только там, где матрица есть (в данных «Кадры» — только консультант).

**`requirement_profiles`** — версия требований к должности [А].
| Столбец | Тип | Null | Смысл |
|---|---|---|---|
| `position_id` | → `positions` (CASCADE) | нет | |
| `version` | integer | нет | unique вместе с `position_id` и `is_synthetic` [v1.5] |
| `status` | `draft` \| `approved` \| `archived`, по умолчанию `draft` | нет | **утверждённая — одна на должность в контуре** (частичный уникальный индекс по `position_id`, `is_synthetic`) [v1.5] |
| `is_synthetic` | bool, по умолчанию false | нет | учебный профиль (п. 2.6.1); утверждается по тем же правилам [v1.5]; не меняется (триггер) |
| `created_by` | varchar(128) | нет | логин или имя модели |
| `approved_by_user_id` | → `users` (SET NULL) | да | |
| `approved_at` | timestamptz | да | |
| `approval_basis` | text | да | основание утверждения: «распоряжение № …» |
| `note` | text | да | |

**`requirement_profile_sources`** — документы версии профиля: `profile_id` → (CASCADE); `source_document_id` → `source_documents` (RESTRICT); `role` (`job_description` | `competency_matrix` | `vacancy_posting` | `regulation` | `other`); `observed_revision` varchar(128) null — редакция, видная в документе; `is_primary` bool. Пара (`profile_id`, `source_document_id`) уникальна.

**Ключ и происхождение строки** — одинаковые столбцы у `formal_requirements`, `competencies`, `competency_indicators`: `key` varchar(64) — unique в профиле (у индикаторов — в компетенции; уникальность по всему профилю проверяет `create_requirement_profile`); `origin` `source` | `team`; `source_refs` jsonb, по умолчанию `[]` — список `{source_document_id, address, quote}`; `note` text null. CHECK `row_source`: при `source` список не пуст, при `team` заполнен `note`. Документы ссылок должны быть среди `requirement_profile_sources` профиля (проверяет `create_requirement_profile`). По `key` пакет сопоставляется с UUID строк базы.

**`formal_requirements`** — условие допуска: `profile_id` → `requirement_profiles` (CASCADE); `kind` `FormalRequirementKind`; `description` text; `params` jsonb (п. 3.5.1); `is_mandatory` bool, по умолчанию true; `verification` `VerificationMethod`; `check_stage` `CheckStage`, по умолчанию `screening`, CHECK `check_stage = 'interview' OR verification IN ('resume', 'documents')` [v1.5]; `acceptance` jsonb `{}` (`AcceptanceIn`); ключ и происхождение; `sort_order` smallint. Столбец `source_quote` v1.0 заменён на `source_refs`.

**`competencies`** — группа индикаторов: `profile_id` → (CASCADE); `code` varchar(32), unique в профиле (`ПАК`, `ИТК`, `PY-DB`); `name`; `rank` `key` | `basic` | `special` **или null**; `target_level_min`, `target_level_max` smallint **или оба null**, иначе `0 <= min <= max <= 100` («90–100 процентов» → 90 и 100); происхождение; `sort_order`.

**`competency_indicators`** — проверяемое требование: `competency_id` → (CASCADE); `text`; `is_mandatory` bool, по умолчанию true; `verification` `VerificationMethod`; `check_stage` — как у формальных требований [v1.5]; `acceptance` jsonb `{}`; `excluded_from_scoring` bool, по умолчанию false; ключ и происхождение; `sort_order`.

### 4.4. Оценка [Д]

**`assessments`** — пара «кандидат × версия требований», а не отклик: скоринг идёт по всем должностям [А].
| Столбец | Тип | Null | Смысл |
|---|---|---|---|
| `candidate_id` | → `candidates` (CASCADE) | нет | |
| `profile_id` | → `requirement_profiles` (CASCADE) | нет | |
| `card_id` | → `candidate_cards` (CASCADE) | нет | по какой версии карточки |
| `version`, `is_current` | integer, bool | нет | версия в паре (кандидат, профиль) |
| `model`, `prompt_version` | varchar(128), varchar(64) null | | кто оценил |
| `formal_result` | `met` \| `not_met` \| `unknown` | нет | считает код (п. 2.6) |
| `formal_preliminary` [v1.5] | bool, по умолчанию false | нет | итог `met`, но с предварительным обязательным требованием этапа `screening`; считает код (п. 2.6) |
| `overall_score` | smallint 0–100 | да | итог по компетенциям |
| `summary` | text | да | |

**`formal_checks`**: `assessment_id` → (CASCADE); `requirement_id` → `formal_requirements` (CASCADE); `result`; `basis` `VerificationMethod`, по умолчанию `resume` [v1.5]; `is_preliminary` bool, по умолчанию false, считает код (п. 2.6) [v1.5]; `explanation` null; `evidence` jsonb `[]`; `alternatives` jsonb `[]` [v1.5]; `confirmed_by_user_id` → `users` (RESTRICT) null [v1.5]. CHECK `basis_confirmation`: при `resume` подтвердившего нет; иначе подтвердивший обязателен, а цитат резюме и альтернатив нет — основание документ, интервью или тест.

**`competency_scores`**: `assessment_id` → (CASCADE); `competency_id` → `competencies` (CASCADE); `level` smallint 0–100 null; `explanation` null; `evidence` jsonb `[]`.

### 4.5. Отбор [Д]

**`applications`** — участие кандидата в отборе.
| Столбец | Тип | Null | Смысл |
|---|---|---|---|
| `candidate_id` | → `candidates` (CASCADE) | нет | |
| `vacancy_id` | → `vacancies` (CASCADE) | да | пусто для внешней должности |
| `external_position_title` | varchar(512) | да | должность вне платформы (из «Истории общения с кандидатом») |
| `posting_title` [v1.6] | varchar(512) | да | публикация hh, на которую пришёл отклик (подвал резюме «Отклик на вакансию: «…»»); у внешних откликов пусто |
| `source` | `response` \| `history` \| `manual` | нет | |
| `applied_at` | date | да | |
| `current_stage_code` | → `selection_stages.code` | нет | текущий этап |
| `created_at`, `updated_at` | timestamptz | нет | |

Ограничения: заполнено `vacancy_id` или `external_position_title` (CHECK); пара (`candidate_id`, `vacancy_id`) уникальна, если вакансия указана; внешний отклик (`source = history`) уникален по (`candidate_id`, `external_position_title`, `applied_at`), пустая дата считается одинаковой (`NULLS NOT DISTINCT`) [v1.6].

Внешний отклик — факт из прошлого, а не текущий отбор: он создаётся на этапе `new` (так устроен `create_application`), но рабочие списки, воронка и действия кадровика берут только `source = response` [v1.6].

**`stage_events`** — журнал переходов, только добавление: `seq` bigint identity unique (порядок); `application_id` → (CASCADE); `from_stage_code` (null у первого события), `to_stage_code` → `selection_stages`; `rejection_reason_code` → `rejection_reasons` null; `actor_user_id` → `users` (SET NULL) null; `comment` null.

**`interviews`**: `application_id` → (CASCADE); `kind` `phone` | `department`; `interviewer_user_id` → `users` (SET NULL); `scheduled_at`, `held_at` timestamptz null; `result` `pending` | `continue` | `stop` | `no_answer`, по умолчанию `pending`; `summary` null.

**`interview_questions`**: `interview_id` → (CASCADE); `competency_id` → `competencies` (SET NULL) null; `gap` text null — какого сведения не хватает; `question` text; `author` `model` | `human`; `answer_notes` null; `score` smallint null; `sort_order`.

**`department_feedback`** — итог рассмотрения департаментом: `application_id` → (CASCADE); `interview_held` bool null; `outcome` `pending` | `fit` | `not_fit`, по умолчанию `pending`; `confirmed_competencies` jsonb; `gaps` null; `rejection_reason_code` → `rejection_reasons` null; `keep_in_reserve` bool null; `comment` null; `author_user_id` → `users` (SET NULL); `received_at` timestamptz.

**`reserve_entries`** — кадровый резерв. Резерв не является этапом: кандидат может получить отказ и остаться в резерве [Д].
| Столбец | Тип | Null | Смысл |
|---|---|---|---|
| `candidate_id` | → `candidates` (CASCADE) | нет | |
| `position_id` | → `positions` (SET NULL) | да | резерв на должность; удалить должность с резервом без направления нельзя (раздел 4, «Удаление») |
| `competency_area` | varchar(256) | да | резерв по направлению |
| `source_application_id` | → `applications` (SET NULL) | да | из какого отбора |
| `reason` | text | да | |
| `status` | `active` \| `withdrawn` \| `hired`, по умолчанию `active` | нет | |
| `added_by_user_id` | → `users` (SET NULL) | да | |
| `added_at` | timestamptz | нет | |
| `valid_until` | date | да | пусто — бессрочно |

Ограничение: заполнено `position_id` или `competency_area`.

### 4.6. Поиск [Д]

**`embeddings`** — вектор фрагмента очищенного текста.
| Столбец | Тип | Null | Смысл |
|---|---|---|---|
| `candidate_id` | → `candidates` (CASCADE), индекс | нет | |
| `candidate_text_id` | → `candidate_texts` (CASCADE) | нет | |
| `chunk_kind` | `ChunkKind` | нет | какая часть резюме |
| `chunk_index` | integer | нет | номер фрагмента |
| `text` | text | нет | фрагмент |
| `start_offset`, `end_offset` | integer | нет | границы в `candidate_texts.text` (п. 2.11) |
| `model` | varchar(128) | нет | модель эмбеддингов |
| `embedding` | `vector` **без размерности** [А] | нет | |

Ограничение: уникальна четвёрка (`candidate_text_id`, `chunk_kind`, `chunk_index`, `model`). **Поиск обязан фильтровать по `model`**: векторы разных моделей несравнимы и могут иметь разную длину. Индекс HNSW требует фиксированной размерности, его добавит миграцией модуль поиска, когда выберет модель.

### 4.7. Доступ

**`users`**: `login` varchar(64) unique; `full_name`; `role` `hr` | `department` | `admin`; `department` null; `is_active` bool, по умолчанию true.

**`audit_log`** — только добавление: `seq` bigint identity unique; `user_id` → `users` (SET NULL) null; `action` `AuditAction`; `entity_type` varchar(64); `entity_id` varchar(64) null — строкой, чтобы журнал не мешал удалению записей; `details` jsonb. Индекс (`entity_type`, `entity_id`).

## 5. Перечисления

| Имя | Значения |
|---|---|
| `DocumentKind` | `resume`, `job_description`, `vacancy_posting`, `competency_matrix`, `regulation`, `other` |
| `Channel` | `hh_ru`, `rabota_rossii`, `city_site`, `email`, `citizen_appeal` (обращение по 59-ФЗ), `internship`, `internal`, `other` |
| `FileFormat` | `hh_txt`, `hh_docx`, `docx`, `pdf`, `txt`, `other` |
| `FormalRequirementKind` | `education_level`, `education_field`, `experience`, `knowledge`, `other` |
| `VerificationMethod` [v1.1] | `resume`, `documents`, `interview`, `test` — и для `verification` строк профиля, и для `formal_checks.basis` [v1.5] |
| `CheckStage` [v1.5] | `screening`, `interview` |
| `RowOrigin` [v1.1] | `source`, `team` |
| `SourceRole` [v1.1] | `job_description`, `competency_matrix`, `vacancy_posting`, `regulation`, `other` |
| `ChunkKind` | `experience`, `about`, `skills`, `education`, `cover_letter`, `full` |
| `AuditAction` | `view_pii`, `llm_call`, `stage_change`, `export`, `other` |

Остальные перечисления приведены у своих столбцов в разделе 4.

## 6. Справочники (загружает `python -m app.db.seed`, повторный запуск безопасен)

Столбцы: `selection_stages` — `code` varchar(32) PK, `title`, `sort_order` smallint, `is_final` bool (из финального этапа переходов нет); `rejection_reasons` — `code` varchar(32) PK, `title`, `side` `employer` | `candidate` | `other`. Новый этап или причину кадровик добавляет строкой, без миграции.

**Этапы `selection_stages`** (в порядке `sort_order`): `new` «Новый отклик» → `screening` «Первичный отбор» → `phone_interview` «Телефонное интервью» → `sent_to_department` «Передан в департамент» → `department_interview` «Собеседование в департаменте» → `documents` «Оформление документов». Финальные: `hired` «Принят», `rejected` «Отказ», `withdrawn` «Кандидат отказался». Первый этап нового отклика — `new`.

**Причины отказа `rejection_reasons`**: `formal_requirements`, `competencies`, `experience`, `legal_restrictions`, `position_filled` (сторона `employer`); `candidate_declined`, `no_response` (`candidate`); `other`.

**Должности `positions`** и папки архива организаторов (по ним импорт находит должность; в коде это `POSITION_CODE_BY_FOLDER`):

| `code` | Папка архива | Муниципальная служба |
|---|---|---|
| `junior-python-dev` | `Junior Python-разработчик` | нет |
| `python-dev` | `Python-разработчик` | нет |
| `qa-manual` | `QA Engineer Manual` | нет |
| `frontend-dev` | `Frontend developer` | нет |
| `junior-ux-ui` | `Junior UX_UI Дизайнер` | нет |
| `hr-consultant` | `консультанта сектора подбора кадров` | да, ведущая группа (группа 3) |

У каждой должности одна вакансия с `channel = hh_ru`: отклики в архиве выгружены из hh.ru.

## 7. Функции доступа (`app/db/repository.py`)

Все функции первым аргументом принимают `Session` и не коммитят (п. 2.8). Остальные ссылки на записи передаются как UUID (`candidate_id`, `application_id` и т. д.), а не как ORM-объекты: модулям не нужно импортировать модели базы (п. 11.1). Возвращаемые объекты читают по атрибутам (`.id`, `.code`) и обратно в функции не передают. Нарушение правил вызывает исключение `RepositoryError` или его наследников `StageTransitionError` и `EvidenceError`. Нарушение ограничения базы вызывает `sqlalchemy.exc.IntegrityError`, после него транзакцию нужно откатить.

| Функция | Что гарантирует | Ошибки |
|---|---|---|
| `add_source_document(kind, channel, file_format, original_path, raw_text, content=None, import_batch=None) → (документ, создан)` | повтор с тем же SHA-256 (`content`, иначе текста) возвращает существующий документ и `False`; путь приводится к NFC | — |
| `create_candidate(code, source_document_id, redacted_text, redaction_method, headline=None, pii=None, is_synthetic=False) → Candidate` | кандидат, ПДн (если переданы), текст версии 1; `is_synthetic` — учебный контур [v1.5]. Если тот же файл пришёл в папке другой вакансии, второго кандидата не создают: импорт находит кандидата по документу и добавляет ему отклик (`docs/modules/ingest.md`, «Статусы и дубли») | нет документа, документ не `resume` → `RepositoryError`; повтор `code` или документа → `IntegrityError` |
| `add_candidate_text(candidate_id, text, redaction_method)` / `get_current_text(candidate_id)` | новая текущая версия текста / текущий текст или `None` | — |
| `add_candidate_card(candidate_id, card, extractor, prompt_version=None, candidate_text_id=None)` | новая текущая версия карточки; навыки из `card.skills` нормализованы и без дублей | нет текста, или текст другого кандидата → `RepositoryError` |
| `get_current_card(candidate_id)` | текущая карточка или `None` | — |
| `find_candidates_by_skills(skills, match_all=True) → [Candidate]` | по текущим карточкам: все навыки или хотя бы один; сортировка по `code` | — |
| `create_requirement_profile(position_id, created_by, formal_requirements, competencies, sources=(), version=None, is_synthetic=False, note=None) → RequirementProfile` [v1.1] | черновик профиля (п. 3.6); порядок строк → `sort_order`; без `version` — следующий номер для должности **в контуре** [v1.5]; `params` проверены по формату 0.1 (при построении входа) | нет должности или документа, документ ссылки не в `sources`, документ в `sources` дважды, повтор ключа строки или кода компетенции, `requires_requirement` не указывает на требование уровня образования профиля [v1.5] → `RepositoryError`; повтор (`position_id`, `is_synthetic`, `version`) → `IntegrityError` |
| `approve_requirement_profile(profile_id, approved_by_user_id, approval_basis) → RequirementProfile` [v1.1] | черновик → `approved`; прежняя утверждённая версия должности **того же контура** → `archived` [v1.5]; `approved_at` = время транзакции | не черновик, пользователь не активный `hr`/`admin`, пустое основание → `RepositoryError`. Учебный профиль утверждается [v1.5] |
| `get_approved_profile(position_id, synthetic=False) → RequirementProfile \| None` [v1.5] | действующий профиль должности в контуре; по умолчанию рабочий | — |
| `save_assessment(candidate_id, profile_id, card_id, model, formal_checks, competency_scores, overall_score=None, summary=None, prompt_version=None)` | новая текущая версия оценки; `basis = resume` у всех строк; альтернативы проверены (п. 3.4); `formal_result`, `is_preliminary`, `formal_preliminary` считает код по этапу `screening` (п. 2.6) | профиль в архиве [v1.1]; реальный кандидат × учебный профиль или × неутверждённый профиль [v1.5]; карточка чужая, требование или компетенция из другого профиля, одно требование или компетенция дважды [v1.3]; альтернативы неполные, лишние или итог строки им противоречит (п. 3.4) [v1.5] → `RepositoryError`; цитата (в том числе альтернативы) не на месте, из чужого текста или не из текста карточки [v1.3] → `EvidenceError` |
| `confirm_formal_check(assessment_id, requirement_id, result, basis, actor_user_id, comment) → Assessment` [v1.5] | новая текущая версия оценки: строки текущей скопированы, строка требования заменена результатом с `basis` ∈ {`documents`, `interview`, `test`}, `confirmed_by_user_id`, `explanation = comment`, без цитат; итог пересчитан; прежняя версия в истории | `basis = resume`, пустой комментарий, оценка не текущая, пользователь не активный `hr`/`admin`, требование не из профиля, профиль не допускает оценку кандидата (п. 2.6.1) → `RepositoryError` |
| `is_preliminary(result, basis, verification) → bool`, `is_training_assessment(candidate, profile) → bool` [v1.5] | предварительный результат (п. 2.6); учебная оценка (п. 2.6.1) | — |
| `create_application(candidate_id, source, vacancy_id=None, external_position_title=None, applied_at=None, actor_user_id=None)` | этап `new` и первое событие журнала | нет ни вакансии, ни внешней должности → `RepositoryError`; повтор на ту же вакансию → `IntegrityError` |
| `move_application(application_id, to_stage_code, actor_user_id=None, comment=None, rejection_reason_code=None, confirm_skip=False) → StageEvent` | блокирует строку отклика (`SELECT … FOR UPDATE`), меняет этап и пишет событие; переход не по порядку — только с подтверждением человека (п. 2.7) | нет такого отклика, нет такого этапа, тот же этап, переход не по порядку без `confirm_skip`, `actor_user_id` и `comment` [v1.3], отклик уже в финальном этапе, причина отказа не при `rejected`/`withdrawn`, неизвестная причина → `StageTransitionError` |
| `stage_history(application_id) → [StageEvent]` | события по `seq` | — |
| `record_department_feedback(application_id, outcome, …)` | сохраняет обратную связь, этап не меняет | неизвестная причина отказа → `RepositoryError` |
| `reserve_candidate(candidate_id, position_id=None, competency_area=None, source_application_id=None, reason=None, contact_basis=None, added_by_user_id=None, valid_until=None, today=None) → (ReserveEntry, created)` [v1.8] | действующая запись на ту же цель (должность, иначе направление) возвращается с `created = False`, в том числе при одновременной вставке; активная с истёкшим сроком закрывается (`expired`) и открывается новый период | нет ни должности, ни направления; нет кандидата, должности или отклика; исходный отклик чужого кандидата или не `response` → `RepositoryError` |
| `add_to_reserve(...)` | то же, что `reserve_candidate`, возвращает только запись (прежняя сигнатура + `contact_basis`, `today`) | как у `reserve_candidate` |
| `withdraw_reserve(reserve_id, actor_user_id, reason)` [v1.8] | `withdrawn`, `ended_at`, `end_reason`, `ended_by_user_id` | пустая причина; записи нет; запись не активна → `RepositoryError` |
| `active_reserve_condition(today=None)` [v1.8] | условие SQLAlchemy «запись действует»: `active` и срок пуст или не раньше `today` (последний день включён). Одно правило для списка резерва и фильтра поиска `search-01` | — |
| `reserve_for_position(position_id, today=None) → [ReserveEntry]` | действующие записи на должность (`active_reserve_condition`); резерв «по направлению» сюда не входит | — |
| `get_candidate_pii(candidate_id, user_id, purpose)` | пишет `view_pii` в журнал, затем возвращает ПДн или `None` | — |
| `write_audit(action, entity_type, entity_id=None, user_id=None, details=None)` | запись журнала | — |
| `normalize_skill(name) → str` | правило нормализации из п. 4.2 | — |

## 8. Пример: один кандидат по всей цепочке

Отклик `Python-разработчик/отклик 5.txt` из архива организаторов. Тексты и позиции реальные. Очистка в примере такая: ссылки `github.com/…` заменены на `[ссылка скрыта]`. UUID условные.

**1. Импорт.** `add_source_document(kind="resume", channel="hh_ru", file_format="hh_txt", original_path="Python-разработчик/отклик 5.txt", …)` возвращает документ и `True`. Повторный вызов с тем же файлом возвращает тот же документ и `False`.
`create_candidate(code="py-0005", headline="Python Backend Developer (FastAPI, PostgreSQL)", pii=PiiData(links=[4 ссылки на GitHub]), redacted_text=<3982 символа>, redaction_method="…")` создаёт кандидата, ПДн и текст версии 1 (`id = 11111111-1111-4111-8111-111111111111`).
`create_application(candidate_id=<id кандидата>, source="response", vacancy_id=<python-dev, hh_ru>)` создаёт отклик на этапе `new`.

**2. Карточка** (`add_candidate_card`, `extractor="yandexgpt-lite/latest"`):

```json
{
  "headline": "Python Backend Developer (FastAPI, PostgreSQL)",
  "applied_to": ["Python-разработчик"],
  "education": [{"level": "высшее", "degree": null, "institution": "Академия труда и социальных отношений",
                 "faculty": null, "field": "Управление персоналом, Менеджмент", "year": 2015}],
  "courses": [],
  "experience_years": 13.3,
  "experience": [
    {"position": "Backend-разработчик", "organization": "Организация 1", "start": "2024-05", "end": "2025-05",
     "is_current": false, "duties": ["REST API на FastAPI", "SQLAlchemy, PostgreSQL", "автотесты на Pytest"]},
    {"position": "Специалист по контролю качества и аналитике", "organization": "Организация 2",
     "start": "2016-06", "end": "2024-05", "is_current": false, "duties": []},
    {"position": "оператор консультант", "organization": "Организация 3", "start": "2012-02", "end": "2016-06",
     "is_current": false, "duties": []}
  ],
  "skills": [{"name": "Python", "level": null}, {"name": "FastAPI", "level": null}, {"name": "Pytest", "level": null}],
  "languages": [{"name": "Русский", "level": "Родной"}],
  "about": "Python Backend Developer с опытом коммерческой разработки на Python/FastAPI. …",
  "cover_letter": null,
  "missing": ["сопроводительное письмо"],
  "pii_hidden": true
}
```

В таблицу при этом попадают `experience_years = 13.3`, `education_level = "высшее"`, `missing_count = 1` и строки `candidate_skills` с `normalized` = `python`, `fastapi`, `pytest`. После этого `find_candidates_by_skills(["FastAPI", "pytest"])` находит `py-0005`.

**3. Оценка** (`save_assessment`) по профилю `python-dev` (создан `create_requirement_profile`, рабочий, утверждён `approve_requirement_profile` — реального кандидата база оценивает только по утверждённому рабочему профилю, п. 2.6.1) с требованием «Высшее образование» и компетенцией `BACKEND`:

```json
{"requirement_id": "<id требования>", "result": "met",
 "evidence": [{"candidate_text_id": "11111111-1111-4111-8111-111111111111",
               "quote": "Высшее образование", "start": 3649, "end": 3667}]}
```
```json
{"competency_id": "<id BACKEND>", "level": 65,
 "evidence": [{"candidate_text_id": "11111111-1111-4111-8111-111111111111",
               "quote": "Писала автоматические тесты на Pytest.", "start": 473, "end": 511},
              {"candidate_text_id": "11111111-1111-4111-8111-111111111111",
               "quote": "Разрабатывала и поддерживала REST API (GET/POST).", "start": 342, "end": 391}]}
```

Результат: `formal_result = "met"`, оценка версии 1 становится текущей.

**4. Отбор.** `move_application` по этапам `screening` → `phone_interview` → `sent_to_department`. Затем `record_department_feedback(outcome="not_fit", gaps="мало коммерческого опыта в разработке", rejection_reason_code="experience", keep_in_reserve=true)`: этап остаётся `sent_to_department`. Кадровик вызывает `move_application(…, "rejected", rejection_reason_code="experience")`, затем `add_to_reserve(position_id=<python-dev>)`.
История `stage_history`: `new → screening → phone_interview → sent_to_department → rejected`. `reserve_for_position(<python-dev>)` содержит `py-0005`.

**5. Ошибочные случаи — одинаково для поставщика и потребителя:**

| Действие | Результат |
|---|---|
| цитата `{"quote": "Руководила командой", "start": 0, "end": 19}` | `EvidenceError`: в тексте на позиции 0–19 другие символы, оценка не сохраняется |
| цитата с `"start": 473, "end": 500` и той же строкой | ошибка проверки `Evidence`: длина не совпадает с границами |
| цитата из текста другого кандидата | `EvidenceError` |
| `move_application(…, "screening")` после `rejected` | `StageTransitionError`: отбор уже завершён на этапе «Отказ» |
| `move_application(…, "screening", rejection_reason_code="experience")` | `StageTransitionError`: причина указывается только при отказе |
| второй `create_application` того же кандидата на ту же вакансию | `IntegrityError` |
| карточка с полем `"salary": 100000` | ошибка проверки `CandidateCard`: лишнее поле |
| `Experience(start="2025-05", end="2024-05")` | ошибка проверки: конец раньше начала |
| `move_application(…, "sent_to_department")` сразу после `new` | `StageTransitionError`: перескок этапов без подтверждения человека |
| то же с `confirm_skip=True, actor_user_id=<кадровик>, comment="…"` | переход выполнен, причина в журнале |
| `met` по требованию с `verification = documents` | сохраняется `met`, `basis = resume`, `is_preliminary = true`; итог `met`, `formal_preliminary = true` [v1.5] |
| `save_assessment` реального `py-0005` по учебному или неутверждённому профилю | `RepositoryError` [v1.5] |

Проверено запуском: v1.0 — 41 тест (team-gorky-9/hr#1) и `scripts/smoke_real_candidate.py` на этом отклике; v1.1 — 59 тестов (team-gorky-9/hr#4) и тот же скрипт; v1.3 — 115 тестов на PostgreSQL (вместе с тестами импорта).

## 9. Как менять контракт

Изменение — это PR в `hr`, в котором вместе меняются этот файл, модели, миграция Alembic и тесты. В описании PR перечисляются затронутые потребители (раздел 1) и способ перехода. Утверждает Родион, потребители проверяют изменение на примере из раздела 8. Добавление необязательного поля в JSON или нового значения в перечисление считается совместимым изменением. Удаление или переименование поля или столбца — несовместимым: его согласуют со всеми потребителями до слияния.

## 10. Отличия от черновика в `project-context.md`

| В черновике | В контракте | Почему |
|---|---|---|
| `"period": "2024-12 — сейчас"` | `start`, `end` (`YYYY-MM`), `is_current` | период можно сравнивать и считать стаж без разбора строки |
| `id`, `source`, `raw_text` внутри карточки | столбцы `candidates`, `source_documents`, `candidate_texts` | карточка версионируется отдельно от документа; `raw_text` содержит ПДн и в карточке недопустим |
| `id` вида `py-0001` | UUID + `code` `py-0005` | UUID не зависит от источника; `code` остаётся для людей |
| — | `headline`, `courses`, `about`, `cover_letter`; `institution`, `faculty` в `education` | есть в резюме hh.ru и docx, нужны для оценки и интерфейса |
| схема базы не описана | разделы 4–6 | |

## 11. Решения по открытым вопросам (19.11.2026)

1. **Функции доступа принимают UUID, а не ORM-объекты** [Д]. Модули не импортируют модели базы. Сигнатуры — раздел 7. Реализация в team-gorky-9/hr#1 приводится к этому.
2. **Формат `code` кандидата** [А, принято]: префиксы `jpy`, `py`, `qa`, `fe`, `ux`, `hr` и номер файла из 4 цифр (`py-0005`).
3. **Прямое чтение таблиц разрешено** [А, принято] всем модулям, кроме `candidate_pii` (только через `get_candidate_pii`). Запись — только через функции раздела 7. Таблицы, для которых функции ещё нет, и кто её добавит — раздел 1.
4. **Эмбеддинги хранятся в pgvector** (тип `vector`). Модель, размерность и индекс выбирает модуль поиска; Родион допишет их в этот контракт вместе с миграцией.
5. **Роль `department` остаётся** в `users`. Заводить ли учётки сотрудникам департаментов, решим позже; схема от этого не меняется.
6. **Даты рождения хранятся в `candidate_pii`**, как и прочие ПДн. Допустимость хранения на стенде уточняем у организаторов.
7. **Очистка ПДн — зона импорта.** В `candidate_texts.text` не должно быть ФИО, контактов, ссылок на профили (в т. ч. GitHub с именем), даты рождения, возраста и пола. Грамматический род («работала») не заменяем: замена портит текст и сдвигает позиции цитат.
8. **Город и гражданство не вычищаются** [Д, 19.11.2026, v1.2]. Строки «Проживает: …» и «Гражданство: …» остаются в `candidate_texts.text`: модель использует их для оценки (место работы, релокация, требование гражданства РФ для муниципальной службы). По отдельности они не указывают на человека. Риск: вместе с другими сведениями из резюме (станция метро, редкая должность) они сужают круг людей. Если понадобится, слепой режим интерфейса может скрывать их отдельно. Столбцы `candidate_pii.city` и `citizenship` остаются в схеме и не заполняются. Удалить их можно отдельной миграцией (несовместимое изменение, раздел 9).

## 12. Изменения v1.1 — единый формат профиля требований (19.11.2026, ждёт утверждения)

**Почему.** В данных «Кадры» матрица компетенций с рангами и процентами есть только у консультанта. У пяти IT-должностей есть только ДИ и вакансия: ранги и проценты пришлось бы придумывать, чтобы пройти NOT NULL. Кейс определяет матрицу как список требований, где ясно, «какие навыки обязательны, какие желательны и каким образом их необходимо проверять» (TASK.md, проблема 3) — проценты в это определение не входят. Разбор данных: `hq/work/2026-11-19-requirement-profiles/db-template-proposal.md` в штабе.

| Изменение | Совместимость |
|---|---|
| `competencies.rank`, `target_level_min/max` допускают null (оба уровня вместе) | ослабление ограничения, старые данные валидны |
| Ключ и происхождение строки (`key`, `origin`, `source_refs`, `note`) у трёх таблиц + CHECK и уникальность ключа | новые столбцы; старые строки → `key = legacy.<начало id>`, `origin = team`, `note` = «создано до миграции 0002…» |
| `formal_requirements.source_quote` → `source_refs` | **несовместимо**: столбец удалён, прежняя цитата переносится в `note`. Потребителей у столбца не было (только тесты и smoke-скрипт) |
| `acceptance` у условий и индикаторов, `competency_indicators.excluded_from_scoring` | новые столбцы |
| `competency_indicators.is_mandatory`, `verification`; `formal_requirements.verification` | новые столбцы; старые строки → `verification = resume` |
| `requirement_profiles.is_synthetic`, `approval_basis`; таблица `requirement_profile_sources` | новые |
| Функции `create_requirement_profile`, `approve_requirement_profile` | закрывают пробел: запись только через функции (п. 11.3), а функций для профилей не было |
| `save_assessment` отклоняет профиль в архиве | новое правило; `draft` по-прежнему допустим (нужен для проверки на учебных данных) |

**Затронутые потребители.** Давид — пишет профиль в формате п. 3.6. Илья — читает `is_mandatory` и `verification` индикаторов; по компетенции без эталона нет «разрыва до эталона». Ася — утверждение через `approve_requirement_profile`.

**Не входит и требует решения Ильи:** результат по отдельному индикатору («есть / нет / неизвестно» с цитатой). Сейчас оценка хранится по компетенции (`competency_scores`). Если скорингу нужен вывод по индикатору — отдельная таблица `indicator_checks` следующей миграцией.

**Загрузка пакета.** `scripts/load_requirement_profiles.py` загружает файловый пакет stage-0b-01 (`requirement-profile-review/0.2`): документы манифеста — в `source_documents` со сверкой SHA-256, профили — через `create_requirement_profile`. Без `--commit` транзакция откатывается. Поля пакета, которые остаются только в пакете (для ревью): `check_stage`, `evidence_channels`, `mandatory_basis`, `interpretation_status`, `grouping_status`, `collection`, `issues`, `context_note`, `aggregation_method`, `exclude_duplicate_weight`, `duplicates_keys`, `related_indicators`, `split_candidates`, `verification_note`, `acceptance` групп. Повторная загрузка той же версии отклоняется: изменения — новой версией.

**Как проверено:** миграция `0002` применена к базе с профилем, созданным до неё (строки получили ключ `legacy.*`, `origin = team`, цитата перенесена в `note`), откат `0002 → 0001` и повторное применение; `alembic check` — модели совпадают с миграциями; 59 тестов на PostgreSQL; `scripts/smoke_real_candidate.py` на `Python-разработчик/отклик 5.txt`; загрузка пакета Давида (ветка `docs/stage-0b-01-requirement-profiles`, `3926099`) в тестовую базу: 4 документа со сверкой SHA-256, `hr-consultant` v2 — 2 условия, 5 компетенций, 54 индикатора; `python-dev` v2 — 2 условия, 8 компетенций, 53 индикатора.

## 13. Изменения v1.2 — город и гражданство остаются в очищенном тексте (19.11.2026, ждёт утверждения)

| Изменение | Совместимость |
|---|---|
| Город и гражданство (это ПДн) не вычищаются и остаются в `candidate_texts.text` (п. 2.2, 11.8) | схема не меняется; меняется только правило очистки в импорте |
| `PiiData.city` и `citizenship` импорт не заполняет (п. 3.3) | поля и столбцы остаются, значения null |
| Пол добавлен в список вычищаемого (п. 11.7) | уточнение: пол уже был ПДн по п. 2.2 |

**Затронутые потребители.** Илья — модель видит город и гражданство в очищенном тексте. Ася — при слепом режиме город можно скрывать в интерфейсе отдельно. Импорт (`app/ingest/`, Денис) реализует правило; проверено тестами `tests/test_ingest_redact.py` и прогоном архива «Кадры».

## 14. Изменения v1.3 — сверка контракта с кодом (19.11.2026, ждёт утверждения)

**Почему.** После v1.1 и v1.2 контракт сверили с `main` (`1e1f654`): моделями, миграциями `0001`–`0002`, `repository.py`, импортом и архивом «Кадры». Найдены места, где текст обещает не то, что делает код, и правила, которых не хватало. Решения по открытым вопросам принял Денис 19.11 [Д].

| Изменение | Совместимость |
|---|---|
| `save_assessment` отклоняет одно требование или компетенцию дважды в одной оценке (п. 2.6, раздел 7). Раньше сохранялись обе строки, а `formal_result` считался по последней | новое правило в функции, схема не меняется. Вызовы без повторов работают как раньше |
| Раздел 1: таблицы без функции записи и кто её добавит | только текст |
| Раздел 4, «Удаление»: в рабочей базе записи не удаляют; `reserve_entries.position_id` (SET NULL) на деле запрещает удаление должности | только текст, схема не меняется. Поведение закреплено тестом |
| П. 2.1, 2.2, `pii_hidden`, раздел 13: город и гражданство — ПДн, которые не вычищаются, а не «не ПДн» | только текст |
| П. 2.6: `met` по требованию с `verification` ≠ `resume` сохраняется как `unknown` [Д] | новое правило в функции. Меняет итог только для требований «по документам / интервью / тесту»; у загруженных профилей это образование консультанта и Python |
| П. 3.2: цитата должна быть из текста карточки оценки [Д] | новое правило в функции. Вызовы, где карточка и цитаты из одного текста (smoke-скрипт, тесты), не меняются |
| П. 2.7: перескок этапа — только с `confirm_skip`, `actor_user_id` и `comment` [Д]; причина отказа необязательна | новый необязательный параметр. Последовательные переходы и выход в `rejected`/`withdrawn` работают как раньше; один тест, который перескакивал этапы, переведён на пошаговый путь |
| Повтор файла в папке другой вакансии решает импорт (раздел 7) | только текст |
| Шапка, вступление, раздел 8: номера PR и число тестов | только текст |

**Затронутые потребители.** Илья — повтор строки в `save_assessment` теперь ошибка; цитаты берутся из текста карточки; `met` по требованию «не по резюме» сохраняется как `unknown`. Ася — перескок этапа в интерфейсе требует подтверждения кадровика с причиной (передать `confirm_skip`, пользователя и комментарий); функции для интервью, пользователей и резерва — в её задачах. Родион — функция записи `embeddings` в задаче поиска.

**Не входит, решается отдельно:**
- Уникальность (`assessment_id`, `requirement_id`) и (`assessment_id`, `competency_id`) в самой базе — миграцией, если понадобится запись в обход функции.
- Замена `CASCADE`/`SET NULL` на `RESTRICT` — миграцией, если правило «не удалять» нужно держать базой, а не договорённостью.
- Пересчёт индексов цитат для эмодзи в интерфейсе (п. 2.11): риск известен, пока не делаем.

**Как проверено:** 108 тестов на PostgreSQL, в том числе новые: повтор строки оценки, `met` → `unknown` по требованию «по документам», цитата не из текста карточки, перескок этапа без подтверждения и с подтверждением, выход и найм по порядку, запрет удаления должности с резервом.

## 15. Изменения v1.4 — расширение карточки кандидата (20.11.2026, ждёт утверждения)

**Почему.** Профили требований (v1.1) и контракт оценки проверяют то, чего в карточке не было: уровень образования из закрытого списка, «учится / окончил», курс, код специальности, переподготовку отдельно от повышения квалификации, периоды работы, где указан только год, и вид занятости. Предложение Ильи. Расширение разрешил Родион, решения по вопросам принял Денис 20.11.

| Изменение | Совместимость |
|---|---|
| `Education.level` — закрытый словарь; новое `level_raw` | читается всё, что было: свободная строка нормализуется, нераспознанная → `null` и `level_raw`. В `candidate_cards.education_level` теперь только значения словаря или null |
| `Education.status`, `course`, `field_code`; `Course.kind`, `field`, `completed`, `hours`; `Experience.kind` | новые необязательные поля (null — не указано), старые карточки валидны |
| `Experience.start/end` — `YYYY`, `YYYY-MM`, `YYYY-MM-DD`; сравнение с учётом точности | расширение формата: прежние `YYYY-MM` валидны. Прежнее сравнение строк ошибочно отклоняло `2024-05` → `2024` |
| `experience_bounds` — стаж по периодам с границами (п. 3.1.1) | новая функция, существующий код не меняется |

Схема базы не меняется: `card` хранится в JSONB, миграция не нужна.

**Затронутые потребители.** Илья — извлечение карточки заполняет новые поля, а стаж по периодам считает через `experience_bounds`. Важно: в карточках до v1.4 нет `kind`, поэтому их периоды попадают только в верхнюю границу, и по ним `lower = 0`. Ася — показывает `level` из словаря, а для `level = null` показывает `level_raw`.

**Как проверено:** тесты `tests/test_card_v14.py`: нормализация всех формулировок уровня из архива «Кадры», чтение старой карточки, новые поля и их ограничения, даты любой точности, границы стажа на примерах из таблицы п. 3.1.1. Все тесты проекта на PostgreSQL проходят, вместе с контрольным набором оценки `py-9001`.

## 16. Изменения v1.5 — учебный и рабочий контуры, основание результата, альтернативы, этап проверки (20.11.2026, ждёт утверждения)

**Почему.** Решения Родиона по пакету профилей (20.11, через Давида): снять запрет утверждения учебного профиля, сохранив `is_synthetic`; формат `params` пакета — основа (Р1); хранить основание результата, результаты альтернатив по ключам и `check_stage` (Р4). Простое снятие запрета ломало рабочий контур: `approve_requirement_profile` архивировал утверждённый профиль должности без учёта `is_synthetic`, индекс держал одну утверждённую версию на должность, а «утверждённый профиль» каждый потребитель выбирал своим запросом — учебное правило «стаж ≥ 24 мес.» стало бы рабочим для реальных откликов Python. Разбор и развилки: `hq/work/2026-11-20-profile-contours-and-basis/plan.md` в штабе. В v1.5 сведены две правки Дениса (первая — контуры и `basis`, вторая — `hq/work/2026-11-20-profile-assessment-joints/proposal.md`): из второй взяты хранимые признаки предварительности, определение «предварительный» по контракту оценки п. 4.4 и правило «`unknown` допустим всегда» для альтернатив.

| Изменение | Совместимость |
|---|---|
| Контуры (п. 2.6.1): `candidates.is_synthetic`; уникальность версии и «одна утверждённая» — в контуре; триггер неизменяемости `is_synthetic` у кандидатов и профилей | новые столбцы и ослабление уникальности; существующие строки — рабочий контур. **Меняет поведение:** учебный профиль утверждается; утверждение архивирует только свой контур |
| `get_approved_profile(position_id, synthetic=False)` | новая функция; потребители, которые выбирали `status = 'approved'` сами, переходят на неё |
| `save_assessment`: реальный кандидат — только утверждённый рабочий профиль | **несовместимо для вызовов** «реальный кандидат × черновик» (v1.1 разрешал черновик для проверки на учебных данных). Эту потребность закрывают учебные кандидаты: их можно оценивать по любому не архивному профилю. Тесты и smoke-скрипт переведены на утверждённый профиль или учебного кандидата |
| `check_stage` у условий и индикаторов + CHECK; `formal_result` — только по `screening` | новый столбец. Миграция: `verification` `interview`/`test` → `interview`, иначе `screening` (у данных пакета v2 — 57 строк `interview`, как `check_stage` в пакете). Итог меняется только у профилей с обязательным требованием этапа `interview`; в данных таких нет |
| `formal_checks.basis`, `is_preliminary`, `alternatives`, `confirmed_by_user_id` + CHECK `basis_confirmation`; `assessments.formal_preliminary` | новые столбцы; старые строки — `resume`, `false`, `[]` |
| Правило v1.3 «`met` → `unknown` при `verification ≠ resume`» отменено | **меняет итоги:** образование «по документам» по резюме даёт предварительный `met`, итог допуска снова различает кандидатов (вопрос из team-gorky-9/hr#6 закрыт решением Р4) |
| `confirm_formal_check` | новая функция: подтверждение документом, интервью или тестом — новая версия оценки, прежняя в истории |
| `params` 0.1 проверяются при создании профиля (п. 3.5.1) | **несовместимо для входа** со свободной формой (`{"min_level": …}`): такие профили больше не создаются. Загруженные данные не перепроверяются; пакеты Давида v2 и v3 и учебный профиль проходят без правок |
| Импорт: `mapping.json` → `synthetic` у записи; отчёт → `is_synthetic`; явная смена контура уже сохранённого файла → `conflict` (`CONTOUR_CONFLICT`) | новое необязательное поле; без него новый кандидат реальный, повтор остаётся в своём контуре. Пакет 0а (`py-9001`, `hr-9001`) помечен учебным |
| Загрузчик профилей: `check_stage` из пакета, `--synthetic synthetic/cases.json` | `check_stage` ушёл из полей «остались только в пакете» |

**Затронутые потребители.**
- **Илья:** выбирать профиль через `get_approved_profile`; рабочий режим — только рабочий контур, технический — учебный кандидат или учебный профиль (правка `assessment_refusal` и п. 1.1 контракта оценки — в его задаче); читать `check_stage` вместо угадывания по `verification`/`kind`; писать альтернативы в `FormalCheckIn.alternatives`, а не в `explanation`; не понижать `met` до `unknown` заранее; `basis` во входе нет. Контрольный набор `py-9001` загружается учебными кандидатами.
- **Давид:** пакет v3 и учебный профиль грузятся без правок (`--synthetic`). Свободные `params` не принимаются.
- **Ася / Денис (API):** рабочие списки — без учебных кандидатов, действующий профиль — `get_approved_profile`; учебный срез — явным параметром; поля `is_training`, `is_preliminary`, `formal_preliminary` (`api.md`).
- **Родион:** поиск не показывает учебных кандидатов в рабочей выдаче (`search-01`).

**Не входит:** результаты и основание по индикаторам, счётчики, группы повторов (`same_as`) — после методики Ильи (решение Родиона); основание у `competency_scores`.

**Как проверено:** 233 теста на PostgreSQL, в том числе `tests/test_contours.py`: утверждение по контурам в обе стороны, нумерация, выбор профиля, правила оценки для реального и учебного кандидата, триггер неизменяемости, `basis` и подтверждение с историей, CHECK `basis_confirmation`, альтернативы (полнота, противоречия, цитаты, `unknown` при подтверждённой альтернативе), `check_stage` (вход, CHECK, итог), формат `params` 0.1; тесты импорта на флаг и конфликт контура. Тесты контуров ловят ослабление: при удалённых фильтрах по контуру падают 5 из них. Миграция `0003` применена к базе с пакетом Давида v2, загруженным кодом до неё; перенос `check_stage`, откат `0003 → 0002`, повторное применение, `alembic check`. Сценарий на реальных данных (`hq/work/2026-11-20-profile-contours-and-basis/check_contours.py`): пакеты Давида v2 и v3 (`3926099`, `b62a3b2`) и учебный профиль с байтами архива «Кадры», реальный «Python-разработчик/отклик 5.txt» и пакет 0а через импорт — 16 проверок.

## 17. Изменения v1.6 — публикация отклика и внешние отклики из истории (20.11.2026, ждёт утверждения)

**Почему.** Задача `ingest-02`: «История общения с кандидатом» из резюме DOCX консультанта. Разбор архива (`hq/work/2026-11-20-ingest-02-full-corpus/plan.md` в штабе): в 226 из 229 блоков истории запись совпадает с подвалом резюме «Отклик на вакансию: «…»» — это сам отклик, а не другая должность. Настоящих внешних откликов — 24 в 4 файлах. Кроме того, папка консультанта собрана из 7 разных публикаций hh (20 откликов — на начальника отдела финконтроля, 1 — на сметчика), и без отдельного поля это сведение теряется.

| Изменение | Совместимость |
|---|---|
| `applications.posting_title` varchar(512) null — публикация hh основного отклика | новый необязательный столбец; существующие строки — `NULL` до повторного прогона импорта |
| Частичный уникальный индекс `uq_applications_history` (`candidate_id`, `external_position_title`, `applied_at`) `WHERE source = 'history'` `NULLS NOT DISTINCT` | новое ограничение; до v1.6 строк `history` не было. Требует PostgreSQL 15+ (стенд и `hr_dev` — 16) |
| `create_application(..., posting_title=None)` | новый необязательный аргумент |
| Внешние отклики не участвуют в рабочих списках и воронке (п. 4.5) | уточнение для потребителей; схема не меняется |

**Решение Дениса (20.11):** публикацию хранить отдельным столбцом, а не в `external_position_title` (иначе поле значило бы две разные вещи: «должность вне платформы» и «откуда пришёл отклик»); дубли внешних откликов запрещает база, а не только код импорта.

**Что делать потребителям:**
- **Денис (API, `backend-01`/`02`):** `vacancies/{id}/applications` внешних откликов не содержит (у них нет `vacancy_id`); `analytics/funnel` и переходы этапов — только `source = response`; `posting_title` отдавать в отклике после правки `api.md`.
- **Илья (`ai-02`):** история другого отбора — 24 строки `source = history` с `external_position_title` и `applied_at`.
- **Ася:** поле «на какую публикацию откликнулся» (после `api.md`).

**Как проверено:** миграция `0004` на `hr_dev` с архивом «Кадры» — вперёд, откат `0004 → 0003`, снова вперёд; `test_models_match_migrations`; тест на отказ базы при повторе внешнего отклика (с датой и без); 290 тестов на PostgreSQL.

## 18. Интеграция оценщика и повторов · v1.7

Миграция 0005 поверх 0004 добавляет nullable поля, не переписывая существующие версии:

| Таблица | Поле | Смысл |
|---|---|---|
| competency_indicators | same_as varchar(64) | Общий ключ повторяющихся индикаторов |
| competency_scores | details JSONB | Типизированный результат версии 1.0; null у прежних оценок |
| assessments | algorithm_version varchar(64) | Версия правил кода, отдельно от промпта |
| assessments | calculation_as_of varchar(7) | Месяц расчёта стажа YYYY-MM |

same_as проверяется до создания профиля: одна компетенция, один check_stage, нет excluded_from_scoring. Обязательность участников может различаться, обязательность группы — OR. CHECK в таблице запрещает пустую группу и исключённого участника; межстрочные условия проверяют repository и загрузчик. Полный профиль должен записываться через create_requirement_profile.

details имеет схему `app.schemas.competency_details.CompetencyDetails`: schema_version=1.0, basis=resume, check_stage=screening, indicators (key/status/evidence/ambiguous_location), groups (key/members/is_mandatory/status/manual_review), mandatory/desired (confirmed/contradicted/no_info/total), on_interview и excluded. Группа — одна единица; противоречие сильнее подтверждения, их сочетание требует ручной сверки. Интервью-группы считаются отдельно, в screening X/Y не входят.

save_assessment проверяет полный набор ключей screening-индикаторов, пересчитывает группы/счётчики, проверяет все вложенные цитаты по тексту карточки. Для confirmed/contradicted нужна цитата. level и overall_score оценщик оставляет null. Прежние callers без details поддерживаются; отсутствие старых details не превращается в нулевые счётчики. confirm_formal_check копирует details, algorithm_version и calculation_as_of в новую версию.

Контекст запуска хранится отдельно в audit_log (action=other, entity_type=assessment_run); purpose не записывается как единственное изменяемое свойство Assessment. См. [контракт применимости](profile-applicability.md). Изменение политики влияет на представление отклика, а не переписывает оценки пар.

Реальная проверка миграции 0005: применение/откат/повторное применение на затронутых таблицах PostgreSQL 18 и сохранение legacy-данных. Проверки оценщика/API — на реальной ORM-схеме без embeddings. Полный прогон цепочки 0001–0005 с pgvector остаётся отдельной проверкой; см. [отчёт](../reports/profile-assessment-integration.md).

## 19. Периоды кадрового резерва · v1.8 (20.11.2026, ждёт утверждения)

Задача backend-02: «одна действующая запись для кандидата и цели, включая два конкурентных запроса; закончился срок или отозвано основание — записи нет ни в списке, ни в фильтре поиска; возобновление требует нового основания и сохраняет историю периода».

Миграция `0006` поверх `0005`:

| Изменение | Зачем |
|---|---|
| `reserve_entries.contact_basis` text null | основание повторного контакта; `reason` остаётся обоснованием профессиональной пригодности. API требует оба поля, у прежних записей может быть null |
| `reserve_entries.ended_at` timestamptz null, `end_reason` text null, `ended_by_user_id` → `users` (SET NULL) null | как и кем закончен период |
| `status` + `expired` (CHECK пересоздан) | срок истёк; запись закрывается при новом включении на ту же цель. `withdrawn` — основание отозвано кадровиком |
| частичный уникальный индекс `uq_reserve_active_position` (`candidate_id`, `position_id`) `WHERE status = 'active' AND position_id IS NOT NULL` | одна активная запись на кандидата и должность — правило держит база, поэтому два одновременных запроса не создают дубль |
| частичный уникальный индекс `uq_reserve_active_area` (`candidate_id`, `competency_area`) `WHERE status = 'active' AND position_id IS NULL` | то же для резерва по направлению |

**Цель записи** — должность, если указана, иначе направление. Две записи на одну должность с разными направлениями считаются одной целью.

**Действующая запись** — `status = active` и `valid_until` пусто или ≥ сегодня. Запись с истёкшим сроком может оставаться `active` до следующего включения на ту же цель. Действующей она не считается: условие `active_reserve_condition` проверяет дату. Фоновое закрытие по расписанию не нужно.

**Гонка.** `reserve_candidate` ищет активную запись с `FOR UPDATE`, затем вставляет новую в точке сохранения. Если параллельная транзакция успела вставить запись, вторая вставка ждёт её commit и получает нарушение уникальности. Точка сохранения откатывается, и функция возвращает запись первой транзакции с `created = False`.

**Откат миграции** переводит `expired` в `withdrawn` (прежний CHECK его не знает) и удаляет новые поля.

**Затронутые потребители.**
- **Ася (frontend-02):** поля `contact_basis`, `status`, `ended_*` в ответах резерва.
- **Родион (search-01):** фильтр резерва — `active_reserve_condition()`.
- **Илья:** не затронут.

**Как проверено:** `test_models_match_migrations`; тесты резерва в `tests/test_selection.py` и `tests/test_api_workflow.py`. Среди них последний день срока, новый период после истечения, отзыв и детерминированная гонка двух транзакций на настоящей PostgreSQL. Вторая транзакция ждёт индекс, получает конфликт и возвращает запись первой.

## 20. Гайд интервью, ревизии ответов, рубрика ядра · v1.9 (20.11.2026, ждёт утверждения)

Задача interview-01, контракт [interview.md](interview.md) v0.4 §5 (хранение, права и HTTP подтвердил Денис). Миграция `0007` поверх `0006`. Номер может сдвинуться (`0008`/`0009`), если раньше вольются ветки workflow-01 и requirements-03, где тоже `0007`.

| Изменение | Зачем |
|---|---|
| `interviews`: частичный уникальный индекс `uq_interviews_open` (`application_id`, `kind`) `WHERE result = 'pending'` | одна открытая встреча на отклик и вид. Гайд — отдельная запись, поэтому перегенерация не создаёт ещё один «звонок» в отчётах |
| `interview_guides` (новая): `interview_id` → `interviews` CASCADE, `guide_version` ≥ 1, `assessment_id` → `assessments` CASCADE (базовая оценка сборки), `profile_id` → `requirement_profiles` CASCADE, `rubric_version`, `prompt_version`, `model_calls`, `uncovered_gaps` jsonb, `request_id` UNIQUE null, `is_migrated`, `created_by_user_id` → `users` SET NULL; UNIQUE (`interview_id`, `guide_version`); CHECK: без оценки и профиля только при `is_migrated` | версии гайда к одной встрече. `CASCADE` у оценки и профиля: при удалении кандидата его оценки и отклики удаляются разными цепочками каскада, и ссылка без `CASCADE` проверялась раньше, чем каскад от отклика доходил до гайда (найдено тестом) |
| `interview_questions`: `guide_id` → `interview_guides` CASCADE NOT NULL, `kind` (`core`/`clarification`), `gap_ref_id`, `criterion` jsonb, `sources` jsonb, `requirement_id`, `indicator_key`, `rubric_question_id`, `carried_from_question_id`; частичный UNIQUE `uq_interview_questions_gap` (`guide_id`, `gap_ref_id`); CHECK `kind = 'core'` ⇔ есть рубрика и нет `gap_ref_id` | вопрос принадлежит версии гайда. Перенесённый вопрос показывает ответ прежней версии. `answer_notes` больше не пишется |
| `interview_answers` (новая): `question_id` → CASCADE, `revision` ≥ 1, `text`, `source` (`phone`/`in_person`/`written`/`unknown`), `author_user_id` → `users` RESTRICT, `previous_answer_id`, `request_id` UNIQUE null; UNIQUE (`question_id`, `revision`); CHECK: автор и `request_id` пусты только при `source = 'unknown'` | ревизии ответа, строки только добавляются. Две правки одной ревизии — одна вставка проходит, вторая получает конфликт |
| `interview_rubric_questions` (новая): `profile_id` → CASCADE, `row_key`, ровно одно из `requirement_id`/`indicator_key`, `question`, `criterion`, `author`, `status` (`draft`/`approved`), `version`, `approved_by_user_id`, `approved_at`; UNIQUE (`profile_id`, `row_key`); CHECK: `approved` ⇔ есть кто и когда | ядро — одно на версию профиля. Первая генерация двумя запросами — `INSERT … ON CONFLICT DO NOTHING` и перечтение |
| `assessments.base_assessment_id` → `assessments` null; `confirm_request_id` UNIQUE null; CHECK: ключ подтверждения только вместе с базовой | версия из `confirm_formal_check` ссылается на последнюю версию модели. По ней гайд не устаревает после подтверждения. Ключ запроса делает повтор подтверждения идемпотентным |
| `formal_checks.source_answer_id` → `interview_answers` NO ACTION null; CHECK: только при `basis <> 'resume'` | на какой ответ опирался кадровик. `NO ACTION` проверяется в конце оператора: удаление кандидата целиком проходит, удаление отдельного ответа, на который ссылается подтверждение, отклоняется |

**Перенос.** Каждая прежняя встреча получает гайд версии 1 с `is_migrated = true` без оценки, её вопросы привязываются к нему как `clarification`. Непустой `answer_notes` становится ревизией 1 с `source = unknown` без автора. Прежние версии оценки, где есть строка не по резюме, получают `base_assessment_id` — ближайшую предыдущую версию пары, где все строки по резюме. **Откат** возвращает последнюю ревизию в пустой `answer_notes` и удаляет вопросы гайдов, созданных после миграции.

**Функции `repository`** (не делают commit):
- `open_interview` — открытая встреча или новая, через `ON CONFLICT`;
- `save_interview_guide` → `(гайд, created)` — повтор `request_id` и гонка номера версии возвращают существующий гайд;
- `save_rubric_questions`, `rubric_for_profile`, `rubric_fingerprint`;
- `add_interview_answer` → `(ответ, created)` — проверки по порядку: повтор, принадлежность вопроса, последняя версия гайда, ожидаемая ревизия, вставка в точке сохранения;
- `visible_answer`, `question_answers`;
- `allowed_bases(verification)`, `is_preliminary` по матрице оснований;
- `confirm_formal_check(..., answer_id, request_id)` и `find_confirmation`.

Ошибки с кодом API — `RuleConflict(code, details, not_found)`, наследник `RepositoryError`.

**Затронутые потребители.**
- **Илья:** `app.interview.build_guide` вызывается только на чтение (`record_calls=False`), журнал вызовов пишет HTTP.
- **Ася:** DTO гайда и ответов — `api.md` §4.
- **Родион (qa):** `hr_dev` и стенд — `alembic upgrade head`.
- **Отчёты о звонках:** одна встреча на звонок, как раньше.

**Как проверено:**
- `test_models_match_migrations`;
- `tests/test_api_interview.py` на PostgreSQL;
- скрипт штаба `hq/work/2026-11-20-interview-01-storage-http/check_migration_0007.py`: перенос встречи, заметки и базовой оценки, откат, повторный подъём, `alembic check`.
