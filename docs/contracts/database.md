# Контракт: база данных

**Версия:** 1.3 (проект) · **Дата:** 2026-11-19 · **Статус:** v1.0 утверждена Родионом 19.11.2026; изменения v1.1 (раздел 12), v1.2 (раздел 13) и v1.3 (раздел 14) ждут утверждения
**Автор:** Денис (бэкенд и база) · **Реализация:** v1.0 — team-gorky-9/hr#1, миграция `0001`; v1.1 — team-gorky-9/hr#4, миграция `0002`; v1.2 — team-gorky-9/hr#5, без миграции; v1.3 — ветка `docs/database-contract-review`, без миграции

Контракт описывает, как платформа хранит данные и как другие модули их пишут и читают. По правилам команды схема базы входит в контракт и меняется только по согласованию с Родионом. Версия 1.0 утверждена, модули опираются на неё; правки v1.1–v1.3 действуют в `main`, но ждут утверждения. Каждая правка вносится этим же файлом вместе с кодом, тестами и, если меняется схема, миграцией (раздел 9).

**Происхождение пунктов:** **[Д]** — решение Дениса (обсуждение 19.11); **[Ч]** — из черновика контракта в `docs/project-context.md` штаба; **[А]** — предложение агента, выбор делегирован Денисом. Пометка стоит у решений, а не у очевидных полей.

## 1. Кто пользуется

| Модуль | Пишет | Читает |
|---|---|---|
| Импорт | `source_documents`, `candidates`, `candidate_pii`, `candidate_texts`, `applications` | справочники, `positions`, `vacancies` |
| Извлечение карточки, скоринг (Илья) | `candidate_cards`, `candidate_skills`, `assessments`, `formal_checks`, `competency_scores`, `interview_questions` | `candidate_texts`, требования должности |
| Матрицы компетенций (Давид) | `requirement_profiles`, `requirement_profile_sources`, `formal_requirements`, `competencies`, `competency_indicators` — через `create_requirement_profile` | `positions`, `source_documents` (ДИ, матрица, вакансия) |
| Поиск (Родион) | `embeddings` | `candidate_texts`, `candidate_cards`, `candidate_skills`, `reserve_entries` |
| API и интерфейс (Ася) | `stage_events`, `interviews`, `department_feedback`, `reserve_entries`, `users`, `audit_log`, утверждение требований (`approve_requirement_profile`) | всё, ПДн — только через `get_candidate_pii` |

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

В одной оценке каждое требование и каждая компетенция встречаются не больше одного раза: повтор `save_assessment` отклоняет [v1.3]. Поле `verification` требования (п. 3.6) на итог не влияет: код смотрит только на `is_mandatory` и `result`. Если требование подтверждается документами, а в резюме о нём есть сведения, скоринг может поставить `met` по резюме. Окончательная проверка по документу остаётся за кадровиком. Учитывать ли `verification` при подсчёте `formal_result` — открытый вопрос к скорингу (Илья).

**2.7. Решение принимает человек [Д][Ч].** Оценка ИИ не меняет этап отбора. Этап меняет только `move_application`, а в журнал пишется, кто это сделал. Обратная связь департамента (`record_department_feedback`) этап тоже не меняет.

**2.8. Транзакции [А].** Функции доступа не делают `commit`. Транзакцией управляет вызывающий (скрипт импорта, обработчик запроса), поэтому несколько шагов сохраняются вместе или не сохраняются вовсе.

**2.9. Идентификаторы [Д].** Первичный ключ — UUID v4. Его ставит приложение, а при вставке через SQL — база (`gen_random_uuid()`). У кандидата есть читаемый `code`, уникальный, до 32 символов. Формат: `<префикс должности>-<номер отклика из 4 цифр>`, например `py-0005` (п. 11.2).

**2.10. Даты и время.** Момент времени — `timestamptz`, в JSON ISO 8601 со смещением: `2026-11-19T15:03:24+03:00`. Дата — `date`, `2026-08-25`. Месяц в карточке — строка `2024-05`.

