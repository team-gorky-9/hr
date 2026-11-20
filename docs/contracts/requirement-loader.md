# Публичный загрузчик требований · 1.0

Дополнение от 20.11.2026 к [профилям 0.2](requirements.md). Владелец — Давид. Существующие интерфейсы repository, форматы `params` 0.1, пакет 0.2 и схема БД v1.7 не изменяются. Это новый интерфейс; переход существующих потребителей на него не предполагается автоматически.

## Python API

Экспорт из `app.requirements`:

```python
validate_draft(data)  # -> ProfileDraft, без БД
load_profile_draft(session, data, *, created_by)  # -> RequirementProfile (draft)
load_package(session, package, manifest, source_root, *, created_by,
             synthetic_profile=None)  # -> PackageResult(profiles, review_fields)
approve_profile(session, profile_id, *, approved_by_user_id, approval_basis)
get_approved_profile(session, position_id, *, synthetic=False)
```

Идентификаторы — `uuid.UUID`, session — SQLAlchemy `Session`. Создание/утверждение возвращает ORM-профиль в текущей сессии. Чтение возвращает ORM-профиль или `None`. Функции не делают commit; write-операции атомарны внутри SAVEPOINT. Неизвестная должность, невалидные строки, отсутствующие источники и запрещённое утверждение дают `RequirementError`. Ошибки подключения/программирования не маскируются под ошибку профиля.

`load_profile_draft` выбирает `max(version)+1` отдельно для должности и `is_synthetic`. `load_package` сохраняет точные версии из пакета, повтор — `version_conflict`. Обе операции создают только draft. Утверждение требует существующего активного HR/admin и непустого основания; предыдущий approved архивируется в том же контуре. Повторное утверждение approved или archived запрещено.

## Нормализованный JSON

Корень: обязательные `schema_version="requirement-draft/1.0"`, `position_code`, boolean `is_synthetic`, массивы `formal_requirements`, `competencies`; опциональные `sources=[]`, `note=null`. Пустой профиль запрещён. `version`, `status` и метаданные утверждения во входе запрещены.

Строки соответствуют `FormalRequirementIn`, `CompetencyIn`, `IndicatorIn`, `ProfileSourceIn` из [общих схем](../../app/schemas/requirements.py): текст условия — `description`, компетенции — `name`, индикатора — `text`; `rationale` пакета здесь называется `note`. `sources` ссылаются на уже зарегистрированные UUID документов. Для источника строки обязательны адрес и цитата; для строки команды — объяснение `note`. Обязательность и этапы по умолчанию совпадают с общими схемами БД. В пакете 0.2 обязательность и способ проверки передаются явно.

Неизвестные поля, виды правил и версии `params` отклоняются. Булевы поля не принимают строки/числа, целые пороги не принимают строки, float или bool. Остальные ограничения — из общих схем: диапазоны 0–100, уникальные ключи/коды, связь образования, правила `same_as`. Содержательное принятие требований этой валидацией не выполняется.

Полный вход — [py-9001.draft.json](../../fixtures/requirement_profiles/py-9001.draft.json). Пакет реальных профилей — [profiles.draft.json](../../fixtures/requirement_profiles/profiles.draft.json), манифест — [sources.json](../../fixtures/requirement_profiles/sources.json).

## Ошибки и CLI

`RequirementError.as_dict()` возвращает `code`, понятное `message`, `path` поля или null. В сообщении нет входных значений, SQL и неизвестных имён полей. Причина сохраняется в цепочке исключений для разработчика, поэтому публичный обработчик должен сериализовать `as_dict()`, а не traceback.

| Код | Причина |
|---|---|
| `invalid_profile` | Схема строки/профиля или общая проверка repository |
| `invalid_package`, `invalid_json`, `invalid_arguments` | Оболочка пакета, JSON или сочетание аргументов |
| `position_not_found`, `profile_not_found`, `source_not_found` | Ссылка на отсутствующую сущность |
| `source_mismatch`, `source_unavailable`, `unsupported_source`, `file_unavailable` | Файл, путь, хеш, абзац или цитата |
| `version_conflict`, `database_constraint` | Повтор фиксированной версии или ограничение хранения |
| `approval_refused` | Не draft, отсутствующий/неактивный утверждающий, роль или основание |

Команды и примеры — [устройство модуля](../modules/requirements.md). CLI возвращает JSON: `status`, `persisted`, `profiles` (UUID, версия, контур, статус и счётчики), `review_fields`. Без `--commit` status=`dry_run`, при сохранении load/load-package — `loaded`, отдельного approve — `approved`. У составного load --approve статус операции `loaded`, а профиля — `approved`. Отказ: status=`refused`, `error` из RequirementError, exit 1. Ошибка соединения: status=`unavailable`, code=`database_unavailable`, exit 2. Ошибка синтаксиса аргументов обрабатывается argparse (stderr, exit 2). Успех — exit 0.

CLI предназначен для доверенного оператора с доступом к БД: `--approver` фиксирует существующего пользователя и проверяет его роль, но не является аутентификацией HTTP-пользователя.
