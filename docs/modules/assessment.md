# Модуль оценки

Для команд утверждения ниже заранее нужен существующий активный HR/admin. Актуальный seed создаёт учётку стенда `hr_demo` (с подчёркиванием); в рабочей среде укажите логин уполномоченного кадровика. Сам скрипт утверждения не создаёт пользователей и не меняет роли. Новый маршрут загрузки и утверждения — [модуль requirements](requirements.md).

Контракт: [assessment v0.3](../contracts/assessment.md). Интеграция `feature/profile-assessment-integration`: main fc61d26 + профили 905ea9b + ai-01 c94285e. [Проверки и ограничения](../reports/profile-assessment-integration.md).

## Путь данных

1. CLI выбирает профиль через get_approved_profile с явным контуром; draft для учебного кандидата задаётся по ID. Для основного отбора передаётся ID отклика; сравнение включается явно через purpose=comparison.
2. `orchestration.assess_in_context` проверяет кандидата, профиль, все params, as_of и отклик до модели. Для hr-consultant resolver проверяет posting_title. Если соответствие не установлено или должность другая, primary пишет skipped без оценки кандидата.
3. `service.assess_candidate` получает текущий очищенный текст. Подходящая карточка переиспользуется; иначе извлекается CandidateCard. В модель не передаются raw_text и candidate_pii.
4. Формальная модель получает критерии acceptance, альтернативы и описание релевантности. Компетентностная — только screening-индикаторы с acceptance. Код находит позиции цитат, считает включительные месяцы и границы [L,U], объединяет альтернативы. Вывод без цитаты понижается; необходимость документа оставляет met предварительным.
5. `counters` сводит same_as: одна единица в компетенции, обязательность OR, конфликт подтверждения и противоречия требует ручной сверки. Интервью-группы и исключённые строки считаются отдельно. Численный уровень и общий процент не придумываются.
6. Repository проверяет все вложенные цитаты и результаты, сохраняет formal_checks.alternatives и competency_scores.details, algorithm_version и calculation_as_of. Контекст запуска записывается отдельно в audit_log. API заново применяет политику к отклику и не выдаёт сравнение за основной отбор.

## Компоненты

| Файл | Ответственность |
|---|---|
| app/ai/client.py, config.py | Провайдер, структурированный ответ, повторы, метаданные вызовов |
| app/assessment/applicability.py + policies/ | Версионируемое точное сопоставление публикаций |
| app/assessment/orchestration.py | Контекст, проверки до модели, повторное использование пары, manifest |
| app/assessment/service.py | Извлечение и оценка по очищенному тексту |
| app/assessment/rules.py | Проверка params общей схемой и разбор правил |
| app/assessment/experience.py, evidence.py | Стаж и позиции цитат |
| app/assessment/counters.py | Группы и счётчики по компетенции/профилю |
| app/schemas/competency_details.py | Типизированный результат с отдельными цитатами |

## Сквозной прогон `py-9001` (qa-01)

Из чистой базы до оценки, которую читает API. Учебный кандидат и учебный профиль; на шаге 6 нужен ключ YandexGPT в `.env`.

```bash
docker compose up -d
uv run alembic upgrade head                                                          # 1. схема
uv run python -m app.db.seed                                                         # 2. справочники
uv run python -m app.ingest --input fixtures/stage_0a --mapping fixtures/stage_0a/mapping.json   # 3. py-9001 (учебный)
uv run python -m scripts.load_synthetic_profile                                      # 4. учебный профиль — черновик
uv run python -m scripts.approve_profile --position-code python-dev --synthetic \
    --approver hr_demo --basis "учебный профиль для qa-01" --commit                  # 5. утверждение кадровиком
APP=$(docker compose exec -T db psql -U hr -d hr -Atc \
  "select a.id from applications a join candidates c on c.id = a.candidate_id where c.code = 'py-9001' and a.source = 'response'")
uv run python -m app.assessment run --candidate-code py-9001 --position-code python-dev \
    --technical --application-id "$APP" --as-of 2025-11                              # 6. оценка по отклику
uv run uvicorn app.main:app                                                          # 7. API
curl -s "http://127.0.0.1:8000/api/v1/applications/$APP" | python -m json.tool | head -40
```

Ожидается: на шаге 6 `status: ok`; в API `assessment_status: ready`, формальная проверка стажа и компетенция с цитатой «Написал API-тесты для сервиса заявок.». Срез `text[utf16_start:utf16_end]` из `GET /api/v1/candidate-texts/{candidate_text_id}` совпадает с `quote`.

- Без шага 5 API отвечает `no_approved_profile`: загрузчик и оценщик профиль не утверждают, это отдельное действие кадровика. `approve_profile` без `--commit` только показывает, что будет утверждено.
- Повторное утверждение того же контура отправляет прежнюю версию в архив; рабочий контур не меняется.
- База, импортированная до БД v1.5, считает `py-9001` реальным кандидатом — её нужно пересоздать.

## Кросс-оценка по всем должностям (ai-02)

Один человек × утверждённые профили всех должностей своего контура. Код — `app/assessment/cross.py`.

```bash
uv run python -m app.assessment batch --all-approved --technical --candidate-code py-9001 --dry-run   # пары и оценка времени
uv run python -m app.assessment batch --all-approved --technical --candidate-code py-9001 --as-of 2025-11
uv run python -m app.assessment batch --all-approved --position-code hr-consultant --limit 20 --skip-existing --workers 4
```

