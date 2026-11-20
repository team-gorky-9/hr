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
