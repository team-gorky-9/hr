# Модуль «База данных»

Где хранятся данные платформы и как с ними работать. Код — `app/db/`, форматы JSON-полей — `app/schemas/`, миграции — `migrations/`.

**Статус:** каркас реализован и проверен на PostgreSQL 16 + pgvector 0.6.2. Схема — предложение до согласования контракта (см. «Что согласовать»).

## Принципы

1. **Три слоя данных о кандидате.** Исходный файл (`source_documents`) не меняется → очищенный от персональных данных текст (`candidate_texts`) → извлечённая карточка (`candidate_cards`). Модель видит только очищенный текст; цитаты-доказательства ссылаются на него.
2. **Персональные данные отдельно** (`candidate_pii`). Читаются только через `repository.get_candidate_pii`, каждое чтение пишется в `audit_log` с целью. Так работает слепой режим и учёт по 152-ФЗ.
3. **Все версии результатов ИИ хранятся** (`version`, `is_current`, модель, версия промпта) для карточек, текстов и оценок. Уникальный частичный индекс гарантирует одну текущую версию.
4. **Карточка — гибрид:** документ JSONB по схеме `CandidateCard` (Pydantic, лишние поля запрещены) + столбцы и таблица `candidate_skills` для фильтров.
5. **Доказательство = цитата + позиция в очищенном тексте.** `save_assessment` отклоняет цитату, которой нет в тексте этого кандидата ровно на указанном месте.
6. **Формальные требования отдельно от компетенций.** Итог по обязательным требованиям считает код (`not_met` > `unknown` > `met`), модель его не задаёт.
7. **Решение принимает человек.** Оценка ИИ (`assessments`) не меняет этап отбора. Этап меняет только `move_application`, с автором и комментарием.

## Таблицы

| Область | Таблицы | Кто пишет |
|---|---|---|
| Источники | `source_documents` | импорт |
| Кандидат | `candidates`, `candidate_pii`, `candidate_texts` | импорт |
| | `candidate_cards`, `candidate_skills` | извлечение карточки (ИИ) |
| Должности | `positions`, `vacancies` | справочник (`app/db/seed.py`), кадровик |
| Требования | `requirement_profiles` → `formal_requirements`, `competencies` → `competency_indicators` | модуль матриц компетенций, утверждает кадровик |
| Оценка | `assessments` → `formal_checks`, `competency_scores` | ИИ-скоринг через `save_assessment` |
| Отбор | `applications`, `stage_events` (журнал), `selection_stages`, `rejection_reasons` (справочники) | импорт создаёт отклик, кадровик двигает этапы |
| | `interviews`, `interview_questions`, `department_feedback` | кадровик, департамент, генерация вопросов |
| Резерв | `reserve_entries` | кадровик |
| Поиск | `embeddings` | модуль поиска |
| Доступ | `users`, `audit_log` | API |

Связи по смыслу:

```
source_documents 1─1 candidates 1─1 candidate_pii
                     candidates 1─N candidate_texts 1─N candidate_cards 1─N candidate_skills
                                                   └─N embeddings
positions 1─N vacancies
positions 1─N requirement_profiles 1─N formal_requirements
                                   1─N competencies 1─N competency_indicators
candidates × requirement_profiles → assessments 1─N formal_checks, competency_scores
candidates × vacancies → applications 1─N stage_events, interviews, department_feedback
candidates 1─N reserve_entries (на должность или направление)
```

Отдельные решения:
- **Одна запись `candidates` на резюме.** Склейка дублей одного человека — позже, отдельной таблицей: в IT-данных «Кандидат №N» нумеруется внутри папки вакансии, сопоставить людей не по чему.
- **`applications.vacancy_id` может быть пуст** для откликов на должности вне платформы (строки «История общения с кандидатом» в резюме консультанта), тогда заполнено `external_position_title`.
- **Резерв — не этап отбора:** кандидат может получить отказ на вакансию и остаться в резерве.
- **Оценка привязана к «кандидат × версия требований»,** а не к отклику: скоринг идёт по всем должностям.
- **Вектор без фиксированной размерности** (`vector`) + столбец `model`. Поиск обязан фильтровать по модели. HNSW-индекс требует фиксированной размерности — добавляется миграцией после выбора модели эмбеддингов.
- **Порядок журналов — по `seq`** (identity), а не по `created_at`: `now()` в PostgreSQL одинаков внутри транзакции.
- **Перечисления — строки с CHECK**, а не нативные ENUM: новое значение добавляется простой миграцией. Справочники, которые пополняет кадровик (этапы, причины отказа), — таблицы.

## Функции доступа (`app/db/repository.py`)
 Ссылки на записи передаются как UUID (`candidate_id`, `application_id`…), а не ORM-объекты; полные сигнатуры — `docs/contracts/database.md`, раздел 7.
Функции не делают `commit` — транзакцией управляет вызывающий. Нарушение правил — исключение `RepositoryError` (`StageTransitionError`, `EvidenceError`).

| Функция | Для кого | Что делает |
|---|---|---|
| `add_source_document` | импорт | сохраняет файл; повтор по SHA-256 возвращает существующий; путь в NFC |
| `create_candidate` | импорт | кандидат + ПДн + очищенный текст v1 |
| `add_candidate_text`, `get_current_text` | импорт | новая версия очищенного текста |
| `create_application` | импорт, API | отклик на вакансию или внешнюю должность, этап «Новый отклик» в журнале |
| `add_candidate_card`, `get_current_card` | ИИ | версия карточки + навыки |
| `save_assessment` | ИИ | версия оценки; проверка цитат и принадлежности требований профилю |
| `find_candidates_by_skills` | поиск, API | по навыкам текущих карточек (все / любой) |
| `move_application`, `stage_history` | API | переход этапа с блокировкой строки; запрет переходов из финального этапа |
| `record_department_feedback` | API | обратная связь департамента; этап не меняет |
| `add_to_reserve`, `reserve_for_position` | API | резерв без дублей, с учётом срока |
| `get_candidate_pii`, `write_audit` | API | чтение ПДн с записью в журнал |

`app/db/seed.py` — этапы, причины отказа, 6 должностей и по вакансии hh.ru на каждую; `POSITION_CODE_BY_FOLDER` сопоставляет папку архива организаторов с должностью.

## Что согласовать (отличия от черновика контракта в `project-context.md`)

- Период работы: вместо строки `"period": "2024-12 — сейчас"` поля `start`/`end` в формате `YYYY-MM` и `is_current`.
- `id`, `source`, `raw_text` не входят в JSON карточки: это столбцы таблиц `candidates`, `source_documents`, `candidate_texts`.
- Добавлены поля карточки `headline`, `courses`, `about`, `cover_letter`; в `education` — `institution`, `faculty`.
- Схема БД целиком (этот документ) — часть контракта по `project-context.md`.

## Ограничения и открытые вопросы

- Очистку ПДн делает импорт. В IT-откликах персональные данные остались: ссылки на GitHub с именем, глаголы в женском роде (`Python-разработчик/отклик 5.txt`).
- Размерность эмбеддингов YandexGPT не проверена; выбор модели и индекса — модуль поиска.
- Входят ли сотрудники департаментов в систему — неизвестно; `users.role` это допускает.
- Хранить ли на стенде даты рождения из резюме консультанта — вопрос к организаторам.
- `docker-compose.yml` не запускался: на машине разработки нет Docker. Проверка шла на локальном PostgreSQL 16.2 + pgvector 0.6.2; в compose — образ `pgvector/pgvector:pg17`.
