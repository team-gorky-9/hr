# Волна 6 · факты, показатель и Excel · демонстрационная сборка

**21 ноября 2026 · Илья.**
- База — `hr` `main` `01de7a5`: включает помощь #69–72, фронтенд #68, кандидата #66/67/73 и обратную связь #74–77.
- Карточка — `hq/tasks/stage-1/wave-6b-ilya-report-demo.md` в штабе.
- Контракты — [wave-4-reporting-stage-1](../contracts/wave-4-reporting-stage-1.md) (4B), [reporting.md](../contracts/reporting.md). Описание адаптера — [management.md](../modules/management.md#4b--годовой-выпуск-из-доступных-фактов).

**Предшествующая задача — 6A**, путь HR и кандидата: [отчёт](wave-6-recruitment-demo.md).
**Адаптер отчёта — 4B**, в main с hr#57: `POST /api/v1/management/annual-reports` собирает пакет из откликов и встреч legacy-hr, считает его существующим годовым модулем и отдаёт JSON и Excel одного снимка.

## Набор и команды

Маленький учебный набор на отдельной пустой базе, только синтетика. Готовит его `scripts/check_report_demo.py --prepare`:
- 4 отклика площадки на python-dev — `rep-9001` 15.09, `rep-9002` 03.11, `rep-9003` 10.11, `rep-9004` 12.11;
- по одной телефонной встрече на отклик.

Итоги встреч записываются штатной операцией `POST /api/v1/interviews/{id}/outcome`:
- `rep-9002` — continue 05.11;
- `rep-9003` — no_answer 11.11;
- поздняя поправка: `rep-9004` — continue 12.11.

```bash
createdb hr_report   # + CREATE EXTENSION vector
DATABASE_URL=…/hr_report uv run alembic upgrade head
DATABASE_URL=…/hr_report uv run python scripts/check_report_demo.py --prepare
DATABASE_URL=…/hr_report HR_REPORTS_DIR=/srv/hr/annual-reports uv run uvicorn app.main:app --port 8000 &
DATABASE_URL=…/hr_report uv run python scripts/check_report_demo.py \
  --transcript docs/reports/wave-6-report-demo.transcript.json --xlsx docs/reports/wave-6-report-demo.xlsx
```

Параметры выпуска:
```json
{"year": 2026, "observed_until": "2026-11-21", "contour": "training",
 "coverage": {"applications": {"complete_intervals": [{"from": "2026-09-01", "to": "2026-11-21"}],
                               "comparable_to_previous_year": false}},
 "confirmation_basis": "Учебный набор волны 6: полнота заявлена только для откликов с 01.09.2026 (учебно)"}
```

Источник — журнал legacy-hr (`legacy-hr.applications`, `legacy-hr.phone_interviews`), контур training, `mode=demo`. Полнота заявлена только для откликов, для телефонных встреч — нет.

## Результат

| Шаг | Наблюдение |
|---|---|
| `POST /management/annual-reports` | 201, `snapshot_id` **`be9884136d7eb4ed2f03b223595560c012df5120ea399efdcf5e66562453ac54`**, период 2026-01-01…2026-11-21, `interim=true` |
| `GET /management/annual-reports/{id}` | 200; повторное чтение совпадает с первым |
| `GET …/xlsx` | 200, книга 18 376 байт с листами «Итоги», «Помесячно», «Вакансии», «Методика», «К докладу»: [`wave-6-report-demo.xlsx`](wave-6-report-demo.xlsx) |

**Эталонные числа для Аси.** Показатель — `applications_received` по месяцам.

| Месяц | Отклики | Разговоры (`phone_interviews_held`) |
|---|---|---|
| 2026-09 | **1** · complete | **null** · unavailable (`coverage_unknown`) |
| 2026-10 | **0** · complete — подтверждённый ноль | **null** · unavailable (`coverage_unknown`) |
| 2026-11 | **3** · complete | **1** · partial (`coverage_gap`) — нижняя граница |
| Год | **4** · partial (`coverage_gap`) | — |

- **Ноль и отсутствие источника различаются.** В октябре отклики `0 complete` — полнота заявлена, откликов нет. Разговоры `null unavailable` — источник без заявленной полноты, это не ноль.
- **Недозвон не считается разговором.** `no_answer` 11.11 к разговорам ноября не прибавлен: значение 1, это только continue 05.11.
- **Годовой итог неполный.** Он `partial`, потому что январь–август в заявленную полноту не входят.

**Поздняя поправка.** Итог встречи `rep-9004` внесли после выпуска.
- Новый `POST` дал новый снимок **`51cfeaa248a0b83c766076333161b989f4122e1e79140d71608248bd186e6e74`**: разговоры ноября 1 → **2** (partial).
- Прежний снимок перечитан без изменений, поправка в него не попала.

**Отрицательные случаи.**
- Роль department → 403 `FORBIDDEN_ROLE`.
- Интервал полноты до 2026-12-01 (за `observed_until`) → 422 `PREPARATION_FAILED`, выпуск не создан.

Все запросы и ответы — в [`wave-6-report-demo.transcript.json`](wave-6-report-demo.transcript.json). Из снимка там приведены заголовок, итоги и месяцы 09–11, полный снимок читается по `report_url`.

## Интерфейс (наблюдение в браузере)

Прототип #68 открыт в Chromium (Playwright, `vite`): «Кабинет HR-менеджера» → «Аналитика» → «Годовой доклад». Снимок — [`wave-6-report-demo-prototype.png`](wave-6-report-demo-prototype.png).

Экран показывает числа макета: «Годовой кадровый доклад · 2025», 1 077 откликов. Запросов к `/api/` не было. Соответствие для подключения:

| Элемент прототипа | API | Что учесть |
|---|---|---|
| «Версия доклада» (список) | реестр выпусков 4B; `snapshot_id` из ответа `POST` | Отдельного списка выпусков `/management` нет. Версии годового модуля — `GET /api/v1/reports/annual` (учебные снимки видны и там) |
| Карточки «откликов / разговоров / разных откликов с разговором» | `report.totals.applications_received` / `phone_interviews_held` / `applications_with_phone_interview` | Рядом с числом показывать `status` и `reason_codes`. `null` при `unavailable` — «нет данных», не 0 |
| «Скачать годовой XLSX» | `xlsx_url` | — |
| Вкладка «Покрытие и состояния» | `release.coverage_summary` (`declared`, `totals_status`, `note`) и `report.sources` | — |
| «Штат и ответы подразделений», «116 сотрудников» | — | Адаптер 4B не включает штат и передачи (`operations`) — Workforce не подключён |
| «Сводка ИИ» | `GET /api/v1/reports/annual/{id}/brief` годового модуля | Через `/management` не проксируется |

## Ограничения

- Источник — только журнал legacy-hr. Полноту заявляет HR, сервис её не проверяет.
- Штат, передачи и внешние источники в выпуск не входят.
- Учебный выпуск (`mode=demo`) читается и анонимно через `/api/v1/reports/annual`, как все учебные снимки годового модуля.
- Код адаптера не менялся. Дефектов, мешающих показу, на прогоне не обнаружено, исправлений не было.
- Фронтенд к API не подключён.
