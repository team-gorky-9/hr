# Реестр проверок, тестов и бенчмарков

Документ сводит **все зафиксированные в репозитории `hr`** результаты автотестов, живых и контролируемых проверок YandexGPT, бенчмарка поиска, прогонов на реальном архиве «Кадры» и сквозных HTTP-протоколов волн 1–6.

**Принцип честности данных:** приведены только фактически выполненные замеры из [`docs/reports/`](reports/) и [`docs/modules/`](modules/). Для каждого замера указаны дата, коммит/база кода, область проверки (`scope`) и явные ограничения. Цифры разных прогонов не складываются между собой.

---

## 1. Полные прогоны pytest на PostgreSQL + pgvector (ядро `app/`)

База данных ядра (`app/`) тестируется на настоящей PostgreSQL с расширением `pgvector` (тесты пересоздают схему `public` в выделенной БД с суффиксом `_test` и прогоняют миграции Alembic).

| Дата | Проверенный коммит / база | Результат pytest | Время | Среда БД и Python | Миграции | Источник | Ограничения (`scope`) |
|---|---|---|---|---|---|---|---|
| 20.11.2026 | `6c5f9ba` (`feature/profile-assessment-integration`) | **570 passed**, 3 subtests, **0 skipped**, 0 failed | 16,12 с | Windows x64, PostgreSQL 16.15, pgvector 0.8.6 | `0001`–`0005` (upgrade → check → downgrade base → upgrade → check) | [`pgvector-full-2026-11-20.md`](reports/pgvector-full-2026-11-20.md), [JSON](reports/pgvector-full-2026-11-20.json) | Нативный PG 16 под Windows (не Docker PG 17); без живых вызовов YandexGPT |
| 20.11.2026 | `61c1957` (база `42ef738`, `requirements-01`) | **684 passed**, 1 skipped, 3 subtests, 0 failed | 45,52 с | Windows, PostgreSQL 16.15, pgvector 0.8.6 | актуальные до `0006` | [`requirements-01-integration.md`](reports/requirements-01-integration.md), [JSON](reports/requirements-01-integration.json) | 1 пропуск — JS SDK отчётности (нет Node.js в среде); без живой LLM и Docker |
| 20.11.2026 | `fec6bd2` + `requirements-02` (прогон `ea7157eb`) | **718 passed**, 1 skipped, 3 subtests, 0 failed | 50,95 с | Windows, Python 3.13, PostgreSQL 16.15, pgvector 0.8.6 | `0001`–`0006` (полный цикл в обе стороны + `alembic check`) | [`requirements-02-six-profiles.md`](reports/requirements-02-six-profiles.md), [JSON](reports/requirements-02-six-profiles.json) | 1 пропуск — JS SDK (нет Node.js); рабочие профили не утверждались; без живой LLM. Ранее в прогоне `6cc99de3` зафиксирован однократный Windows `PermissionError` в конкурентном тесте файлов отчётности (на повторе прошёл) |
| 20.11.2026 | `279c460` (база `e4910e2`, `requirements-03`) | **831 passed**, 1 skipped, 3 subtests, 0 failed | 49,34 с | PostgreSQL 16.15, pgvector 0.8.6, Python 3.13.17 | `0001`–`0007` (`0007_posting_sources`, полный цикл + `alembic check`) | [`requirements-03-verification.md`](reports/requirements-03-verification.md), [JSON](reports/requirements-03-verification.json) | 1 пропуск — `test_node_sdk_against_uvicorn` (нет Node.js); модель в интеграционных тестах — `FakeLLMClient` |
| 21.11.2026 | `0a20c84` → `ec0a764` → `802a8f7` → `3fd9a0e` → `3755b5f` → `22df231` → `ad769f6` (`wave-2` → `wave-4c`) | Прогрессия полного набора `uv run pytest`: **878 → 881 → 884 → 887 → 890 → 893 → 898 passed**, **0 skipped**, 0 failed | — | PostgreSQL 16 + pgvector | `0010`–`0013` (`alembic check` чистый) | [`wave-2-interview-outcome.md`](reports/wave-2-interview-outcome.md), [`wave-3a`…`3c`](reports/wave-3c-vacancy-suggestions.md), [`wave-4a`…`4c`](reports/wave-4c-planning-snapshot.md) | Прогоны выполнены на ветках волн 2–4C до миграций `0014`–`0015`; без живых вызовов LLM |

