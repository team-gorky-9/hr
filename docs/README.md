# Документация платформы «Кадровый ассистент»

Навигация по материалам репозитория в зависимости от того, что именно вы проверяете.

## Быстрый выбор документа

| Кто вы / что проверяете | С чего начать |
|---|---|
| Руководитель, кадровик, отраслевой департамент — хочу быстро потыкать сайт и понять ценность | **[Путеводитель по возможностям (`PRODUCT-GUIDE.md`)](PRODUCT-GUIDE.md)** — 4 маршрута по ролям на `https://gorky.bond`, таблица покрытия 11 проблем кейса и карта достоверности данных |
| IT-архитектор, аналитик, инженер эксплуатации — хочу понять устройство и научную часть | **[Научно-инженерная статья (`paper/kadry-paper.pdf`)](paper/kadry-paper.pdf)** + **[Общая архитектура (`ARCHITECTURE.md`)](ARCHITECTURE.md)** |
| Проверяющий качество моделей, тестов и замеров | **[Сводный реестр проверок (`EVALUATION.md`)](EVALUATION.md)** — все прогоны, JSON-протоколы, границы применимости и команды воспроизведения |
| Разработчик — хочу поднять локально или подключиться к API | **[Корневой `README.md`](../README.md)** · **[Карта сервисов и деплой](modules/deployment.md)** · **[Контракты API](contracts/README.md)** |

---

## Разделы папки `docs/`

- **[`paper/`](paper/README.md)** — исходник LaTeX (`kadry-paper.tex`), готовый PDF (`kadry-paper.pdf`) и скрипт `build_figures.py`, генерирующий графики строго из JSON-отчётов репозитория.
- **[`PRODUCT-GUIDE.md`](PRODUCT-GUIDE.md)** — нетехнический путеводитель по 4 ролям на стенде (`Портал соискателя`, `Сотрудник по подбору персонала`, `ОПК`, `Сотрудник`), покрытие 11 проблем кейса и юридические гарантии (25-ФЗ, 99-З, 152-ФЗ).
- **[`ARCHITECTURE.md`](ARCHITECTURE.md)** — единый обзор фактически реализованной архитектуры 9 сервисов, БД, пайплайнов, безопасности и CI/CD.
- **[`EVALUATION.md`](EVALUATION.md)** — сводка всех зафиксированных проверок (`pytest`, YandexGPT, поиск BM25/E5, реальный архив 1 739 файлов / 287 DOCX, единое окно, волны 1–6).
- **[`contracts/`](contracts/README.md)** — формальные HTTP- и data-контракты модулей (`api.md`, `assessment.md`, `database.md`, `import.md`, `interview.md`, `search.md`, `workflow.md`, `reporting.md`, `interaction-window.md`, контракты волн 1–5).
- **[`modules/`](modules/)** — подробные инструкции по каждому модулю и сервису (`ingest.md`, `assessment.md`, `interview.md`, `search.md`, `reporting.md`, `management.md`, `deployment.md`, `workforce-service.md`, `hiring-service.md`, `requirements-service.md`, `students-service.md`, `social-support.md`, `employee-feedback.md`, `mobility-service.md`, `recognition.md`, `interaction-window.md` и замер `search-evaluation-v1.json`).
- **[`reports/`](reports/)** — первичные протоколы проверок, JSON-выгрузки замеров, OpenAPI-снимки и примеры Excel-книг.
- **[`demo/wave-6-runtime.md`](demo/wave-6-runtime.md)** — подробная карта локального запуска отдельных сервисов и учебных ролей.
