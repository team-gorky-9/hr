# Контракт: модуль импорта и очистки (`app/ingest/`)

**Версия:** 0.1 (проект к Этапу 0а/1) · **Дата:** 2026-11-19 · **Владелец:** Денис · **Потребители:** модуль оценивания (`app/assessment/`), HTTP API (`app/api/`).

Опирается на [database.md](database.md) v1.0 (пп. 2.1–2.3, 2.8, 2.14, 4.1–4.2, 6, 7, 11.7).

## 1. Назначение и границы

Модуль `app/ingest/` принимает пакет исходных документов (TXT, DOCX, PDF с текстовым слоем или выгрузку `corpus.jsonl` + `originals/`), отделяет персональные данные в `candidate_pii`, формирует очищенный текст `candidate_texts` версии 1 и создаёт отклик `applications` в статусе `new`.

**Жёсткие инварианты:**
1. Вся запись в БД идёт только через функции `app/db/repository.py` (`add_source_document`, `create_candidate`, `create_application`, `write_audit`). Транзакцией управляет импорт: ошибка на середине обработки одной записи откатывает только эту запись и не оставляет «полусозданного» кандидата.
2. В `candidate_texts.text` не попадают ФИО, телефоны, email, даты рождения, возраст, пол, ссылки на профили (`github.com/...`, `t.me/...`, `vk.com/...`, `linkedin.com/...`). Грамматический род глаголов («работала») **не** переписывается (`database.md`, п. 11.7).
3. Если очистка ПДн не прошла проверку, файл не распознан (например, PDF-скан без текстового слоя) или вакансия не определена однозначно — запись уходит в **карантин** (в БД не создаётся `candidate_texts` для модели), а в отчёте фиксируется безопасный идентификатор и причина без текста резюме и без ПДн.
4. Все пути нормализуются в Unicode NFC (`database.md`, п. 2.14), переносы строк в `raw_text` и `candidate_texts.text` приводятся к `\n`.

## 2. Вход импорта

Модуль поддерживает запуск локальной CLI-командой (формат аргументов выбирает владелец, пример ниже):

```bash
uv run python -m app.ingest --input <папка_пакета> --mapping <файл_маппинга.json> [--batch <метка>]
```

### 2.1. Входной пакет (два равноправных режима)
1. **Выгрузка парсера архива:** каталог с `corpus.jsonl` (поля: `source_path`, `original_file`, `format`, `sha256`, `text`) и подкаталогом `originals/` (байты оригинальных файлов для расчёта `sha256` в `add_source_document`).
2. **Автономный синтетический пакет (для тестов и локальной приёмки без архива):** каталог с файлами `.txt`/`.docx`/`.pdf` и файлом маппинга. Извлечение текста из `.txt`/`.docx`/`.pdf` должно совпадать по правилам нормализации (UTF-8/CP1251, XML-таблицы DOCX без дублирования объединённых ячеек, PDF только с текстовым слоем; скан без текста → ошибка `PDF_NEEDS_REVIEW`).

### 2.2. Явное сопоставление с вакансией (`mapping`)
Импорт **не угадывает** должность эвристикой по тексту резюме. Источник сопоставления — либо `POSITION_CODE_BY_FOLDER` из `app/db/seed.py` (для известной папки архива), либо явная таблица/JSON-манифест маппинга:

```json
{
  "entries": [
    {
      "source_path": "Python-разработчик/py-9001.txt",
      "candidate_code": "py-9001",
      "position_code": "python-dev",
      "channel": "hh_ru",
      "document_kind": "resume",
      "file_format": "hh_txt"
    }
  ]
}
```

Допустимые значения `document_kind`, `channel`, `file_format` соответствуют перечислениям `app/db/enums.py`. Служебные документы (`job_description`, `vacancy_posting`, `competency_matrix`, `regulation`) сохраняются только в `source_documents` (или явно исключаются из потока откликов с отметкой в отчёте) и **не** создают `candidates` и `applications`.

## 3. Правила дедупликации и конфликтов