---

## 2. Контролируемые и живые кейсы ИИ-оценки (YandexGPT и контрольные фикстуры)

### 2.1. 41 кейс формальной оценки (`scripts.replay_requirement_cases`)

Набор из 41 синтетического случая закреплён криптографическим хешем `fixture_sha256 = 9ec1753df3e962945a4241a189ab602cf8c64d4eb0fe960ae3b413f457f4a6d9` (включает 2 случая неизвестного правила, отклоняемых кодом до обращения к модели). Эталонный ответ в промпт живой модели **не передаётся**.

| Прогон | Дата | Режим | Версия алгоритма / промпта | Итог | Ошибки LLM | Отчёт | Что именно подтверждает и границы |
|---|---|---|---|---:|---:|---|---|
| Исторический базовый живой прогон | 20.11.2026 | `live` (YandexGPT) | `assessment-2.0` / `assess-v2` | **36 / 41** | — | [`formal-extraction-unknown-status.md`](reports/formal-extraction-unknown-status.md) | Выявил сбой `alternatives[1].status = unknown` вместо `no_info` на `py-education-unknown` (3/3 сбоя до правки → **3/3 ожидаемых `unknown`** после нормализации границы `assessment-2.0.1`) |
| Контролируемый прогон до PR #15 | 20.11.2026 | `controlled` | `assessment-2.0` / `assess-v2` | **41 / 41** | 0 | [`requirement-cases-controlled-2026-11-20.json`](reports/requirement-cases-controlled-2026-11-20.json) | Проверка детерминированных правил стажа, альтернатив и цитат без модели |
| Живой прогон до фиксов PR #15 | 20.11.2026 | `live` (YandexGPT) | `assessment-2.0` / `assess-v4` | **41 / 41** | 0 | [`requirement-cases-live-2026-11-20.json`](reports/requirement-cases-live-2026-11-20.json) | Живой прогон на `yandexgpt/latest`, `temperature=0` |
| Контролируемый прогон после фиксов PR #15 | 20.11.2026 | `controlled` | `assessment-2.0.2` / `assess-v4` | **41 / 41** | 0 | [`requirement-cases-controlled-pr15-fixes-2026-11-20.json`](reports/requirement-cases-controlled-pr15-fixes-2026-11-20.json), [`pr15-review-fixes.md`](reports/pr15-review-fixes.md) | Подтверждает исправление 6 дефектов ревью PR #15 (включая ограничение отрицания опыта фразой и проверку цитат без склейки); **не является** замером качества LLM |
| Живой прогон после фиксов PR #15 | 20.11.2026 | `live` (YandexGPT) | `assessment-2.0.2` / `assess-v4` | **41 / 41** | 0 | [`requirement-cases-live-pr15-fixes-2026-11-20.json`](reports/requirement-cases-live-pr15-fixes-2026-11-20.json), [`pr15-review-fixes.md`](reports/pr15-review-fixes.md) | **Ограничения:** проверяет целевой `rule_key` каждого из 41 синтетического случая без записи в БД; **не измеряет** качество извлечения полной `CandidateCard` или качество на реальных резюме. В коммите `c87cbd6` алгоритм обновлён до `assessment-2.0.4` (добавлены скоупированные отрицания опыта `2.0.3` и правило «старших курсов» `2.0.4`, покрытые регрессионными тестами; новый живой прогон 41/41 на `2.0.4` не фиксировался) |

### 2.2. Контрольный набор `py-9001` (12 случаев) и 16 содержательных кейсов

