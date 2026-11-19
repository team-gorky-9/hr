# Контракт: модуль извлечения карточки и оценивания (`app/ai/`, `app/assessment/`)

**Версия:** 0.1 (проект к Этапу 1) · **Дата:** 2026-11-19 · **Владелец:** Илья · **Потребители:** HTTP API (`app/api/`), CLI-прогон, модуль интервью (Этап 2б).

Опирается на [database.md](database.md) v1.0 и [requirements.md](requirements.md) v0.1.

## 1. Назначение и границы

Модуль разделён на два пакета:
- `app/ai/` — абстракция провайдера (`LLMConfig`, `LLMClient`, реализация для YandexGPT через OpenAI-совместимый API, тестовая заглушка `FakeLLMClient`).
- `app/assessment/` — бизнес-логика извлечения `CandidateCard`, сопоставления с утверждённым профилем требований, детерминированный расчёт границ цитат `Evidence`, валидация инвариантов и CLI-запуск.

**Жёсткие инварианты (не могут быть обойдены промптом):**
1. **Слепой вход:** в LLM уходит **только** `candidate_texts.text` (никогда `source_documents.raw_text` и никогда `candidate_pii`).
2. **Только утверждённый профиль:** оценка по профилю со статусом `draft` или `archived` **запрещена** (`AssessmentDomainError`).
3. **Единая версия текста:** все `Evidence` оценки обязаны ссылаться на тот же `candidate_text_id`, из которого построена переданная `CandidateCard` (и эта версия текста должна совпадать с текущей версией текста кандидата на момент расчёта).
4. **Оффсеты считает код, а не LLM:** модель возвращает дословную подстроку `quote` (и при повторах в тексте — короткий контекст или индекс вхождения). Python-код находит точные `start`/`end` в кодовых точках Unicode и проверяет `text[start:end] == quote`.
5. **Нет цитаты — нет подтверждённого факта:**
   - для `FormalCheckIn` со статусом `met` или `not_met` требуется `len(evidence) >= 1` (исключение: требование `experience` с `min_years == 0`, где стаж не требуется — допускает явное пояснение без цитаты из резюме);
   - если модель выдала `met`/`not_met`, но ни одна цитата не найдена дословно в `candidate_texts.text`, код **переводит** проверку в `unknown` с пояснением `«вывод модели не подтверждён цитатой в очищенном тексте»` и ставит предупреждение в лог;
   - для `CompetencyScoreIn` с непустым `level` требуется `len(evidence) >= 1`; без валидной цитаты `level` сбрасывается в `None` («нет подтверждённых сведений»).
6. **Итог `formal_result` считает код:** `not_met` > `unknown` > `met` (дублируется в `repository.save_assessment`). Высокий `overall_score` компетенций не перекрывает `not_met`.
7. **Сбой LLM безопасен:** таймаут, сетевая ошибка или невалидный JSON после ретрая вызывают типизированную ошибку (`LLMUnavailableError` / `LLMInvalidResponseError`), не пишут фиктивную оценку и **не меняют** этап отклика.
8. **Защита от prompt injection:** текст резюме передаётся внутри явного блока данных (`<resume_text>...</resume_text>`), у модели нет инструментов записи в БД или смены этапа.

## 2. Конфигурация LLM (`app/ai/config.py`)

Провайдер и модель не хардкодятся в коде сервисов; читаются из переменных окружения через Pydantic Settings (`LLMConfig`):

| Переменная `.env` | Назначение | Значение по умолчанию / пример |
|---|---|---|
| `LLM_PROVIDER` | `yandexgpt` \| `openai_compat` \| `fake` | `yandexgpt` |
| `LLM_BASE_URL` | базовый URL OpenAI-совместимого API | `https://llm.api.cloud.yandex.net/v1` |
| `YANDEX_API_KEY` | секретный ключ (никогда не логируется) | — |
| `YANDEX_FOLDER_ID` | каталог Yandex Cloud | — |
| `LLM_EXTRACT_MODEL` | URI модели для `CandidateCard` | `gpt://<FOLDER_ID>/yandexgpt-lite/latest` |
| `LLM_ASSESS_MODEL` | URI модели для оценивания | `gpt://<FOLDER_ID>/yandexgpt/latest` |
| `LLM_TEMPERATURE` | детерминизм | `0.0` |
| `LLM_TIMEOUT_SEC` | таймаут одного вызова | `30` |
| `LLM_MAX_RETRIES` | число повторов при сетевой/схемной ошибке | `1` |

Интерфейс `LLMClient` предоставляет единый метод `complete_structured(system_prompt, user_prompt, response_model, *, model_role) -> BaseModel`. Все вызовы логируют метаданные (`model`, `prompt_version`, `status`, `latency_ms`) в `audit_log` (`AuditAction.LLM_CALL`) **без** текста резюме и без ключей.

