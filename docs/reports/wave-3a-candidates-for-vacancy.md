# Wave 3A · люди под выбранную вакансию · этап 1

**21 ноября 2026 · Илья.**
- Ветка `feature/wave-3a-candidates-for-vacancy` от `hr` `main` `ec0a764`, база спецификации hr#45 `c22fa51`.
- Карточка — `hq/tasks/stage-1/wave-3a-ilya-candidates-for-vacancy.md` в штабе.
- Контракт — [wave-3-matching-stage-1](../contracts/wave-3-matching-stage-1.md), раздел 3A. Описание модуля — [matching.md](../modules/matching.md).

## Что сделано

- `POST /api/v1/matching/candidates`: снимок вакансии + `filters` + `limit` → записи действующего поиска со статусом оценки по точному профилю (`app/matching/`).
- `app/search/api.py`: проверка ключа рабочего контура и вызов поиска вынесены в `require_search_access` и `run_search`. Их использует и `/search`, и `/matching`. Поведение `/search` не изменилось, его тесты проходят.
- Исправление предыдущей поставки (wave-2): `GET /applications/{id}/interviews` упорядочивал встречи одной транзакции по случайному `id`. Теперь при равном `created_at` завершённые идут раньше открытой. Дефект проявился в полном прогоне как падение `test_guide_after_completed_interview_opens_next_pending`. После исправления полный прогон дважды зелёный.
- Миграций нет: подбор ничего не сохраняет.

## Проверка

**Через HTTP.**
- Окружение: учебная база `hr_demo` (PostgreSQL 16), `python -m app.search load-demo`, `uvicorn app.main:app --port 8000`, плотная ветка выключена.
- Команда: `uv run python scripts/check_matching_candidates.py`.

| Шаг | Результат |
|---|---|
| Вакансия `…00a1`, `search_query` «анализ и согласование требований к ИС», limit 3 | 200, `source_mode=provided`, `observed_at=2026-11-21T09:00:00+03:00`. Первая — `search-9015`: «Анализ и согласование требований к ИС при модернизации портала…», `not_evaluated/no_profile_ref` |
| + `required_terms: ["SAP ERP"]` | 200, `items: []` |
| `status: closed` | 409 `VACANCY_NOT_PUBLISHED` |
| `contour: working` без ключа поиска | 401 `SEARCH_AUTH_REQUIRED` |
| `dept_demo` | 403 `FORBIDDEN_ROLE` |
| python-dev с `profile_ref` на утверждённый учебный профиль | 200. В `hr_demo` оценок нет (база собрана `--no-llm`), поэтому `not_evaluated/not_assessed` — без ложного допуска |

**Тесты.** `uv run pytest tests/test_matching_candidates.py` → 3 passed:
- фрагмент `search-9015` проверяется по `GET /candidate-texts/{id}`;
- пустая выдача по отсутствующему термину;
- число откликов и записей резерва не меняется;
- отказы: закрытая вакансия, рабочий контур, роли, неверные входы;
- длинное описание принимается;
- статус оценки `met`/`unknown` с `assessment_id` по точному профилю (FakeLLMClient) и `not_evaluated` при другой версии, неизвестном, catalog-профиле и чужой должности.

Полный `uv run pytest` → **881 passed**, 0 пропусков, прогон дважды.

## Для интерфейса

`POST /api/v1/matching/candidates`, схемы `CandidatesForVacancyIn` / `CandidatesForVacancyOut` в `/openapi.json`. Цитату подсвечивать так же, как в поиске: `GET /api/v1/candidate-texts/{candidate_text_id}` и `utf16_start/utf16_end`. Формальный статус показывать отдельно от поискового совпадения: `not_evaluated` — не «подходит».

## Ограничения

- `source_mode=catalog_api` не реализован: адаптера к каталогу вакансий Дениса нет, вход — предоставленный HR снимок.
- `profile_ref.system=catalog` всегда `unmapped_profile`, пока нет подтверждённого отображения на legacy-профили.
- Права на контакт в ответе нет: в продукте нет такого поля. Прежние отклики видны в `applications`.
- Плотная (смысловая) ветка в HTTP-проходе выключена. С индексом порядок может отличаться, как и в `/search`.