**2.11. Позиции цитат — в символах [А].** `start`/`end` — индексы символов Unicode (кодовых точек), как срез строки Python `text[start:end]`, а не байты UTF-8. В JavaScript строки считаются в единицах UTF-16, и символ вне BMP (эмодзи и т. п.) занимает две единицы. После такого символа `start`/`end` в JS указывают не туда. В архиве «Кадры» такие символы есть в 54 из 1 434 TXT-откликов [v1.3]. Поэтому база и API отдают индексы кодовых точек, а интерфейс сам переводит их перед подсветкой: `Array.from(text).slice(start, end).join("")` или пересчёт `start` в позицию UTF-16. Проверочный пример для интерфейса: в строке `"😀 Python"` цитата `Python` имеет `start = 2`, `end = 8`, а в UTF-16 — `3` и `9`.

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
| `experience_years` | число \| null, 0–80 | нет | общий стаж в годах, один знак после запятой |
| `experience` | список `Experience` | нет, `[]` | места работы |
| `skills` | список `Skill` | нет, `[]` | навыки |
| `languages` | список `Language` | нет, `[]` | языки |
| `about` | строка \| null | нет | раздел «Обо мне» |
| `cover_letter` | строка \| null | нет | сопроводительное письмо |
| `missing` | список строк | нет, `[]` | каких сведений не хватает для оценки |
| `pii_hidden` | bool | нет, `true` | ПДн из п. 11.7 убраны из карточки и текста; город и гражданство могут остаться (п. 11.8) |

- `Education`: `level`, `degree`, `institution`, `faculty`, `field` (строки или null), `year` (целое 1950–2100 или null).
- `Course`: `title` (обязательно), `organization`, `year`.
- `Experience`: `position`, `organization`, `start`, `end` (месяц `YYYY-MM` или null), `is_current` (bool, по умолчанию false), `duties` (список строк). Правила: `end >= start`; при `is_current = true` поле `end` пустое.
- `Skill`, `Language`: `name` (непустая строка), `level` (строка или null).

### 3.2. Доказательство — `Evidence`

```json
{"candidate_text_id": "<uuid>", "quote": "<дословная цитата>", "start": 473, "end": 511}
```

Правила: `quote` непустая строка; `start >= 0`; `end - start == len(quote)`. Если `candidate_text_id` указывает на старую версию текста кандидата, цитата сверяется с ней. Совпадение версии текста цитаты с текстом карточки (`candidate_cards.candidate_text_id`) не проверяется [v1.3]. Скоринг должен брать цитаты из того же текста, из которого извлечена карточка, иначе подсветка покажет другую версию резюме.

### 3.3. Персональные данные — `PiiData` (вход `create_candidate`)

`full_name`, `gender`, `phone`, `email`, `city`, `citizenship` — строки или null; `birth_date` — дата или null; `age` — целое 14–100 или null; `links` — список строк; `extra` — объект для прочего персонального (например, желаемая зарплата). `city` и `citizenship` необязательны: импорт их не заполняет, потому что город и гражданство остаются в очищенном тексте (п. 11.8). Поля сохранены, чтобы не менять схему.

### 3.4. Результат оценки (вход `save_assessment`)

- `FormalCheckIn`: `requirement_id` (uuid), `result` (`met` | `not_met` | `unknown`), `explanation` (строка или null), `evidence` (список `Evidence`).
- `CompetencyScoreIn`: `competency_id` (uuid), `level` (целое 0–100 или null, где null значит «нет сведений»), `explanation`, `evidence`.

### 3.5. Прочие JSONB-поля

| Поле | Формат |
|---|---|
| `formal_requirements.params` | объект условий (вход — `FormalRequirementIn`, п. 3.6), например `{"min_level": "высшее", "fields": ["Юриспруденция", "ГМУ"], "retraining_allowed": true}`. Схема свободная; ключи договаривают модуль матриц и скоринг |
| `formal_checks.evidence`, `competency_scores.evidence` | список `Evidence` |
| `department_feedback.confirmed_competencies` | список кодов компетенций: `["ИТК", "РК"]` |
| `candidate_pii.links` | список строк; `candidate_pii.extra` — объект |
| `audit_log.details` | объект, для `view_pii` — `{"purpose": "<цель>"}` |

### 3.6. Профиль требований (вход `create_requirement_profile`) [v1.1]

Один формат для всех должностей: условия допуска + компетенции с индикаторами. Схемы — `app/schemas/requirements.py`.