## 3. Публичные функции модуля (`app/assessment/service.py`)

Функции принимают `Session`, UUID (не ORM-объекты) и `LLMClient`; **не делают `commit`** (транзакцией управляет CLI или вызывающий).

```python
def extract_candidate_card(
    session: Session,
    *,
    candidate_id: uuid.UUID,
    llm: LLMClient,
    prompt_version: str = "card-v1",
) -> uuid.UUID:
    """Берёт текущий очищенный текст кандидата, извлекает CandidateCard,
    сохраняет через repository.add_candidate_card и возвращает card_id."""

def assess_candidate(
    session: Session,
    *,
    candidate_id: uuid.UUID,
    profile_id: uuid.UUID,
    llm: LLMClient,
    card_id: uuid.UUID | None = None,
    prompt_version: str = "assess-v1",
) -> uuid.UUID:
    """Проверяет approved-статус профиля и актуальность карточки, запускает оценку,
    резолвит цитаты в Evidence по candidate_texts.text, сохраняет через
    repository.save_assessment и возвращает assessment_id."""
```

### Ошибки модуля (`app/assessment/errors.py`)
- `AssessmentDomainError` — черновой/архивный профиль, устаревшая карточка (`card.candidate_text_id != current_text.id`), отсутствие очищенного текста.
- `LLMUnavailableError` — сеть/таймаут/HTTP 5xx/429 от провайдера.
- `LLMInvalidResponseError` — провайдер вернул невалидный JSON или нарушил Pydantic-схему даже после ретрая.

## 4. CLI-запуск для Этапа 1

По ADR-003 на Этапе 1 оценивание запускается локальной CLI-командой (HTTP API только читает результат из БД):

```bash
# Оценить одного кандидата по утверждённому профилю должности
uv run python -m app.assessment run --candidate-code py-9001 --position-code python-dev

# Пакетный прогон (Этап 2а) — все кандидаты с текстом по указанной или всем должностям
uv run python -m app.assessment batch --position-code python-dev
```

Команда сама управляет транзакцией на каждого кандидата (ошибка на одном кандидате не откатывает остальных) и выводит JSON-сводку: `candidate_code`, `status` (`ok` | `domain_error` | `llm_error`), `card_id`, `assessment_id`, `formal_result`, `overall_score`, `error`.

## 5. Сквозной контрольный пример (`py-9001`)

Базовый очищенный текст (`candidate_text_id = T1`, длина 37 символов):
`Написал API-тесты для сервиса заявок.`

Утверждённый учебный профиль `python-dev`:
- Обязательное требование `R1` (`kind="experience"`, `params={"min_years": 2.0, "scope": "commercial_total"}`).
- Компетенция `C1` (`code="API_TEST"`, индикатор «Писал автоматизированные API-тесты»).

| Сценарий | Очищенный текст | Ожидаемый результат `assess_candidate` |
|---|---|---|
| **1. Пробел (`unknown`)** | `Написал API-тесты для сервиса заявок.` | `card.experience_years = None`, `card.missing` содержит «длительность коммерческого опыта»; `R1 → unknown` (`evidence=[]`); `C1 → level >= 70` с `Evidence(candidate_text_id=T1, quote="Написал API-тесты для сервиса заявок.", start=0, end=37)`; `formal_result = "unknown"`. |
| **2. Выполнено (`met`)** | `Написал API-тесты для сервиса заявок.\nОбщий коммерческий опыт — 3 года.` | `R1 → met` с цитатой `"Общий коммерческий опыт — 3 года."` (`start=38, end=71`); `C1` с прежней цитатой `0..37`; `formal_result = "met"`. |
| **3. Не выполнено (`not_met`)** | `Написал API-тесты для сервиса заявок.\nОбщий коммерческий опыт — 1 год.` | `R1 → not_met` с цитатой `"Общий коммерческий опыт — 1 год."` (`start=38, end=70`); `C1` остаётся подтверждённой (`level >= 70`, цитата `0..37`); `formal_result = "not_met"` (высокий балл `C1` не перекрывает `R1`). |
| **4. Черновой профиль** | любой | Исключение `AssessmentDomainError`, запись в `assessments` не создаётся. |
| **5. Галлюцинация цитаты** | базовый текст, модель вернула `quote="Руководил отделом"` | Резолвер не находит подстроку → вывод не принимается как подтверждённый (`unknown` / `level=None`), `EvidenceError` в БД не допускается. |
| **6. Сбой LLM** | `FakeLLMClient` бросает таймаут | `LLMUnavailableError`, оценка не создаётся, этап отклика остаётся `new`. |
