# Wave 4B · годовой выпуск по доступным фактам · этап 1

**21 ноября 2026 · Илья.**
- Ветка `feature/wave-4b-annual-source` от `hr` `main` `22df231` (4A уже в main).
- Карточка — `hq/tasks/stage-1/wave-4b-ilya-annual-source.md` в штабе.
- Контракт — [wave-4-reporting-stage-1](../contracts/wave-4-reporting-stage-1.md), раздел 4B. Описание — [management.md](../modules/management.md#4b--годовой-выпуск-из-доступных-фактов).

## Что сделано

- Три новых маршрута в `app/management/annual.py` и `api.py`:
  - `POST /api/v1/management/annual-reports`;
  - `GET /api/v1/management/annual-reports/{snapshot_id}`;
  - `GET /api/v1/management/annual-reports/{snapshot_id}/xlsx`.
- Пакет фактов собирается из своих `Application` (response) и `Interview` (phone) в формате действующего контракта годового отчёта. Затем он проходит через существующие `load_package`, `generate` и `store.save` и выгружается в Excel через `make_workbook`. Загрузчик, расчёт и формат снимка не менялись.
- Реестр выпусков `annual_report_releases` (миграция `0012`, `alembic check` чистый) хранит контур, заявленную полноту, основание, итог подготовки и автора.

## Проверка

**Через HTTP.**
- Окружение: учебная база `hr_demo` (PostgreSQL 16), встречи из проверки 4A.
- `HR_REPORTS_DIR` — временный каталог, `uvicorn app.main:app --port 8000`.
- Команда: `uv run python scripts/check_management_annual.py`.

| Шаг | Результат |
|---|---|
| POST, 2026, `observed_until=2026-11-21`, учебный контур, полнота заявлена для откликов за 01.11–21.11 | 201, `mode=demo`, `interim=true`, период 2026-01-01…2026-11-21 |
| Подготовка | откликов 15 (1 без даты), встреч 4; 2 встречи 21.11 исключены как `interviews_after_cutoff` |
| Итоги | `applications_received` 14 (partial: `missing_business_date`, `coverage_gap`); `phone_interviews_held` **1** (partial: `coverage_gap`). Две попытки `no_answer` к проведённым не прибавлены |
| GET JSON и xlsx | 200, Excel 18 776 байт из того же снимка |
| Поздняя поправка: итог открытой встречи py-9106 внесён после выпуска | новый POST → новый `snapshot_id`, `phone_interviews_held` 2. Прежний выпуск читается без изменений |
| Роль department | 403 `FORBIDDEN_ROLE` |
| `observed_until` в будущем | 422 `INVALID_OBSERVED_UNTIL` |

**Тесты.** `uv run pytest tests/test_management_annual.py` → 3 passed:
- частичная полнота;
- `phone_interviews_held=1` при `no_answer` рядом;
- недатированные отклик и итог встречи;
- в снимке нет ФИО;
- JSON и Excel из одного снимка;
- новая версия после поправки;
- точный `complete` при заявленной полноте за два года;
- отказы: department, будущая дата, интервал за пределами `observed_until` → `PREPARATION_FAILED`, неизвестный и неверный id; отказы не оставляют выпусков.

Полный `uv run pytest` → **893 passed**, 0 пропусков.

## Для интерфейса

`POST /api/v1/management/annual-reports` → `report_url`, `xlsx_url`. Отчёт отображается так же, как существующий годовой (`report` — тот же формат снимка, что у `/api/v1/reports/annual/{id}`). Статус и причины полноты показывать рядом с числом. `coverage_summary.note` объясняет, что это не полная кадровая статистика организации.

## Ограничения

- Источник — только журнал legacy-hr: отклики площадки и телефонные встречи выбранного контура. Встречи `department`, история общения и ручные записи в выпуск не входят.
- Полноту заявляет HR, сервис её не проверяет по внешнему журналу. Основание сохраняется в выпуске.
- Учебные выпуски (`mode=demo`) видны и через анонимный `/api/v1/reports/annual`, как все учебные снимки годового модуля. Рабочие (`mode=work`, scope `legacy-hr-working`) — только через `/management` либо сервисный ключ отчётов этого охвата.
- Выпуск не подписывает пакет отдельной ревизией источника: `source_revision` равен моменту выгрузки.
