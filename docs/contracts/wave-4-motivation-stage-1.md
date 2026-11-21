# Волна 4 · мотивация и участие · этап 1

Четыре последовательных небольших результата Давида. Реализация в отдельном модуле/пакете recognition текущего окружения, например services/recognition, префикс /api/v1/recognition. Контейнеры, брокер, отдельная модель и общий сервис уведомлений для сдачи не требуются.

## Основа и доступ

Actor имеет organization_id и подтверждённые учебные роли. employee участвует от своего имени. hr назначается организатором/модератором по конкретной области, department может быть назначенным рассматривающим. Назначения хранятся явно, административное назначение не даёт права читать личные записи всех модулей.

Ресурсы имеют UUID, revision, даты и автора. Изменение требует expected_revision, ошибки 409 STALE_REVISION/INVALID_STATE, 422 для неверных данных, 404 для чужого скрытого объекта. Используются локальные fixture-акторы или уже доступный вход. Полный общий движок повтора и распределённые сообщения отложены.

При создании клиент задаёт содержательные поля объекта; id, organization_id, автора, revision и начальный status выставляет сервер по разрешённому контексту. Действия open/publish/withdraw, где тело не расписано отдельно, принимают expected_revision и при снятии/отмене reason. Списки имеют limit/cursor и только разрешённые поля. История хранит автора и прежнюю редакцию.

## 4A · благодарность и её видимость

Thanks = {id,organization_id,author_id,recipient_id,text,revision,requested_visibility:private|organization,recipient_choice:pending|private|organization|declined,moderation_status:pending|approved|returned,moderation_reason:null|string,status:pending|private|published|withdrawn}. Текст и причины имеют версионную историю.

| Операция | Результат |
|---|---|
| POST /thanks {recipient_id,text,requested_visibility} | employee создаёт запись адресату своей области |
| GET /thanks/{id} | Автор/адресат читают свою запись. Модератор читает только направленную на публикацию. Остальные — только published |
| GET /thanks?view=mine|received|wall | Отправленные, полученные либо разрешённая общая стена |
| POST /thanks/{id}/visibility {expected_revision,choice:private|organization|declined} | Только адресат выбирает видимость своей версии |
| POST /thanks/{id}/moderation {expected_revision,result:approved|returned,reason} | Назначенный модератор, причина возврата обязательна |
| PATCH /thanks/{id} {expected_revision,text} | Автор изменяет текст; согласие на прежнюю версию перестаёт давать публикацию, новая версия снова pending |
| POST /thanks/{id}/withdraw {expected_revision,reason} | Автор либо адресат снимает показ; история остаётся у допустимых участников |

Общая публикация появляется только при выборе organization адресатом и одобрении текущей версии модератором. Private доступна автору/адресату без прохождения публичной модерации. Declined не показывается на стене. Самоблагодарность запрещена. Подсчёт баллов или рейтинг сотрудников не создаётся.

Модератор не одобряет запись, в которой он автор или адресат. Для учебного случая используется второй назначенный модератор либо состояние ожидания другого рассматривающего. Личные записи, не направленные на публикацию, не включаются в его очередь.

Демо — отправить благодарность, адресат разрешает публикацию, модератор возвращает текст, автор исправляет, адресат снова подтверждает и модератор одобряет. На стене видна только новая согласованная версия.

## 4B · кампания и номинация

Campaign = {id,organization_id,title,criteria,starts_on,ends_on,reviewer_actor_id,status:draft|open|closed,revision}. Nomination = {id,campaign_id,author_id,nominee_id,statement,revision,status:awaiting_consent|submitted|declined|selected|not_selected,decision_reason:null|string,publication_choice:pending|allowed|denied}. Реквизиты рабочего результата могут быть обычной разрешённой ссылкой, она не открывает закрытые материалы соседнего процесса.

