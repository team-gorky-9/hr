# Социальная помощь · учебный этап 1

Цельный показ волны 6: `uv run pytest tests/test_wave6_demo.py -q -s`.
[Подача → дополнение → личный результат, фактические ответы и граница UI](../../docs/reports/wave-6-support-demo.md).
Сценарий проверяет одно дело через настоящий HTTP, сохранность после перезапуска
и чужой доступ. Внешние решение и исполнение регистрируются вручную на учебных источниках.

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

## 5C: внешнее решение и личная выписка

Назначенный секретарь POST /cases/{id}/decision регистрирует outcome,
public_explanation,source_reference,source_author,decided_on,recording_basis
и expected_revision. Это внешний человеческий итог, не цифровое голосование.
Самому себе секретарь решение не регистрирует; координатор назначает другого.
GET /cases/{id}/extract выдаёт id,case_id,version,outcome,public_explanation,decided_on.
Внутренние source_reference/recording_basis и общий протокол в выписку не входят.
POST /decision-corrections требует те же поля и correction_reason, создаёт новую
запись. Старое решение сохранено. needs_information возвращает дело к комплектности.
Проверка: uv run pytest tests/test_5c.py -q.

## 5D: исполнение, закрытие, отзыв

Координатор POST /cases/{id}/executor-assignment с expected_revision,
executor_actor_id,assignment_basis назначает отдельного регистратора исполнения.
Исполнитель читает только минимальную карточку, личный итог и события исполнения;
комплект и заявление ему не открываются. POST /execution принимает status
unknown/failed/confirmed,source_reference,source_author,occurred_on,note и
expected_revision. Разрешён только после approved; это запись внешнего факта,
не автоматический платёж. История хранит все версии и ID решения.

Заявитель видит status и дату исполнения без внутренних реквизитов и заметки.
POST /close выполняет специалист с expected_revision,reason. Явное основание
организационного закрытия обязательно; unknown остаётся unknown. POST /withdraw
доступен заявителю до окончательного решения; файл и история не удаляются.
Отозванный личный черновик не появляется в очереди координатора.
Исправление решения сбрасывает текущий статус исполнения в unknown, сохраняя
старое свидетельство в истории: оно не подтверждает новую редакцию решения.

uv run pytest tests/test_5d.py -q — путь 5D.
uv run pytest tests/test_5a.py tests/test_5b.py tests/test_5c.py tests/test_5d.py -q —
короткая проверка четырёх частей (4 теста). Финальный OpenAPI и ответы находятся в
../../docs/reports/wave-5d-support-openapi.json и wave-5d-support-examples.json.

Части сохранены отдельными зависимыми ветками 5A → 5B → 5C → 5D. При интеграции
после предыдущей части следующую нужно перенести на актуальный main. Рабочие правила,
настоящая идентификация, сроки хранения, аварийное восстановление и интеграция
с кадровым/платёжным источником остаются архитектурным продолжением этапа 2.
