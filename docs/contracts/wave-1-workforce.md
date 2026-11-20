# Workforce · контракт первой волны 1.1

Спецификация к реализации Давидом. Обязателен [общий контракт](wave-1-common.md). Владелец — сервис workforce. Существующие users и Candidate в legacy-hr сохраняют прежний смысл.

Уточнение 21 ноября 2026 по ответу Давида в задаче Workforce: сервис не загружает и не хранит файлы, только ссылки и реквизиты оснований. Файловый API принадлежит Hiring и Requirements. Исправление оформления проверяется по прежнему назначению: применить дату/основание либо сохранить прежние значения с объяснением. Оба исхода завершают проверку и передаются Hiring. HTTP и новое событие ниже конкретизируют это решение; настоящая интеграция с обработчиком Hiring проверяется отдельно.

## Ресурсы и полномочия

| Объект | Поля сверх общих id/revision/timestamps | Кто меняет |
|---|---|---|
| Department | organization_id, code, name, parent_id UUID/null | admin своей организации; parent обязан принадлежать той же организации, циклы запрещены |
| Employee | organization_id, display_name, source_refs [{system,id}], account_actor_id UUID/null | hr/admin своей организации; связь с actor только после явного подтверждения |
| Assignment | employee_id, department_id, position_code, starts_on, ends_on date/null, manager_employee_id UUID/null, basis {reference,issued_on}, recorded_by | hr/admin; сотрудник и руководитель из той же организации, ends_on не раньше starts_on |
| Intake | source_case_id, person_ref, proposed_assignment, status received/needs_review/registered/rejected, issue string/null, employee_id/assignment_id UUID/null | создаётся потребителем, разбирается hr/admin |

Employee не содержит единственного current_department. Одновременные назначения могут существовать, источник и период сохраняются. В первой волне запись сотрудника и назначения вводятся вручную или через intake, универсальный CSV-импорт — дальнейшая поставка. Связь source_refs уникальна по organization/system/id, ФИО не уникально.

## Операции

Все даты, ключи повторов, expected_revision, ошибки и пагинация по common.

| Метод и путь | Тело / результат | Правило |
|---|---|---|
| POST /departments | {code,name,parent_id?} → 201 Department | organization берётся из области актора; code уникален в организации |
| GET /departments | → список Department | Разрешённая организация |
| PATCH /departments/{id} | {expected_revision,name?,parent_id?} → Department | История старого названия/иерархии сохраняется |
| POST /employees | {display_name,source_refs,account_actor_id?,confirmation_basis} → 201 Employee | Пустое основание/ссылка на чужой actor → ошибка |
| GET /employees | ?query=имя/code → список | Только hr/admin; поиск имени может вернуть нескольких |
| GET /employees/{id} | → Employee и assignments | hr/admin своей организации, сотрудник — только явно связанный self без лишних чужих полей |
| PATCH /employees/{id} | {expected_revision,display_name?,account_actor_id?,correction_basis} → Employee | Причина обязательна, подтверждённые источники не переписываются молча |
| POST /employees/{id}/assignments | {department_id,position_code,starts_on,ends_on?,manager_employee_id?,basis} → 201 Assignment | Нельзя дублировать одно назначение по тому же основанию; проверять свои ссылки |
| POST /assignments/{id}/end | {expected_revision,ends_on,reason} → Assignment | История, запрет пустой причины; будущая дата означает план окончания |
| POST /assignments/{id}/transfer | {expected_revision,ends_on,new_department_id,new_position_code,starts_on,manager_employee_id?,basis} → {ended,new} | Атомарно закрыть старое и создать новое; одно действие на повтор |
| POST /assignments/{id}/correct | {expected_revision,starts_on?,ends_on?,manager_employee_id?,reason,basis} → Assignment | Исправление с историей дат, действующих и зарегистрированных сведений |
| GET /employees/{id}/history | → события с автором, старой/новой версией и основанием | Разрешённые кадровые акторы |
| GET /intakes | ?status=received/needs_review/registered/rejected → список | hr/admin своей организации |
| GET /intakes/{id} | → Intake | Конфликты и совпадения видны как вопросы, автоматической склейки по ФИО нет |
| POST /intakes/{id}/register | {expected_revision,employee_id:UUID/null,create_employee:{display_name}:object/null,identity_basis} → {intake,employee,assignment} | Ровно один вариант существующего/нового сотрудника, основание обязательно. Даты/должность берутся из proposed_assignment. Транзакция создаёт assignment.registered в outbox |
| POST /intakes/{id}/reject | {expected_revision,reason} → Intake | received/needs_review → rejected; автоматического изменения дела hiring нет |