- Ключ и происхождение строки (общие поля `FormalRequirementIn`, `CompetencyIn`, `IndicatorIn`): `key` — устойчивый ключ строки в пакете (до 64 символов без пробелов: `hr.education.level`, `py.di.P106`), уникален в профиле и не меняется между версиями; `origin` — `source` | `team`; `source_refs` — список `SourceRefIn`; `note`. Правило: при `source` нужна хотя бы одна ссылка; при `team` — обоснование в `note`.
- `SourceRefIn`: `source_document_id` (uuid, документ из `sources` профиля), `address` (до 256 символов: `п. 2.2.1`, `разд. 7, второй критерий; OOXML P201`, `ИТК, инд. 2`), `quote` (дословно). Строка может ссылаться на несколько документов: строка матрицы и пункт ДИ.
- `AcceptanceIn` (поле `acceptance` условия и индикатора): `met`, `not_met`, `unknown`, `limit` — строки или null: что считать выполнением, явным невыполнением, нехваткой сведений и чем ограничен вывод.
- `ProfileSourceIn`: `source_document_id`, `role` (`job_description` | `competency_matrix` | `vacancy_posting` | `regulation` | `other`), `observed_revision` (строка или null: `1.2 от 01.02.2024`), `is_primary` (bool).
- `FormalRequirementIn`: `kind`, `description`, `params` (объект, по умолчанию `{}`), `is_mandatory` (по умолчанию true), `verification`, `acceptance`.
- `CompetencyIn`: `code` (до 32), `name`, `rank` (или null), `target_level_min`, `target_level_max` (оба null или оба 0–100, min ≤ max), `indicators` — не пустой список `IndicatorIn`.
- `IndicatorIn`: `text`, `is_mandatory` (по умолчанию true; false — «будет преимуществом»), `verification`, `acceptance`, `excluded_from_scoring` (по умолчанию false: строка хранится ради прослеживаемости, но в оценку не входит).

`verification` — где подтверждается требование: `resume`, `documents` (диплом, трудовая книжка), `interview` (личные качества, знание законов), `test` (практическое задание).

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
| `education_level` | varchar(64) | да | `education[0].level` |
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
| `version` | integer | нет | unique вместе с `position_id` |
| `status` | `draft` \| `approved` \| `archived`, по умолчанию `draft` | нет | **утверждённая — одна на должность** (частичный уникальный индекс) |
| `is_synthetic` | bool, по умолчанию false | нет | учебный профиль; утвердить нельзя |
| `created_by` | varchar(128) | нет | логин или имя модели |
| `approved_by_user_id` | → `users` (SET NULL) | да | |
| `approved_at` | timestamptz | да | |
| `approval_basis` | text | да | основание утверждения: «распоряжение № …» |
| `note` | text | да | |

**`requirement_profile_sources`** — документы версии профиля: `profile_id` → (CASCADE); `source_document_id` → `source_documents` (RESTRICT); `role` (`job_description` | `competency_matrix` | `vacancy_posting` | `regulation` | `other`); `observed_revision` varchar(128) null — редакция, видная в документе; `is_primary` bool. Пара (`profile_id`, `source_document_id`) уникальна.

**Ключ и происхождение строки** — одинаковые столбцы у `formal_requirements`, `competencies`, `competency_indicators`: `key` varchar(64) — unique в профиле (у индикаторов — в компетенции; уникальность по всему профилю проверяет `create_requirement_profile`); `origin` `source` | `team`; `source_refs` jsonb, по умолчанию `[]` — список `{source_document_id, address, quote}`; `note` text null. CHECK `row_source`: при `source` список не пуст, при `team` заполнен `note`. Документы ссылок должны быть среди `requirement_profile_sources` профиля (проверяет `create_requirement_profile`). По `key` пакет сопоставляется с UUID строк базы.

**`formal_requirements`** — условие допуска: `profile_id` → `requirement_profiles` (CASCADE); `kind` `FormalRequirementKind`; `description` text; `params` jsonb (п. 3.5); `is_mandatory` bool, по умолчанию true; `verification` `VerificationMethod`; `acceptance` jsonb `{}` (`AcceptanceIn`); ключ и происхождение; `sort_order` smallint. Столбец `source_quote` v1.0 заменён на `source_refs`.

**`competencies`** — группа индикаторов: `profile_id` → (CASCADE); `code` varchar(32), unique в профиле (`ПАК`, `ИТК`, `PY-DB`); `name`; `rank` `key` | `basic` | `special` **или null**; `target_level_min`, `target_level_max` smallint **или оба null**, иначе `0 <= min <= max <= 100` («90–100 процентов» → 90 и 100); происхождение; `sort_order`.