| Ситуация | Ожидаемое поведение | Статус в отчёте |
|---|---|---|
| Новый файл (новый `sha256` байтов оригинала) + валидная вакансия | Создаются `source_document`, `candidate`, `candidate_pii`, `candidate_text` (v1), `application` (`new`) | `imported` |
| Повтор тех же байтов (тот же `sha256`, даже если файл переименован) + та же вакансия | Дубль не создаётся; возвращаются существующие `source_document` и `application` | `duplicate_skipped` |
| Те же байты (тот же `sha256`), но **другая** вакансия | Используется существующий `candidate`, создаётся новый `application` на новую вакансию | `application_added` |
| Разные файлы (разный `sha256`) с одинаковым извлечённым текстом и разными `code` | По ADR-002 Р2 — два отдельных `source_document` и два `candidate`, в отчёте ставится предупреждение `duplicate_text_warning` | `imported` (с флагом warning) |
| Тот же `candidate_code`, но **другие байты** (`sha256` не совпадает с существующим кандидатом) | Не перезаписывается молча; запись уходит в карантин на ручную сверку | `conflict` |
| Неизвестный `position_code`, пустой текст, `PDF_NEEDS_REVIEW`, сбой очистки ПДн или ошибка парсинга | Откат транзакции по записи, карантин с причиной | `quarantined` / `error` |
| Служебный файл (`job_description`, `vacancy_posting`, др. не-резюме) | Не создаёт кандидата/отклик | `excluded_non_resume` |

## 4. Выход (отчёт прогона)

Команда печатает (и опционально сохраняет в JSON) однозначный отчёт прогона. В отчёт **запрещено** включать `raw_text`, фрагменты резюме и значения ПДн.

```json
{
  "import_batch": "stage-0a-smoke-2026-11-19",
  "started_at": "2026-11-19T18:00:00+03:00",
  "finished_at": "2026-11-19T18:00:01+03:00",
  "counts": {
    "total": 4,
    "imported": 2,
    "application_added": 0,
    "duplicate_skipped": 0,
    "excluded_non_resume": 1,
    "conflict": 0,
    "quarantined": 1,
    "error": 0
  },
  "items": [
    {
      "source_path": "Python-разработчик/py-9001.txt",
      "sha256": "<64-hex>",
      "status": "imported",
      "candidate_code": "py-9001",
      "candidate_id": "<uuid>",
      "candidate_text_id": "<uuid>",
      "application_id": "<uuid>",
      "reason": null
    },
    {
      "source_path": "Python-разработчик/broken-scan.pdf",
      "sha256": "<64-hex>",
      "status": "quarantined",
      "candidate_code": null,
      "candidate_id": null,
      "candidate_text_id": null,
      "application_id": null,
      "reason": "PDF_NEEDS_REVIEW: страница без текстового слоя"
    }
  ]
}
```

## 5. Сквозной контрольный пример (`py-9001`)

- **Вход:** синтетический `py-9001.txt` на `python-dev`, содержащий синтетические контакты (ФИО, телефон, email, ссылку `https://github.com/test-ivanov`) и контрольную фразу `Написал API-тесты для сервиса заявок.`.
- **Результат в БД:**
  - `source_documents`: исходный файл с `sha256` байтов оригинала и `raw_text` как есть;
  - `candidates`: `code = "py-9001"`;
  - `candidate_pii`: синтетические ФИО, телефон, email и ссылка `https://github.com/test-ivanov`;
  - `candidate_texts` (v1, `is_current = true`): очищенный текст **без** ФИО, телефона, email и ссылки, но с точно сохранённой фразой `Написал API-тесты для сервиса заявок.`;
  - `applications`: отклик на вакансию `python-dev` (`hh_ru`) в статусе `new` + 1 запись в `stage_events`.
- **Повторный запуск** того же пакета (включая копию `py-9001.txt` с другим именем файла, но теми же байтами): `duplicate_skipped`, число записей в `candidates`, `candidate_texts` и `applications` не меняется.