- **`fixtures/assessment/py-9001.json`** ([`fixtures/assessment/README.md`](../fixtures/assessment/README.md)): **12 случаев** (`C1`–`C5` положительные и Unicode non-BMP UTF-16 `🙂`, `N1`–`N7` отрицательные: сдвинутая цитата, неверная длина, устаревшая версия текста, чужой текст, вывод без цитаты, отказ модели, черновой профиль). Проверяется детерминированно без БД и модели командой `uv run python -m scripts.check_assessment_fixtures` и автотестами `tests/test_assessment_fixtures.py`, `tests/test_assessment_fixtures_db.py`.
- **16 содержательных кейсов** (`fixtures/requirement_profiles/synthetic/content-cases.json`, [`profile-assessment-integration.md`](reports/profile-assessment-integration.md)): **16 / 16 проверок прошли** с подставленными ответами (проверяют доставку `acceptance` и маршрутизацию; кейсы этапа `interview` проверяют только отсутствие в `screening`, а не качество живого интервью).

---

## 3. Бенчмарк поиска кандидатов (`search-evaluation-v1.json`)

Замер выполнен на замороженном синтетическом датасете [`fixtures/search/synthetic-v1.json`](../fixtures/search/synthetic-v1.json) (`data_version = search-01-synthetic-v1`, `data_sha256 = 6a6e13d64caa212d1bb1fb131f2fd220a18eb5c0d49d4f661c88e8a67d7c275a`): **18** документов, **25** чанков, **6** калибровочных запросов и **8** контрольных запросов (из них 2 запроса без релевантного ответа).

- **Источник:** [`docs/modules/search-evaluation-v1.json`](modules/search-evaluation-v1.json), описание и выводы — [`docs/modules/search.md`](modules/search.md).
- **Модель плотной ветки:** `intfloat/multilingual-e5-small@614241f622f53c4eeff9890bdc4f31cfecc418b3:chunk-v1`, 384 измерения.
- **Среда замера:** Windows 11, Python 3.13.6, 16 логических CPU (`OMP_NUM_THREADS=4`, `MKL_NUM_THREADS=4`), `torch 2.14.1+cpu`, `transformers 5.20.2`, `sentence-transformers 6.2.0`, `numpy 2.5.3`.
- **Калибровка порога (6 калибровочных запросов, сетка `0.70`–`0.94` с шагом `0.02`):**
  - пороги `0.70`–`0.80`: `relevant_at_5 = 3`, но `negative_with_results = 2` (отклонены — ложная выдача на обоих запросах без ответа);
  - пороги `0.82`–`0.94`: `relevant_at_5 = 3`, `negative_with_results = 0` (приняты; выбран порог **`0.94`** до прохода по контрольной группе).
- **Инициализация и векторизация:** холодная загрузка модели E5 — **26 247,05 мс (26,25 с)**; векторизация 25 фрагментов — **349,76 мс (0,35 с)**.

| Способ | Precision@5 | Precision@10 | Релевантные выданы / пропущены в топ-10 | Ложная выдача на запросах без ответа | Валидные границы цитат | Медиана тёплого поиска (24 запроса), мс | p95 тёплого поиска, мс |
|---|---:|---:|---:|---:|---:|---:|---:|
| **BM25 (лексика)** | **0,20** | **0,10** | **6 / 1** | **0 / 2** | **7 / 7** | **4,33** | **5,66** |
| **Dense E5 (`0.94`)** | 0,00 | 0,00 | 0 / 7 | 0 / 2 | 0 | 27,50 | 44,47 |
| **Hybrid (BM25 + E5 + RRF)** | 0,20 | 0,10 | 6 / 1 | 0 / 2 | 7 / 7 | 30,32 | 41,17 |