**`competency_indicators`** — проверяемое требование: `competency_id` → (CASCADE); `text`; `is_mandatory` bool, по умолчанию true; `verification` `VerificationMethod`; `acceptance` jsonb `{}`; `excluded_from_scoring` bool, по умолчанию false; ключ и происхождение; `sort_order`.

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
| `overall_score` | smallint 0–100 | да | итог по компетенциям |
| `summary` | text | да | |

**`formal_checks`**: `assessment_id` → (CASCADE); `requirement_id` → `formal_requirements` (CASCADE); `result`; `explanation` null; `evidence` jsonb `[]`.

**`competency_scores`**: `assessment_id` → (CASCADE); `competency_id` → `competencies` (CASCADE); `level` smallint 0–100 null; `explanation` null; `evidence` jsonb `[]`.

### 4.5. Отбор [Д]

**`applications`** — участие кандидата в отборе.
| Столбец | Тип | Null | Смысл |
|---|---|---|---|
| `candidate_id` | → `candidates` (CASCADE) | нет | |
| `vacancy_id` | → `vacancies` (CASCADE) | да | пусто для внешней должности |
| `external_position_title` | varchar(512) | да | должность вне платформы (из «Истории общения с кандидатом») |
| `source` | `response` \| `history` \| `manual` | нет | |
| `applied_at` | date | да | |
| `current_stage_code` | → `selection_stages.code` | нет | текущий этап |
| `created_at`, `updated_at` | timestamptz | нет | |

Ограничения: заполнено `vacancy_id` или `external_position_title` (CHECK); пара (`candidate_id`, `vacancy_id`) уникальна, если вакансия указана.

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
| `VerificationMethod` [v1.1] | `resume`, `documents`, `interview`, `test` |
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
| `create_candidate(code, source_document_id, redacted_text, redaction_method, headline=None, pii=None) → Candidate` | кандидат, ПДн (если переданы), текст версии 1. Если тот же файл пришёл в папке другой вакансии, второго кандидата не создают: импорт находит кандидата по документу и добавляет ему отклик (`docs/modules/ingest.md`, «Статусы и дубли») | нет документа, документ не `resume` → `RepositoryError`; повтор `code` или документа → `IntegrityError` |
| `add_candidate_text(candidate_id, text, redaction_method)` / `get_current_text(candidate_id)` | новая текущая версия текста / текущий текст или `None` | — |
| `add_candidate_card(candidate_id, card, extractor, prompt_version=None, candidate_text_id=None)` | новая текущая версия карточки; навыки из `card.skills` нормализованы и без дублей | нет текста, или текст другого кандидата → `RepositoryError` |
| `get_current_card(candidate_id)` | текущая карточка или `None` | — |
| `find_candidates_by_skills(skills, match_all=True) → [Candidate]` | по текущим карточкам: все навыки или хотя бы один; сортировка по `code` | — |
| `create_requirement_profile(position_id, created_by, formal_requirements, competencies, sources=(), version=None, is_synthetic=False, note=None) → RequirementProfile` [v1.1] | черновик профиля (п. 3.6); порядок строк → `sort_order`; без `version` — следующий номер для должности | нет должности или документа, документ ссылки не в `sources`, документ в `sources` дважды, повтор ключа строки или кода компетенции → `RepositoryError`; повтор (`position_id`, `version`) → `IntegrityError` |
| `approve_requirement_profile(profile_id, approved_by_user_id, approval_basis) → RequirementProfile` [v1.1] | черновик → `approved`; прежняя утверждённая версия должности → `archived`; `approved_at` = время транзакции | не черновик, учебный профиль, пользователь не активный `hr`/`admin`, пустое основание → `RepositoryError` |
| `save_assessment(candidate_id, profile_id, card_id, model, formal_checks, competency_scores, overall_score=None, summary=None, prompt_version=None)` | новая текущая версия оценки; `formal_result` считает код (п. 2.6) | профиль в архиве [v1.1], карточка чужая, требование или компетенция из другого профиля, одно требование или компетенция дважды [v1.3] → `RepositoryError`; цитата не на месте или из чужого текста → `EvidenceError` |
| `create_application(candidate_id, source, vacancy_id=None, external_position_title=None, applied_at=None, actor_user_id=None)` | этап `new` и первое событие журнала | нет ни вакансии, ни внешней должности → `RepositoryError`; повтор на ту же вакансию → `IntegrityError` |
| `move_application(application_id, to_stage_code, actor_user_id=None, comment=None, rejection_reason_code=None) → StageEvent` | блокирует строку отклика (`SELECT … FOR UPDATE`), меняет этап и пишет событие. Порядок этапов не проверяется: из любого нефинального этапа можно перейти в любой другой, в том числе назад и сразу в `hired`. Причина при `rejected` необязательна [v1.3, открытый вопрос к интерфейсу] | нет такого отклика, нет такого этапа, тот же этап, отклик уже в финальном этапе, причина отказа не при `rejected`/`withdrawn`, неизвестная причина → `StageTransitionError` |
| `stage_history(application_id) → [StageEvent]` | события по `seq` | — |
| `record_department_feedback(application_id, outcome, …)` | сохраняет обратную связь, этап не меняет | неизвестная причина отказа → `RepositoryError` |
| `add_to_reserve(candidate_id, position_id=None, competency_area=None, source_application_id=None, reason=None, added_by_user_id=None, valid_until=None)` | при активной записи на ту же должность или направление возвращает её, дубль не создаётся | нет ни должности, ни направления → `RepositoryError` |
| `reserve_for_position(position_id, today=None) → [ReserveEntry]` | активные записи на должность с неистёкшим сроком; резерв «по направлению» сюда не входит | — |
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

