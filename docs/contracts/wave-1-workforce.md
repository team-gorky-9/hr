# Workforce · контракт первой волны 1.0

Спецификация к реализации Давидом. Обязателен [общий контракт](wave-1-common.md). Владелец — сервис workforce. Существующие users и Candidate в legacy-hr сохраняют прежний смысл. Уточнение от 21 ноября по вопросам исполнителя — файловый API реализуют Hiring и Requirements; Workforce сохраняет ссылки и реквизиты оснований.

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
| POST /intakes/{id}/resolve-correction | {expected_revision,expected_assignment_revision,action:"apply_correction"|"keep_existing",reason} → {intake,assignment,resolution} | hr/admin своей организации, needs_review с ранее зарегистрированным assignment_id; обработка по правилам ниже |

Для вызова /intakes/register после ручной проверки HR не нужен ответ соседнего сервиса. Повтор одного source_case_id с той же версией не создаёт нового intake. Новая версия готовности после registered даёт needs_review с сохранением прежнего назначения и запретом автоматической отмены. Отказ intake отражается при интеграции как ручной вопрос ответственному hiring, сценарий автоматического отзыва оформления вынесен в последующую версию.

## Завершение повторной проверки

Если assignment_id уже существует, /register и /reject дают 409 CORRECTION_REVIEW_REQUIRED. Новая передача того же source_case_id меняет предложенные сведения intake и его revision, сохраняя employee_id/assignment_id и ранее принятое основание. История хранит received event_id, case revision, correlation_id, предлагаемые значения и прежние решения. Пришедшая до первой регистрации поправка просто уточняет ещё незарегистрированный intake, который затем проходит обычный /register.

HR открывает сравнение сохранённого назначения и последней передачи. /resolve-correction проверяет обе ревизии; устаревшая форма даёт 409 STALE_REVISION. Повтор команды проверяется раньше ревизий по common. Два варианта:

- apply_correction обновляет starts_on и реквизиты basis **у прежнего assignment_id**, увеличивает revision назначения, сохраняет предыдущие значения, источник и причину. Выполняются обычные проверки периода. ФИО, person_ref, department_id и position_code таким исправлением не меняются. Если эти ссылки отличаются от принятой передачи, вернуть 409 MANUAL_PERSONNEL_CHANGE_REQUIRED и оставить needs_review.
- keep_existing сохраняет прежние поля и revision назначения. HR обязан объяснить, почему предложенную поправку не применяет. Например, исходное кадровое основание подтверждает прежнюю дату. Проверка версии назначения всё равно обязательна.

В обоих случаях intake возвращается в registered, увеличивает собственную revision и сохраняет последнее решение по source_event_id/source_case_revision. В той же транзакции создаётся assignment.review-resolved с resolution=corrected либо kept_existing и фактическими значениями назначения. Для kept_existing aggregate_revision сообщения остаётся текущей revision назначения; дедупликация выполняется по event_id, а разрешение сверки — по source_event_id/case_revision. Это новый результат проверки, а не попытка обновить назначение той же ревизией.

Новое назначение создаётся при реальном переводе/новом кадровом основании отдельной командой по своему сценарию. Исправленная дата начала существующего оформления не порождает второго сотрудника или назначения. Если HR сперва выполняет отдельное кадровое исправление, перед resolve-correction он перечитывает назначение и принимает решение по актуальной версии.

Если во время просмотра пришла следующая поправка, предыдущая форма не завершает новую проверку. Запоздалое исходное employment.ready не возвращает intake к старым данным. Ошибка публикации результата оставляет его в outbox, повтор доставки не повторяет коррекцию.

## Замещение

POST /delegations {manager_employee_id,substitute_employee_id,department_id,starts_on,ends_on,basis} → 201 Delegation с этими полями и id/revision. Все стороны одной организации, даты ограничивают действие. GET /delegations?department_id=…&as_of=YYYY-MM-DD возвращает действующие записи. POST /delegations/{id}/end {expected_revision,ends_on,reason} прекращает период. Сервис сообщает назначение заместителя, соседний процесс отдельно решает о переназначении старого открытого дела.

## Учебный вход

GET /actors?role=… и GET /actors/{id} возвращают actor без токенов/пароля для hr/admin своей организации. Этот read-интерфейс позволяет назначить согласующего. При автономном fixture-режиме requirements использует тот же набор actors.json. Деактивированный актор не возвращается как пригодный для нового назначения.

Сессии по common. Акторы из actors.json фиксируют права, кадровый Employee может связываться с ними через account_actor_id. Отдельная админка ролей не входит в волну. Для запрета доступа нужны два hr из разных организаций и два однофамильца в кадровом наборе. При AUTH_MODE=fixture данные и поведение предметных операций те же, что после настоящего входа.

## Критерии на общем примере

Один employment.ready создаёт один intake. HR проверяет запись кандидата, регистрирует employee/assignment с основанием. RabbitMQ получает один логический assignment.registered, повтор доставки допускается и не дублирует кадровые факты. Два параллельных подтверждения одной ревизии дают один результат и контролируемый конфликт/повтор. Перевод сохраняет прежний период. Неверная организация отклоняется. Перезапуск сохраняет БД, сессии до срока и outbox.