**Инженерный вывод и границы замера:**
- `hybrid_added_paraphrase_hits = []`, `hybrid_meets_local_rule = false`: при безопасном пороге `0.94` гибрид не добавил ни одной релевантной находки на перефразировании (пропущен `search-9013` по «маршрутизация заявлений горожан по подразделениям»), увеличив задержку в ~7 раз. Поэтому по умолчанию в `deploy/compose.yaml` включён **BM25** (`HR_SEARCH_SEMANTIC_ENABLED=false`).
- **Ограничения (`scope`):** `synthetic in-memory, without PostgreSQL/HTTP` — замер выполнен без сетевого слоя HTTP и без SQL `pgvector` (сам SQL-оператор проверяется отдельно в `tests/test_search_postgres.py` и диагностической проверкой `scripts/check_search_demo.py --probe-semantic` при `0.78`). Качество на реальном корпусе резюме с разметкой HR предстоит измерить на пилоте.

---

## 4. Проверки на реальном архиве «Кадры» (1 739 файлов, 1 721 резюме, 287 DOCX)

| Проверка | Дата | Область и объём данных | Зафиксированный результат | Источник | Ограничения |
|---|---|---|---|---|---|
| **Импорт и повторный прогон (`ingest-02`)** | 20.11.2026 | Полный архив «Кадры» — **1 739 файлов** (`1 721` резюме, `18` служебных документов), локальная PG 16 | Первый прогон ≈ 15 с (`1 721 imported`, `18 excluded_non_resume`, `0 quarantined`, `0 errors`); `--reredact` ≈ 20 с (`1 721 duplicate_skipped`, `242` основных отклика получили дату/публикацию, `24` внешних отклика истории, перечищено `295 + 8` текстов). Повторный прогон не изменил число строк в 6 таблицах. Тесты на момент `ingest-02`: **290 passed** | [`docs/modules/ingest.md`](modules/ingest.md#проверено) | Полнота поиска имён ручной разметкой не измерялась: имя без слова-подсказки рядом может остаться в тексте |
| **Независимый аудит очистки ПДн (`app.ingest.audit`)** | 20.11.2026 | Все `1 721` очищенных текстов архива «Кадры» | До `ingest-02` (правила v1): **273 кандидата** с находками (272 — личные ссылки с путём). После `ingest-02` (правила v2): **0 находок**; `2` текста в очереди ручного просмотра `review` (`@слово`) | [`docs/modules/ingest.md`](modules/ingest.md#проверено) | Автоматический аудит проверяет широкие шаблоны и сверку с `candidate_pii`, но не заменяет сплошную ручную вычитку |
| **Реестр публикаций на 287 DOCX (`requirements-03`)** | 20.11.2026 | Реальный архив `kadry-2026` (`1 739` файлов, `archive_sha256: 801efb82...`), **287 DOCX** папки консультанта + 10 документов ДИ/публикаций для 5 IT-должностей | `extract_text`/`parse_history` + runtime resolver (`registry_version = v1`, 14 правил): **242 `awaiting_hr`**, **45 `missing_posting`**, **0 `confirmed`**, **0 `no_matching_position`**; **21** отрицательное свидетельство о паре с `hr-consultant` (не превращается в «нет ни одной должности»); **24** внешних упоминания в 4 файлах. Повтор побайтово идентичен. `0` вызовов модели, `0` записей в БД | [`requirements-03-verification.md`](reports/requirements-03-verification.md), [`requirements-03-posting-mapping.json`](reports/requirements-03-posting-mapping.json), [`profile-applicability-2026-11-20.json`](reports/profile-applicability-2026-11-20.json) | Чистый разбор без импорта резюме в БД и без оценки кандидатов; подтверждение 7 реальных кадровых соответствий остаётся за HR |
| **Загрузка 6 профилей по реальным ДИ и матрице (`requirements-02`)** | 20.11.2026 | **7 оригинальных DOCX** (`fixtures/requirement_profiles/all_six/originals/`), 6 должностей (`frontend-dev`, `hr-consultant`, `junior-python-dev`, `junior-ux-ui`, `python-dev`, `qa-manual`) | Проверены SHA-256 оригиналов, абзацы и дословные цитаты: **12** формальных условий, **36** компетенций, **256** индикаторов. Все 6 загружаются одной транзакцией как `draft` рабочего контура. **14** адресных тестов `test_all_six_profiles.py` прошли | [`requirements-02-six-profiles.md`](reports/requirements-02-six-profiles.md) | Профили загружаются как черновики (`draft`); рабочее утверждение требует действия уполномоченного HR |

---

## 5. Серверный замер единого окна взаимодействия (`interaction-window`)

- **Дата и база:** 21.11.2026, база `deed93a` + объединение с `d10bf96` ([`docs/reports/interaction-window.md`](reports/interaction-window.md)).
- **Команда:** `pytest` по 4 файлам (`tests/test_interaction_http.py`, `tests/test_interaction_legacy.py`, `services/hiring/tests/test_interaction_portal.py`, `services/hiring/tests/test_interaction_window.py`).
- **Результат:** **4 passed за 3,11 с** (Python 3.13.7, FastAPI 0.165.0, SQLAlchemy 2.0.58).
- **Замер внутри HTTP-сценария:** **8 чтений**, максимум **39,4 мс**, максимум **7 727 байт** после сборки финального DTO. Установленные стартовые лимиты: `1 с` connect / `2 с` read / `3 с` overall, `256 КиБ` на источник, `page_size = 25` (максимум `100`).
- **Проверены инварианты:** Q-ref с `event_sequence`, независимые H1/H2, идемпотентный `FeedbackReview`, атомарная запись review + `StageEvent`, отзыв доступа к H1 без потери H2, запрет GET без `X-Interaction-Gateway-Key`, отбрасывание browser-заголовков, `training-gate` (working UUID не проходит), деградация `partial` (200) и отказ всех источников (`503`).
- **Ограничения (`scope`):** изолированная SQLite + `ASGITransport` (и `MockTransport` для имитации сетевого отказа); **не проверялись** исполнение миграции `0014` и блокировки на PostgreSQL под конкуренцией, запуск `deploy/compose.interaction.yaml`, реальная сеть, большой корпус и UI.

---

## 6. Протоколы сквозных HTTP-проверок волн 1–6 и интерфейсных проверок

| Волна / сервис | Дата и база | Зафиксированный результат | Что проверено | Источник | Ограничения |
|---|---|---|---|---|---|
| **Wave 1 · Workforce** | 21.11.2026, `9f6fece` (`2ab2584`) | **57 passed, 0 skipped** (25,04 с в Docker PG 17.6 + RMQ 4.1.8; 40,75 с нативно на Windows); `smoke normal`, `review_smoke apply` и `keep` — passed | Миграции, seed, сессии, права, конкуренция, outbox/inbox, crash before ack, dead-queue, коррекции | [`wave-1-workforce.md`](reports/wave-1-workforce.md) | Синтетические данные; без реального Hiring/Requirements |
| **Wave 1 · Hiring** | 21.11.2026, `2ab2584` | **40 passed, 0 skipped** (4 повтора подряд) на PG 16.15 + `python -m hiring.demo` | 17 операций дела, комплект/версии файлов, конкуренция `ready` vs upload, идемпотентность, `record-assignment`, рестарт uvicorn | [`wave-1-hiring.md`](reports/wave-1-hiring.md) | Автономно (`AUTH_MODE=fixture`, `transfer_mode=manual`); `compose up` не запускался (нет Docker Hub в среде) |
| **Wave 1 · Requirements** | 21.11.2026, `376b9b4` / `fd8e126` | **26 passed, 1 skipped** (live PG/RMQ); `test_stage1.py` + `test_validation_parity.py` — **13 passed** на отдельном uvicorn + рестарт | Паритет схемы с legacy, загрузка/транскрипция сканов, версии v1/v2, outbox/backoff/retry на сбое брокера, рестарт процесса | [`wave-1-requirements.md`](reports/wave-1-requirements.md) | SQLite; `test_integration_live.py` пропущен (нет Docker/PG17/RMQ в локальной среде) |
| **Wave 2 · Onboarding (Workforce)** | 21.11.2026, `0a20c84` | 2 адресных pytest (2,19 с + 1,21 с) + живой uvicorn/httpx smoke | 6 операций `/api/v1/onboarding`, 3 шага, права employee/HR, `STALE_REVISION`, сохранность после остановки | [`wave-2-onboarding.md`](reports/wave-2-onboarding.md) | SQLite, без Docker/PG/нагрузки |
| **Wave 2 · Vacancies (Requirements)** | 21.11.2026, `0a20c84` | **2 passed** (`test_vacancies.py`, `test_stage1.py`) на отдельном uvicorn | 7 операций каталога, проверка `is_current` профиля при публикации, 5-польная публичная DTO, история | [`wave-2-vacancies.md`](reports/wave-2-vacancies.md) | SQLite, `fixture`-акторы, без PG/Docker |
| **Wave 2 · Interview outcome (`legacy`)** | 21.11.2026, `0a20c84` | 4 адресных теста + **878 passed** (полный набор) | `POST /interviews/{id}/outcome` (`continue`/`stop`/`no_answer`), `audit_log`, неизменность этапа | [`wave-2-interview-outcome.md`](reports/wave-2-interview-outcome.md) | Учебная БД, без вызова LLM |
| **Wave 3 · Development (Workforce)** | 21.11.2026, `ec0a764` | **6 passed** (7,39 с: 4 development + 2 onboarding) + живой uvicorn `development_smoke` (~6 с) | 17 операций ИПР (3A–3C): цели, план со снимком, попытки, неизменяемые ревью, закрытие, `ResultPackage`, рестарт | [`wave-3-development.md`](reports/wave-3-development.md) | SQLite, без PG/Docker/нагрузки |
| **Wave 3 · Matching (`legacy`)** | 21.11.2026, `ec0a764` → `3fd9a0e` | 3A/3B/3C: по 3 адресных теста; полный набор **881 → 884 → 887 passed**, 0 skipped | Двунаправленный подбор, статусы кросс-оценок, неизменяемые `matching_suggestions` (`0011`) | [`wave-3a`](reports/wave-3a-candidates-for-vacancy.md), [`wave-3b`](reports/wave-3b-vacancies-for-candidate.md), [`wave-3c`](reports/wave-3c-vacancy-suggestions.md) | Синтетический корпус поиска, без живой LLM |
| **Wave 3 · Students (3A–3C)** | 21.11.2026, `ec0a764` → `a39a4dc` | По **1 passed** на каждую часть (3A, 3B, 3C) через реальный HTTP отдельного uvicorn | Места, заявки, вместимость, задания/попытки/ревью, итоги практики и вуза, карьерный пакет | [`wave-3a`](reports/wave-3a-practice.md), [`wave-3b`](reports/wave-3b-practice.md), [`wave-3c`](reports/wave-3c-practice.md) | SQLite, `fixture`-акторы, без PG |
| **Wave 4 · Mobility (4A–4C)** | 21.11.2026, `22df231` → `9750713` | 4A: **1 passed** (7,50 с); 4B: **1 passed** (5,42 с); 4C: **1 passed** (3,82 с) на отдельном uvicorn + рестарт | Временные задачи, приватный интерес, версионные согласования времени, участие, пакет, заявление на вакансию | [`wave-4-mobility.md`](reports/wave-4-mobility.md) | Синтетика `mobility-training-v1`, SQLite, без UI и PG |
| **Wave 4 · Recognition (4A–4D)** | 21.11.2026, `8038d09` | **4 passed** (1,52 с) + 4 loopback HTTP-сценария `tests.smoke --part 4a..4d` с перезапуском uvicorn | Благодарности, номинации, мероприятия с вместимостью/очередью, закрытые сессии, отзыв материалов | [`wave-4-recognition.md`](reports/wave-4-recognition.md) | SQLite, `demo-*` токены, без UI и PG |
| **Wave 4 · Management (4A–4C)** | 21.11.2026, `3755b5f` → `ad769f6` | Адресные тесты 3 + 3 + 5; полный набор **890 → 893 → 898 passed**, 0 skipped | Оперативная сводка 4A, годовой выпуск 4B (`0012`), плановый снимок с паросочетанием Куна 4C (`0013`) | [`wave-4a`](reports/wave-4a-operational-overview.md), [`wave-4b`](reports/wave-4b-annual-source.md), [`wave-4c`](reports/wave-4c-planning-snapshot.md) | Только факты `legacy-hr`; `workforce`/`hiring`/`practice` помечены `unavailable` |
| **Wave 5 · Candidate portal (Hiring 5A–5C)** | 21.11.2026, `120a4b0` → `21bd647` | **44 → 47 → 50 passed** (40 базовых Hiring + 10 тестов портала) на PG | Подача `ОБР-NNNNNN`, уточнения/дополнения, ручная регистрация рассмотрения, публичные исходы, сообщения с `read` | [`wave-5a`](reports/wave-5a-candidate-request.md), [`wave-5b`](reports/wave-5b-candidate-clarification.md), [`wave-5c`](reports/wave-5c-candidate-outcome.md) | `fixture`-акторы, учебный снимок вакансий |
| **Wave 5 · Feedback (5A–5D)** | 21.11.2026, `21bd647` → `ecf5794` | **4 passed** (1,91 с) + 4 loopback HTTP-сценария `tests.smoke --part 5a..5d` с перезапуском | Одноразовые коды без связи с ответом, подавление малых групп/категорий, меры, отдельные именные обращения | [`wave-5-feedback.md`](reports/wave-5-feedback.md) | Синтетика, SQLite; не аудит сетевой анонимности |
| **Wave 5 · Social support (5A–5D)** | 21.11.2026, `ad769f6` | **4 passed** (6,78 с) на отдельном uvicorn + рестарт | Заявление, файлы, доработка, решения/выписка, правило отвода, раздельное исполнение и закрытие | [`wave-5-support.md`](reports/wave-5-support.md) | Синтетика `support-training-v1`, SQLite, без UI/бухгалтерии |
| **Wave 6 · Сквозные демо-сборки (6A–6B)** | 21.11.2026, `ecf5794` / `01de7a5` | **Recruitment:** полный HTTP-путь Hiring + `legacy` (8 шагов + `404` для `candidate2`, [transcript](reports/wave-6-recruitment-demo.transcript.json)). **Report:** 2 снимка SHA-256 (`be988413...` → `51cfeaa2...`) + XLSX 18 376 байт ([XLSX](reports/wave-6-report-demo.xlsx)). **Practice:** **1 passed in 2.98 s** + рестарт. **Support:** **1 passed in 2.35 s** + рестарт | Полные многошаговые HTTP-прогоны с сохранением реальных request/response трасс и проверкой сохранности после перезапуска | [`wave-6-recruitment-demo.md`](reports/wave-6-recruitment-demo.md), [`wave-6-report-demo.md`](reports/wave-6-report-demo.md), [`wave-6-practice-demo.md`](reports/wave-6-practice-demo.md), [`wave-6-support-demo.md`](reports/wave-6-support-demo.md) | Синтетические данные; без нагрузочных испытаний |
| **Серверные данные в UI и пользовательские сценарии** | 21.11.2026, `20fd99b` / `7269c05` | Сборка TypeScript/Vite (74 и 82 модуля); 2 адресных теста `analytics/dashboard`; READ ONLY проверка на PG стенда (01–21.11.2026 training: 13 поступлений, 2 интервью, 2 передачи, 4 недели, 6 вакансий); проверка `py-9101` в браузере и 3 XLSX | Реальные серверные данные в `AnalyticsDashboard`, карточке кандидата, единой базе, портале, архиве и годовом отчёте | [`frontend-feedback-2026-11-21.md`](reports/frontend-feedback-2026-11-21.md), [`server-data-original-layout.md`](reports/server-data-original-layout.md) | Не является E2E-прогоном всех экранов; `mobility` и `recognition` в SPA не подключены |

---

## 7. Воспроизводимые команды проверки

Все команды выполняются из корня репозитория `hr` (если не указан каталог сервиса).

### 7.1. Ядро `app/` (PostgreSQL + pgvector)

```bash
# 1. Полный набор pytest ядра (требуется отдельная тестовая БД с pgvector, имя оканчивается на _test;
#    pytest очищает схему public этой БД!)
TEST_DATABASE_URL="postgresql+psycopg://hr:hr@127.0.0.1:5432/hr_test" uv run pytest -q -ra

# 2. Проверка контрольного набора оценки py-9001 (12 случаев, без БД и без LLM)
uv run python -m scripts.check_assessment_fixtures

# 3. Контролируемый прогон 41 кейса формальной оценки (без LLM)
uv run python -m scripts.replay_requirement_cases --mode controlled --output controlled.json

# 4. Живой прогон 41 кейса на YandexGPT (нужны YANDEX_API_KEY и YANDEX_FOLDER_ID в .env)
uv run python -m scripts.replay_requirement_cases --mode live --output live.json

# 5. Подготовка учебного стенда одной командой (без вызовов LLM / с LLM)
uv run python -m scripts.demo_setup --no-llm
# uv run python -m scripts.demo_setup --workers 4

# 6. Независимый аудит очистки ПДн по текущей БД
uv run python -m app.ingest.audit

# 7. Бенчмарк поиска BM25 vs E5 vs Hybrid (требуются зависимости requirements-search.txt и кэш модели)
uv run --no-sync python -m app.search prepare-model
uv run --no-sync python -m app.search evaluate --repeats 3 --output search-evaluation.json
```

### 7.2. Инфраструктурный smoke и проверка общих сессий (Compose + Nginx)

```bash
# Поднятие всех 9 сервисов через Nginx gateway (127.0.0.1:8080)
python3 deploy/create-env.py deploy/local/runtime.env --release local
docker compose --env-file deploy/local/runtime.env -f deploy/compose.yaml up -d --build --wait --wait-timeout 240
bash deploy/seed-roles.sh deploy/local/runtime.env

# Проверка OpenAPI, Swagger-префиксов, 404, readiness и 401 по всем 9 сервисам
python3 deploy/smoke.py --base http://127.0.0.1:8080

# Проверка общей Bearer-сессии (Workforce / Hiring / Requirements) с пересозданием контейнеров и отзывом
python3 deploy/check-sessions.py create --state deploy/local/probe.json
docker compose --env-file deploy/local/runtime.env -f deploy/compose.yaml down
docker compose --env-file deploy/local/runtime.env -f deploy/compose.yaml up -d --wait --wait-timeout 240
python3 deploy/check-sessions.py verify --state deploy/local/probe.json
```

### 7.3. Тесты отдельных сервисов (`services/*`)

```bash
# Workforce (полный набор с PG/RabbitMQ — через WORKFORCE_TEST_DATABASE_URL и WORKFORCE_TEST_RABBITMQ_URL)
uv --directory services/workforce run pytest -q

# Requirements (stage 1 + паритет формата)
uv --directory services/requirements run pytest -q -rs

# Hiring (40 базовых + 10 портала; требуется тестовая PostgreSQL)
uv --directory services/hiring run pytest -q

# SQLite-сервисы (автономный запуск с временной SQLite и реальным uvicorn)
uv --directory services/students run pytest -q
uv --directory services/mobility run pytest -q
uv --directory services/social-support run pytest -q
uv --directory services/recognition run pytest -q
uv --directory services/feedback run pytest -q
```

---

## Связанные документы в репозитории

- [Архитектура реализованной платформы](ARCHITECTURE.md)
- [Серверная сборка и CI/CD](modules/deployment.md)
- [Инструкция модуля поиска и сравнение моделей](modules/search.md)
- [Инструкция модуля оценки](modules/assessment.md)