Для вызова /intakes/register после ручной проверки HR не нужен ответ соседнего сервиса. Повтор одного source_case_id с той же версией не создаёт нового intake. Новая версия готовности после registered даёт needs_review с сохранением прежнего назначения и запретом автоматической отмены. Отказ intake отражается при интеграции как ручной вопрос ответственному hiring, сценарий автоматического отзыва оформления вынесен в последующую версию.

## Повторная проверка зарегистрированного назначения

`POST /intakes/{id}/review` принимает `{expected_revision,expected_assignment_revision,decision:"apply"|"keep",reason?:string}` и возвращает `{intake,assignment,review}`. Доступ — hr/admin своей организации. Нужны `needs_review` и прежний `assignment_id`. `reason` обязателен и непуст для `keep`; у `apply` объяснение дополнительно к входному основанию необязательно. Проверяются обе ревизии; повтор ключа возвращает прежний результат прежде проверки ревизий.

- `apply` переносит `starts_on` и реквизиты `basis` из последней принятой версии `employment.ready` в **существующее** назначение, увеличивает его revision, сохраняет прежние дату/основание в истории. ID, сотрудник, подразделение, должность, руководитель и окончание периода не меняются. Несовместимая дата даёт 422. Смена человека/подразделения/должности не трактуется как исправление и даёт 409 INVALID_STATE: нужен отдельный кадровый процесс.
- `keep` сохраняет назначение, его ID, значения и revision, записывает объяснение и сравниваемую версию в историю.

В обоих случаях Intake возвращается в `registered`, увеличивает revision и хранит `last_review={decision,reason,reviewed_by_actor_id,reviewed_at,source_case_revision,source_event_id,assignment_revision}`. `reason` может быть null только у apply. Новая готовность позже снова даёт needs_review; last_review остаётся явно привязан к предыдущей версии. Изменение назначения (если apply), история, завершение проверки и outbox `assignment.reviewed` сохраняются одной транзакцией. Для перевода остаётся `/assignments/{id}/transfer`, новая запись при исправлении даты не создаётся.

## Замещение

POST /delegations {manager_employee_id,substitute_employee_id,department_id,starts_on,ends_on,basis} → 201 Delegation с этими полями и id/revision. Все стороны одной организации, даты ограничивают действие. GET /delegations?department_id=…&as_of=YYYY-MM-DD возвращает действующие записи. POST /delegations/{id}/end {expected_revision,ends_on,reason} прекращает период. Сервис сообщает назначение заместителя, соседний процесс отдельно решает о переназначении старого открытого дела.

## Учебный вход

GET /actors?role=… и GET /actors/{id} возвращают actor без токенов/пароля для hr/admin своей организации. Этот read-интерфейс позволяет назначить согласующего. При автономном fixture-режиме requirements использует тот же набор actors.json. Деактивированный актор не возвращается как пригодный для нового назначения.

Сессии по common. Акторы из actors.json фиксируют права, кадровый Employee может связываться с ними через account_actor_id. Отдельная админка ролей не входит в волну. Для запрета доступа нужны два hr из разных организаций и два однофамильца в кадровом наборе. При AUTH_MODE=fixture данные и поведение предметных операций те же, что после настоящего входа.

## Критерии на общем примере

Один employment.ready создаёт один intake. HR проверяет запись кандидата, регистрирует employee/assignment с основанием. RabbitMQ получает один логический assignment.registered, повтор доставки допускается и не дублирует кадровые факты. Два параллельных подтверждения одной ревизии дают один результат и контролируемый конфликт/повтор. Перевод сохраняет прежний период. Неверная организация отклоняется. Перезапуск сохраняет БД, сессии до срока и outbox.