**3. Оценка** (`save_assessment`) по профилю `python-dev` (создан `create_requirement_profile`, учебный) с требованием «Высшее образование» и компетенцией `BACKEND`:

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

Проверено запуском: v1.0 — 41 тест (team-gorky-9/hr#1) и `scripts/smoke_real_candidate.py` на этом отклике; v1.1 — 59 тестов (team-gorky-9/hr#4) и тот же скрипт; v1.3 — 108 тестов на PostgreSQL (вместе с тестами импорта).

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

**Почему.** После v1.1 и v1.2 контракт сверили с `main` (`1e1f654`): моделями, миграциями `0001`–`0002`, `repository.py`, импортом и архивом «Кадры». Найдены места, где текст обещает не то, что делает код, и одно правило, которого не было.

| Изменение | Совместимость |
|---|---|
| `save_assessment` отклоняет одно требование или компетенцию дважды в одной оценке (п. 2.6, раздел 7). Раньше сохранялись обе строки, а `formal_result` считался по последней | новое правило в функции, схема не меняется. Вызовы без повторов работают как раньше |
| Раздел 1: таблицы без функции записи и кто её добавит | только текст |
| Раздел 4, «Удаление»: в рабочей базе записи не удаляют; `reserve_entries.position_id` (SET NULL) на деле запрещает удаление должности | только текст, схема не меняется. Поведение закреплено тестом |
| П. 2.11: обязанность интерфейса переводить индексы кодовых точек в UTF-16, пример | только текст |
| П. 2.1, 2.2, `pii_hidden`, раздел 13: город и гражданство — ПДн, которые не вычищаются, а не «не ПДн» | только текст |
| П. 2.6: `verification` не влияет на `formal_result`; п. 3.2: цитата может быть из другой версии текста, чем карточка; раздел 7: порядок этапов не проверяется; повтор файла в другой папке решает импорт | описано текущее поведение, код не менялся |
| Шапка, вступление, раздел 8: номера PR и число тестов | только текст |

**Затронутые потребители.** Илья — повтор строки в `save_assessment` теперь ошибка; открыт вопрос про `verification` в `formal_result` и про версию текста цитат. Ася — пересчёт индексов цитат (п. 2.11); открыт вопрос про порядок этапов и обязательную причину отказа; функции для интервью, пользователей и резерва — в её задачах. Родион — функция записи `embeddings` в задаче поиска.

**Не входит, решается отдельно:**
- Уникальность (`assessment_id`, `requirement_id`) и (`assessment_id`, `competency_id`) в самой базе — миграцией, если понадобится запись в обход функции.
- Замена `CASCADE`/`SET NULL` на `RESTRICT` — миграцией, если правило «не удалять» нужно держать базой, а не договорённостью.
- Ограничение переходов между этапами — после ответа интерфейса.

**Как проверено:** 108 тестов на PostgreSQL, в том числе новые `test_same_requirement_twice_is_rejected`, `test_same_competency_twice_is_rejected` и `test_position_with_reserve_cannot_be_deleted`. Пример п. 2.11 посчитан в Python. Число файлов с символами вне BMP получено прогоном по TXT-откликам архива «Кадры».
