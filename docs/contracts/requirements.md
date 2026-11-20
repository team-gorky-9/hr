# Контракт: модуль профилей требований (`app/requirements/`)

**Версия:** 0.1 (проект к Этапу 0б/1) · **Дата:** 2026-11-19 · **Владелец:** Давид · **Потребители:** модуль оценивания (`app/assessment/`), HTTP API (`app/api/`).

Опирается на [database.md](database.md) v1.0 (пп. 3.5, 4.3, 5, 6).

## 1. Назначение и границы

Модуль `app/requirements/` хранит машиночитаемые эталоны требований должностей (формальные требования из ДИ + матрицу компетенций по образцу заказчика), загружает их в таблицы `requirement_profiles`, `formal_requirements`, `competencies`, `competency_indicators` и управляет переводом профиля из `draft` в `approved`.

**Жёсткие инварианты:**
1. Каждый загружаемый профиль создаётся со статусом `draft` (если явно не выполняется отдельная операция утверждения уполномоченным пользователем или пометка синтетического учебного профиля).
2. На одну должность (`position_id`) может существовать **не более одного** профиля в статусе `approved` (частичный уникальный индекс БД). При утверждении новой версии прежний `approved` переводится в `archived` в той же транзакции.
3. Каждое обязательное формальное требование (`is_mandatory = true`) и каждая компетенция имеют ссылку на источник (`source_quote` — пункт ДИ или эталонной матрицы, либо явную метку `synthetic_test_rule` для учебного профиля `py-9001`).
4. Оценивание (модуль Ильи) **никогда** не запускается по профилю в статусе `draft` или `archived`.

## 2. Машиночитаемый формат входного файла профиля (JSON)

Файлы профилей лежат в каталоге данных модуля (например, `data/profiles/<position_code>.v<N>.json` или `fixtures/profiles/`).

```json
{
  "position_code": "python-dev",
  "is_synthetic": true,
  "source_document_ref": "synthetic:stage-0b-py-9001",
  "created_by": "david",
  "note": "Учебный профиль для сквозной проверки py-9001; порог 2 года — только для теста.",
  "formal_requirements": [
    {
      "kind": "experience",
      "description": "Подтверждённый общий коммерческий опыт не менее 2 лет",
      "is_mandatory": true,
      "source_quote": "synthetic_test_rule: stage-0b-02 (учебный порог 2 года)",
      "sort_order": 1,
      "params": {
        "min_years": 2.0,
        "scope": "commercial_total",
        "allow_equivalent": false
      }
    }
  ],
  "competencies": [
    {
      "rank": "special",
      "code": "API_TEST",
      "name": "Автоматизированное тестирование API",
      "target_level_min": 70,
      "target_level_max": 100,
      "sort_order": 1,
      "indicators": [
        {
          "text": "Писал автоматизированные API-тесты",
          "sort_order": 1
        }
      ]
    }
  ]
}
```

## 3. Согласованная схема `formal_requirements.params`

В `database.md` п. 3.5 поле `params` хранится как JSONB. Чтобы модули Давида и Ильи читали условия одинаково, для каждого значения `FormalRequirementKind` фиксируются допустимые ключи `params`:

