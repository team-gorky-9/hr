# Волна 3 · практика · этап 1

Три последовательных самостоятельных задачи Дениса. Для начала достаточно учебных участников, мест и ручных подтверждений. Готовность развития, мобильности и архива не требуется.

Реализация — изолированный students-пакет, например services/students, с собственными HTTP-операциями и постоянными данными, /api/v1/students. Отдельная контейнерная инфраструктура не является условием. Стек текущего продукта, внутреннее разбиение выбирает исполнитель. Дальнейшее размещение в карьерном сервисе определяется этапом 2.

## Участники и общие правила

Использовать локальный повторяемый набор акторов в формате wave-1 actors: hr как организатор, candidate как студент, department/employee как назначенный наставник. Предметные назначения «студент заявки»/«наставник участия» задаются объектом, а не расширяют права глобальной роли. Учебный fixture-вход явно помечен. Для демонстрации добавить вторую candidate-учётку своей области для проверки чужой заявки. Действующий Workforce необязателен.

У ресурсов UUID, organization_id, revision, авторы и даты. Изменение принимает expected_revision; чужая запись — 404, неверное состояние — 409, неправильные данные — 422. ФИО не используется для автоматической склейки. Персональные данные ограничены нужными для учебной заявки.

## 3A · место, заявка и ручное назначение

Opportunity = {id,title,description,starts_on,ends_on,capacity:int>=1,mentor_actor_id,revision,status:draft|published|closed}. Даты согласованы; наставник принадлежит области организатора. Application = {id,opportunity_id,student_actor_id,university_label,programme_label,comment,revision,status:submitted|withdrawn|assigned|not_assigned,reason:null|string}. Placement = {id,application_id,opportunity_id,student_actor_id,mentor_actor_id,starts_on,ends_on,revision,status:active|completed|stopped,organization_id}.

| Операция | Результат |
|---|---|
| POST /opportunities | HR создаёт draft из title,description,starts_on,ends_on,capacity,mentor_actor_id |
| POST /opportunities/{id}/publish | HR, {expected_revision} → published |
| GET /opportunities | Студент видит published с доступными местами; HR — свои состояния |
| POST /applications | Студент подаёт {opportunity_id,university_label,programme_label,comment}; одна открытая заявка на пару студент/возможность |
| GET /applications и GET /applications/{id} | HR своей области и собственный студент |
| POST /applications/{id}/withdraw | Собственный студент, {expected_revision,reason}, до назначения |
| POST /applications/{id}/assign | HR, {expected_revision,confirmation_basis} → Placement, application assigned |
| POST /applications/{id}/decline | HR, {expected_revision,reason} → not_assigned |
| GET /placements и GET /placements/{id} | Организатор, собственный студент и назначенный наставник |

Место расходуется только при назначении. Проверка остатка и запись назначения выполняются атомарно; последнее место не может быть выдано двум людям. Основание подтверждения отражает ручную сверку учебных условий/наставника, а не цифровую подпись вуза. При нехватке места исход понятен, заявка не исчезает. Повтор assign возвращает то же Placement, а не второй расход места.

Политика совместной нагрузки наставника в первом примере — один действующий студент на пересекающийся период для одного mentor_actor_id. Это явно учебное ограничение, вынесенное в конфигурацию примера. Если назначений уже больше допустимого, новая команда даёт MENTOR_CAPACITY_UNAVAILABLE, автоматического перераспределения нет.

Демонстрация — место на одного, две заявки, назначение первой, понятный отказ по вместимости второй. Изменение этих учебных правил не следует выдавать за рабочий регламент.

## 3B · задание и проверка работы

TaskVersion = {id,placement_id,version,title,description,criteria:[{key,text,required}]}. Создаёт назначенный наставник через POST /placements/{id}/tasks. В первом пути одна опубликованная версия задания на участие; менять содержание можно новой версией до первой сдачи. После сдачи дальнейшая смена критериев требует отдельного пользовательского сценария.

Submission = {id,placement_id,task_version_id,attempt_no,text,artifact_url:null|string,submitted_at,submitted_by}. Исходная сдача сохраняется. Review = {id,submission_id,reviewed_by,reviewed_at,results:[{criterion_key,result:confirmed|needs_revision|not_verified,reason}]}.

| Операция | Результат |
|---|---|
| GET /placements/{id}/tasks | Опубликованная версия и доступная история |
| POST /placements/{id}/submissions | Студент, {task_version_id,text,artifact_url?} → новая попытка |
| GET /placements/{id}/submissions | Студент, наставник и организатор видят разрешённые попытки/отзывы |
| POST /submissions/{id}/review | Только действующий наставник, {results} → Review по всем критериям именно этой версии задания |
| POST /placements/{id}/mentor | HR, {expected_revision,mentor_actor_id,reason} → Placement с историей смены; старый автор отзыва сохраняется |

Внешняя ссылка без копии имеет ограничение изменяемого источника. Наставник может указать not_verified, если работа недоступна. Новый наставник получает право на новые решения, прежний теряет его. Точный повтор review возвращает прежний результат, другой итог той же попытки требует новой рассмотренной попытки либо будущей операции исправления.

Демонстрация — задание, сдача, возврат, новая попытка, подтверждение. Второй студент и прежний наставник после замены не могут записать чужое решение. Чат помощника, OCR и модель не нужны для этой сдачи.

## 3C · итог практики и пакет для карьеры

POST /placements/{id}/complete {expected_revision,outcome:completed|partial|stopped,reason} → Placement с completion {outcome,reason,actor_id,completed_at,criteria_snapshot}. Назначенный наставник или организатор фиксирует итог, completed требует подтверждённых required критериев последней применимой попытки. Partial/stopped показывают ограничение. Программа завершается предметным действием, дата окончания сама не выставляет успех.

POST /placements/{id}/university-result {expected_revision,result:passed|not_passed|unknown,source_reference,source_author,occurred_on} → Placement с отдельной записью вузовского результата. HR-организатор регистрирует внешний источник. Поле не меняет мнение наставника.

POST /placements/{id}/career-interest {expected_revision,interested:boolean,note} → Placement, только студент. Интерес и его отзыв сохраняются в истории.

POST /placements/{id}/career-package {criterion_keys,purpose,contact_basis} → {package_id,placement_id,student_actor_id,created_at,selected_results,university_result,education_status:"unconfirmed",purpose,contact_basis,transfer_status:"prepared"}. Только организатор, при актуальном interested=true и непустом основании цели/контакта. Выбираются разрешённые подтверждённые результаты; сведения из частных диалогов не входят. GET /career-packages/{id} доступен организатору и студенту при действующей видимости. После отзыва интереса новые пакеты недоступны, прежний имеет признак interest_withdrawn и историю.

Это подготовленный пакет с происхождением, который HR может передать вручную. Он не создаёт автоматически запись архива, отклик или официальный резерв. Диплом по результату практики не подтверждается.

Демонстрация — итог наставника, отдельно неизвестный/полученный итог вуза, собственный интерес студента и пакет из одного подтверждённого результата. При отзыве интереса новое формирование запрещено. Получатель архива не нужен для проверки этой задачи.