| Операция | Результат |
|---|---|
| POST /campaigns и POST /campaigns/{id}/open | Организатор готовит критерии/период и открывает кампанию |
| GET /campaigns и GET /campaigns/{id} | Разрешённая аудитория читает открытые условия |
| POST /campaigns/{id}/nominations {nominee_id,statement} | employee предлагает коллегу, в пределах дат |
| POST /nominations/{id}/consent {expected_revision,accepted:boolean} | Кандидат принимает участие либо отклоняет |
| GET /nominations/{id} | Автор, кандидат и назначенный рассматривающий по делу |
| POST /nominations/{id}/decision {expected_revision,result:selected|not_selected,reason} | Рассматривающий после согласия, с объяснением |
| POST /nominations/{id}/publication {expected_revision,allowed:boolean} | Выбранный кандидат разрешает либо запрещает показ |
| GET /campaigns/{id}/results | Только selected с allowed, без имён отказавшихся/неотобранных |

Рассматривающий не принимает решение по собственной номинации или номинации, которую сам подал; организатор назначает замену через PATCH campaign с revision и причиной. После начала рассмотрения критерии не переписываются. Формальное кадровое поощрение не создаётся автоматически.

Демо — номинация, согласие, решение, разрешённый итог. Отказ от участия не появляется в публичных результатах. Собственная номинация рассматривающего требует замены.

## 4C · семейное событие, места и очередь

Event = {id,organization_id,title,description,starts_at,ends_at,location,capacity:int>=1,status:draft|open|cancelled|completed,revision,organizer_id}. Registration = {id,event_id,actor_id,participants_count:int>=1,child_age_bands:[],status:confirmed|waiting|awaiting_reconfirmation|cancelled,agreed_event_revision,revision}. Минимальные сведения семьи определяются нужными категориями, имена родственников в учебном сценарии не требуются.

| Операция | Результат |
|---|---|
| POST /events и POST /events/{id}/open | Организатор публикует условия и вместимость |
| GET /events и GET /events/{id} | Доступные объявления и доступные места |
| POST /events/{id}/registrations {participants_count,child_age_bands} | employee записывает свою группу. Достаточно мест → confirmed, иначе waiting |
| GET /events/{id}/registrations | Организатор читает организационный список; обычный участник только собственную запись |
| POST /registrations/{id}/cancel {expected_revision} | Свой участник освобождает место |
| POST /registrations/{id}/offer {expected_revision} | Организатор предлагает освободившееся место ожидающей группе с проверкой вместимости, статус awaiting_reconfirmation |
| PATCH /events/{id} {expected_revision,starts_at?,ends_at?,location?,reason} | Организатор меняет существенные условия, подтверждённые участники ожидают повторного ответа |
| POST /registrations/{id}/reconfirm {expected_revision,accepted:boolean} | Участник принимает текущую версию либо освобождает место |
| POST /events/{id}/finish {expected_revision,outcome:completed|cancelled,reason} | Организатор фиксирует реальный исход |

Вместимость проверяется атомарно для всей группы. Одно действующее участие на event+actor. Последние места не выдаются двум группам. При переносе места прежних подтверждённых групп остаются занятыми до ответа/отмены организатором с причиной; статус ожидания виден. Предложение группе из очереди также временно занимает места до её ответа. В первом функциональном пути очередь ведёт организатор вручную; автоматические таймеры и рассылка — этап 2.

Демо — событие на три места, семья из трёх подтверждена, следующая заявка в очереди; отмена первой, предложение второй и подтверждение. Перенос даты требует нового ответа. Факт присутствия и публикация фотографий не выводятся из регистрации.

## 4D · закрытая сессия и материалы

Использовать механику Event с type=general|confidential_session. Для confidential_session participants_count=1, семейные поля не применяются. Доступ к списку записавшихся имеют только назначенный организатор и ведущий данной сессии. Руководителю подразделения это право не предоставляется. Витрина показывает тему/условия/места без списка участников.

Material = {id,title,description,url,version,audience_scope,status:draft|published|withdrawn,author_actor_id,revision}. Организатор или уполномоченный публикующий создаёт материал, проверяет право распространения и указывает основание. POST /materials, POST /materials/{id}/publish, POST /materials/{id}/withdraw и GET /materials/{id}, GET /materials образуют путь доступного курса. Названия и ссылки — учебные либо разрешённые источники. Изменение содержания получает новую версию.

Содержание консультации, профессиональные записи психолога и диагностика не собираются в этом функциональном пути. Материал можно открыть независимо от сессии. Просмотр курса не создаёт оценку компетентности.

Демо — employee записывается на сессию, другой руководитель не видит его запись; материал опубликован и затем отозван с объяснением. Список личных посещений не уходит в кадровую аналитику.
