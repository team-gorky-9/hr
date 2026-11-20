# Полный прогон PostgreSQL + pgvector — 20.11.2026

Проверен коммит **6c5f9baec31e7eae1284ec0848602e8d881cd66f**, ветка `feature/profile-assessment-integration`. При проверке продуктовый код, тесты и `tests/conftest.py` не менялись.

**Результат: 570 passed, 3 subtests passed, 0 skipped, 0 failed, 0 errors.** Полный штатный pytest завершился за 16.12 с, exit 0. JUnit содержит 573 проверки с учётом трёх подслучаев. Все 208 ранее пропущенных проверок БД выполнены.

Среда: Windows x64, PostgreSQL **16.15**, pgvector **0.8.6**. Отдельный кластер с новой тестовой БД, слушал только `127.0.0.1:55440`; после проверки сервер остановлен. Векторное расширение установлено настоящей миграцией, таблица embeddings не исключалась. Дополнительно проверено расстояние между `[1,2,3]` и `[1,2,4]`: результат `1.0`.

## Миграции

На второй новой базе выполнены все команды, каждая с exit 0:

```text
alembic upgrade head        # 0001 → 0002 → 0003 → 0004 → 0005
alembic check               # No new upgrade operations detected.
alembic downgrade base     # 0005 → ... → 0001 → base
alembic upgrade head        # повторная установка всей цепочки
alembic check               # No new upgrade operations detected.
```

Штатные тесты отдельно проверили наличие всех ORM-таблиц, расширения vector и соответствие моделей миграциям. Итоговая ревизия — **0005**.

## Воспроизведение

Нужна отдельная пустая база PostgreSQL с доступным pgvector. Тесты удаляют её схему; имя базы обязано оканчиваться на `_test`. Из корня продукта:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://<user>:<password>@127.0.0.1:<port>/<database>_test'
uv run pytest -q -ra
```

В этом прогоне `.env` не менялась: тестовый URL передан только процессу. Служебный скрипт создания нового кластера и журнал подготовки сохранены в штабе: `hq/work/2026-11-20-profile-assessment-integration/run_full_pgvector.py` и `pgvector-run.md`. [Машинный отчёт с версиями и SHA-256 пакетов](pgvector-full-2026-11-20.json).

## Границы проверки

Это полный прогон БД с pgvector, включая миграции, но на **PostgreSQL 16 под Windows**. Проектный `docker-compose.yml` использует PostgreSQL 17; запуск этого Docker-окружения здесь не проверен. Нового живого вызова YandexGPT для данного прогона не было; предыдущие 41/41 сохранены в отдельном отчёте. Рабочие базы и профили не менялись, публикация не выполнялась.

Для среды использованы пакеты [conda-forge PostgreSQL](https://anaconda.org/channels/conda-forge/packages/postgresql) и [pgvector](https://anaconda.org/conda-forge/pgvector), установленные переносимым micromamba во временную папку; системная PostgreSQL 18 не изменялась.