| `kind` (`FormalRequirementKind`) | Обязательные / допустимые ключи `params` | Как оценивание трактует `met` / `not_met` / `unknown` |
|---|---|---|
| `education_level` | `min_level`: `"среднее профессиональное"` \| `"высшее"` \| `"высшее (специалитет/магистратура)"` | `met` — в резюме явно указан уровень `>= min_level`; `not_met` — явно указан только более низкий уровень; `unknown` — образование не указано или уровень неясен. |
| `education_field` | `fields`: `list[str]` (допустимые направления, напр. `["Юриспруденция", "ГМУ"]`); `retraining_allowed`: `bool` (допускается ли профпереподготовка при ином высшем); `retraining_fields`: `list[str]` (опц.) | `met` — направление из `fields` или (при `retraining_allowed=true`) иное высшее + профпереподготовка по `fields`; `not_met` — указано иное направление и нет нужной переподготовки (когда раздел курсов/переподготовки заполнен либо явно несовместим); `unknown` — специальность/курсы не указаны. |
| `experience` | `min_years`: `float` (`>= 0`); `scope`: `"total"` \| `"commercial_total"` \| `"municipal_service"` \| `"specialty"`; `allow_equivalent`: `bool` (по умолчанию `false`) | Если `min_years == 0` → `met` всегда (стаж не требуется). Иначе: `met` — подтверждённый стаж в заданном `scope >= min_years`; `not_met` — даты/стаж указаны полно и сумма `< min_years`; `unknown` — длительность/даты не указаны или нельзя однозначно вычислить `scope`. |
| `knowledge` | `topics`: `list[str]` (напр. `["25-ФЗ", "131-ФЗ", "ТК РФ", "59-ФЗ"]`); `verify_at_interview`: `bool` (обычно `true`) | Знание законов редко доказывается резюме: `met` — прямое упоминание практики/знания темы; `unknown` — не упомянуто в резюме (повод включить вопрос в гайд интервью, **не** отказ); `not_met` — только при прямом противоречии. |
| `other` | `rule_summary`: `str`; `check_hint`: `str` | Проверяется по `description` и `check_hint` с обязательной цитатой. |

Неизвестные ключи в `params` запрещены при валидации входного JSON загрузчиком (`extra="forbid"`).

## 4. Публичные операции модуля (`app/requirements/service.py`)

| Функция / CLI | Вход | Выход / эффект | Ошибки |
|---|---|---|---|
| `load_profile_draft(session, payload)` | `Session`, валидированный JSON профиля | Создаёт `RequirementProfile(status="draft", version=max+1)` + дочерние `formal_requirements`, `competencies`, `competency_indicators`. Не коммитит. | Неизвестный `position_code`, дубль кода компетенции в профиле, некорректный `params` или `min > max` → `RequirementError`. |
| `approve_profile(session, profile_id, *, approved_by_user_id=None, note=None)` | `Session`, UUID профиля | Переводит прежний `approved` профиль этой должности в `archived`, ставит выбранному `status="approved"`, `approved_by_user_id`, `approved_at=now()`. Не коммитит. | Профиль не найден или уже `archived` → `RequirementError`. |
| `get_approved_profile(session, position_id)` | `Session`, UUID должности | Полная DTO-структура утверждённого профиля (с формальными требованиями и компетенциями с индикаторами) или `None`. | — |
| CLI: `uv run python -m app.requirements load <file.json> [--approve]` | путь к JSON | Загружает черновик (и при `--approve` утверждает его), печатает `profile_id`, `version`, `status`. | Код выхода `!= 0` и причина ошибки. |

## 5. Второй контрольный пример (`hr-consultant`)

Для муниципальной должности `hr-consultant` (по ДИ и эталонной матрице заказчика):
- `formal_requirements`:
  1. `education_level`: `{"min_level": "высшее"}`, `is_mandatory: true`;
  2. `education_field`: `{"fields": ["Юриспруденция", "Государственное и муниципальное управление"], "retraining_allowed": true}`, `is_mandatory: true`;
  3. `experience`: `{"min_years": 0.0, "scope": "municipal_service", "allow_equivalent": false}`, `is_mandatory: true` (стаж не требуется → `met`);
  4. `knowledge`: `{"topics": ["25-ФЗ", "131-ФЗ", "ТК РФ", "59-ФЗ", "антикоррупционное законодательство", "Устав города"], "verify_at_interview": true}`, `is_mandatory: false` (или проверяется на интервью; окончательный флаг `is_mandatory` Давид сверяет по тексту п. 2 ДИ в `stage-0b-01`).
- `competencies`: ранги `key` (КР: `ПАК`, `ИТК`), `basic` (БР: `РК`, `ОИК`), `special` (СР: `ДК`), диапазон `90..100`, индикаторы дословно из эталонной матрицы заказчика.
