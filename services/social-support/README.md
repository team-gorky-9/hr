# Социальная помощь · учебный этап 1

Самостоятельный FastAPI пакет, контракт: ../../docs/contracts/wave-5-support-stage-1.md.
SQLite и неизменяемые локальные оригиналы. Никаких реальных правил или личных данных
в fixture: support-training-v1 — синтетическое основание с двумя приложениями.

## Запуск (PowerShell из services/social-support)

```powershell
uv sync --python 3.13 --dev
uv run uvicorn support.main:app --host 127.0.0.1 --port 8106
```

База создаётся при первом запуске (schema version 1), рестарт её не очищает.
SUPPORT_DATA_DIR задаёт каталог БД/оригиналов, по умолчанию data/.
SUPPORT_ACTORS_PATH — учебные акторы, по умолчанию fixtures/actors.json.
Вход исключительно учебный: Bearer fixture:employee (также employee2, specialist,
secretary, secretary2, coordinator, executor, manager, other_org). Нельзя применять
эту авторизацию для рабочих личных данных. Сервис слушает loopback в команде выше.

Swagger: http://127.0.0.1:8106/docs; OpenAPI: /openapi.json.
Все изменения существующего дела требуют expected_revision. При загрузке его
передают multipart-полем. Чужой объект — 404, конфликт состояния/редакции — 409,
неверные данные — 422. Повтор подачи не создаёт второе дело: возвращает конфликт,
после которого GET показывает сохранённый номер и снимок.

## 5A: короткий HTTP-путь

GET /api/v1/support/rules от employee → POST /cases с rule_version_id,statement →
POST /cases/{id}/documents (multipart: file,item_key,expected_revision; для двух
пунктов application/evidence) → GET /cases/{id} → POST /cases/{id}/submit.
Координатор через GET /cases читает минимальную очередь, затем POST /cases/{id}/assign
с expected_revision,specialist_actor_id,secretary_actor_id,assignment_basis.
UUID акторов доступны в fixture. Личные черновики координатору не видны.
Назначенный специалист читает GET /cases/{id}; employee2 получает 404.

Оригиналы скачиваются GET /cases/{id}/documents/{document_id}/content.
Заявитель загружает applicant-файлы, назначенный специалист/секретарь — internal
с item_key=internal. Клиентское имя не становится путём. Лимит 10 MiB; пустой файл
не принимается. Байты записываются и fsync выполняется до фиксации метаданных.
Ошибка транзакции удаляет новый файл; при аварийном завершении между записью и
commit возможен непривязанный файл, но ложного принятия в БД нет.

```powershell
uv run pytest tests/test_5a.py -q
```

Тест поднимает настоящий uvicorn на временном порту, использует отдельную SQLite,
проверяет две загрузки, подачу, назначения, чужой доступ и чтение после рестарта.
SUPPORT_REPORT_DIR позволяет сохранить OpenAPI и синтетические ответы для фронтенда.
PostgreSQL, UI, внешние системы и полный набор продукта не входят в проверку этапа.

## 5B: комплектность

Назначенный специалист POST /cases/{id}/staff-confirmation фиксирует confirmed/unknown
и source_reference кадрового источника; роль employee не подтверждает занятость.
POST /cases/{id}/completeness принимает expected_revision, items по всем пунктам,
public_message. У present/unreadable/needs_clarification документ обязан входить в
текущую подачу и относиться к этому пункту. missing не ссылается на файл; замечанию
нужна причина. Полный комплект без confirmed остаётся submitted.

После needs_information заявитель загружает замену и явно делает POST /addenda
с expected_revision,text,document_ids. Это новый снимок подачи; одна версия на пункт,
история не перезаписывается. Проверяющий читает его перед новой completeness.
GET /history отделяет публичные объяснения от служебных деталей.
Проверка: uv run pytest tests/test_5b.py -q.