- **Людей выбирает оператор:** `--candidate-code` (можно несколько раз), `--position-code` (должность исходного отклика), `--limit`. Без выбора команда откажет: весь архив × 6 профилей — это часы работы модели. `--dry-run` показывает пары и оценку времени (~10 с на пару).
- **Цель пары:** должность собственного прямого отклика — `primary`, с проверкой применимости публикации; остальные — `comparison`. Отклики, события этапа и записи резерва не создаются.
- **Карточка** извлекается один раз на версию текста. Пары одного человека идут последовательно, `--workers N` параллелит разных людей.
- **Повтор.** Оценка пары переиспользуется при совпадении версий текста, алгоритма (включает версии промптов), промпта и `as_of`. С `--skip-existing` такие пары пропускаются без записи и без вызова модели. Если параллельный запуск уже записал пару, повтор берёт готовую оценку: одна текущая оценка на пару гарантируется уникальным индексом.
- **Отчёт:** `people`, `pairs`, `counts` по исходам (`assessed`, `reused`, `skipped_current`, `skipped_context`, `error`) — сумма равна числу пар. В `explained` — должности без утверждённого профиля и коды не того контура. Пара с ошибкой доступна для повтора.

Чтение для API — `cross_assessments(session, candidate_id, application_id=None)`; маршрут `GET /api/v1/candidates/{candidate_id}/cross-assessments` подключает модуль API (backend-02) без своей логики. По каждой должности контура возвращается:
- должность (`position_id`, код, название, `is_municipal_service`), утверждённый профиль и его версия, `is_training`, признак `is_source_position` (прямой отклик `response` на вакансию должности);
- `vacancies` — все вакансии должности, у каждой отклик кандидата (`application_id`, `source`, этап) или `null`;
- `assessment_status` и `stale_reason` — по общему правилу `app.assessment.state.resolve_states`, тому же, что у списка откликов: `text_changed`, `algorithm_changed` (алгоритм или промпт), `profile_changed`;
- оценка: профиль самой оценки (при `profile_changed` — прежняя версия), формальный итог, предварительность, `overall_score`, пробелы, проверки и компетенции (код, название, ранг, целевой уровень, `level`, счётчики) с цитатами. У цитаты `start/end` и `utf16_start/utf16_end` по тексту, на который она ссылается, в том числе прежней версии (`state.evidence_with_utf16`).

Кроме того, ответ содержит отклики кандидата с этапом. Если утверждённых профилей нет — `items = []` и `empty_reason = no_approved_profiles`.

`app/assessment/state.py` — общие правила для API и кросс-оценки: статусы оценки, `resolve_states`, сбор текстов цитат и границы UTF-16. Раньше у API и у кросс-оценки были свои копии, и статус одной пары мог различаться.

## Запуск и проверка

После настройки .env и миграций:

```bash
uv run python -m app.assessment run --candidate-code py-9001 --position-code python-dev --technical --purpose comparison --profile-id <draft-profile-uuid> --as-of 2026-11
uv run python -m app.assessment run --candidate-code <real-code> --position-code hr-consultant --application-id <application-uuid> --as-of 2026-11
uv run python -m scripts.replay_requirement_cases --mode controlled --output controlled.json
uv run python -m scripts.replay_requirement_cases --mode live --output live.json
uv run python -m scripts.report_profile_applicability <archive.zip> --output coverage.json
uv run pytest
```

Для pytest полной БД требуется PostgreSQL с pgvector и отдельная TEST_DATABASE_URL с именем базы, заканчивающимся `_test`. Тесты очищают её схему. Controlled replay проверяет правила кода на прежних 41 случаях. Live replay проверяет формальное извлечение, не извлечение CandidateCard и не качество полной оценки; эталон в живой промпт не передаётся. 16 содержательных примеров проверяются отдельно; случаи интервью проверяют только отсутствие в screening.

as_of фиксирует месяц расчёта текущего стажа; дата резюме сама не выводится. Старые оценки с другой algorithm_version API помечает stale. При обновлении содержимого уже загруженного профиля создаётся новая версия; approve не выполняется загрузчиком или оценщиком.

В `assessment-2.0.3` прямое отрицание опыта распознаётся и с областью в начале фразы: «В тестировании ПО опыта нет», «По разработке интерфейсов опыта нет». Такое отрицание опровергает требование, только если все значимые слова области есть в `relevance_hint` этого требования: «В тестировании ПО опыта нет» даёт not_met для QA и unknown для Python; область-время («В 2022 году») не считается. Отсутствие сведений в резюме/анкете/описании и отсутствие недостатка или проблем с опытом не подтверждают отрицание опыта. Регрессии проверяют формальный результат с цитатой; пакет requirements-02 дополнительно сравнивает один учебный отклик по Junior Python и QA и проверяет неизменность этапа. Формат результата и правило решения руководителя не меняются; версия вычислителя повышена, чтобы предыдущие оценки не считались рассчитанными этой редакцией.

В `assessment-2.0.4` альтернатива «студент старших курсов» подтверждается только прямыми словами («студент старших курсов», «старшекурсник»). Номер курса без этих слов даёт `unknown` с вопросом об образовании: по acceptance профилей число курса само по себе не задаёт границу. Найдено на демо-наборе (py-9105, «3 курс»): модель засчитывала такой курс как старший. Предыдущие оценки становятся устаревшими из-за смены версии.
