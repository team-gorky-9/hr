# Модуль оценки

Контракт: [assessment v0.3](../contracts/assessment.md). Интеграция `feature/profile-assessment-integration`: main fc61d26 + профили 905ea9b + ai-01 c94285e. [Проверки и ограничения](../reports/profile-assessment-integration.md).

## Путь данных

1. CLI выбирает профиль через get_approved_profile с явным контуром; draft для учебного кандидата задаётся по ID. Для основного отбора передаётся ID отклика; сравнение включается явно через purpose=comparison.
2. `orchestration.assess_in_context` проверяет кандидата, профиль, все params, as_of и отклик до модели. Для hr-consultant resolver проверяет posting_title. Если соответствие не установлено или должность другая, primary пишет skipped без оценки кандидата.
3. `service.assess_candidate` получает текущий очищенный текст. Подходящая карточка переиспользуется; иначе извлекается CandidateCard. В модель не передаются raw_text и candidate_pii.
4. Формальная модель получает критерии acceptance, альтернативы и описание релевантности. Компетентностная — только screening-индикаторы с acceptance. Код находит позиции цитат, считает включительные месяцы и границы [L,U], объединяет альтернативы. Вывод без цитаты понижается; необходимость документа оставляет met предварительным.
5. `counters` сводит same_as: одна единица в компетенции, обязательность OR, конфликт подтверждения и противоречия требует ручной сверки. Интервью-группы и исключённые строки считаются отдельно. Численный уровень и общий процент не придумываются.
6. Repository проверяет все вложенные цитаты и результаты, сохраняет formal_checks.alternatives и competency_scores.details, algorithm_version и calculation_as_of. Контекст запуска записывается отдельно в audit_log. API заново применяет политику к отклику и не выдаёт сравнение за основной отбор.

## Компоненты

`llm_schemas.AlternativeItem` нормализует только явное `status="unknown"` от провайдера в каноническое `no_info`. Это устранение смешения словарей извлечения и итоговой оценки, а не признание неизвестного ответа валидным. Ключи/цитаты не переписываются, другие недопустимые статусы отклоняются. Изменение отмечено версией алгоритма assessment-2.0.1; прежние оценки становятся stale по существующему правилу версии. [Регрессия и живые повторы](../reports/formal-extraction-unknown-status.md).

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
    --approver hr-demo --basis "учебный профиль для qa-01" --commit                  # 5. утверждение кадровиком
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
