# Волна 4 · внутренняя мобильность · этап 1

Три последовательные задачи Дениса. Собственный mobility-модуль/пакет, /api/v1/mobility. Входы — готовые или локальные учебные сотрудники и их руководители. Не нужно ждать API развития, признания или новый брокер.

## Участники

employee выражает свой интерес. Владелец задачи назначен на Opportunity. Текущий руководитель берётся из подтверждённого организационного контекста либо явно помеченного fixture. HR регистрирует организационные назначения в своей области. Объектные права проверяются отдельно от имени общей роли.

UUID, revision, expected_revision, история автора/основания и стандартные 404/409/422. Личный интерес до согласованного раскрытия не виден текущему руководителю. Новое сервисное размещение и автоматические уведомления отложены.

## 4A · возможность и выраженный интерес

Opportunity = {id,organization_id,owner_actor_id,title,result_description,starts_on,ends_on,time_percent,revision,status:draft|open|closed|cancelled}. Доля времени >0 и <=100, период корректен. Interest = {id,opportunity_id,employee_actor_id,comment,revision,status:submitted|withdrawn|not_selected|selected}.

| Операция | Результат |
|---|---|
| POST /opportunities | Владелец создаёт задачу с указанными полями |
| POST /opportunities/{id}/open {expected_revision} | Открывает при полных условиях |
| GET /opportunities и GET /opportunities/{id} | Сотрудник видит доступную опубликованную возможность |
| POST /opportunities/{id}/interests {comment} | Сотрудник выражает интерес, один открытый на пару |
| GET /interests/{id} и GET /opportunities/{id}/interests | Собственный участник либо владелец этой задачи |
| POST /interests/{id}/withdraw {expected_revision,reason} | Сотрудник отзывает своё обращение |
| POST /interests/{id}/select {expected_revision} | Владелец выбирает для согласования, само по себе это ещё не начало работы |
| POST /interests/{id}/decline {expected_revision,reason} | Владелец фиксирует понятный исход |

Демо — две внутренние возможности, интерес к одной, владелец видит его, текущий руководитель пока не получает этот личный интерес. Отзыв сохраняется, рейтинг сотрудника не меняется.

## 4B · версия условий и согласование времени

Proposal = {id,interest_id,employee_actor_id,owner_actor_id,manager_actor_id,starts_on,ends_on,time_percent,revision,status:awaiting_employee|awaiting_manager|agreed|declined|withdrawn,employee_response:null|accepted|declined,manager_response:null|accepted|declined,reason:null|string}.

POST /interests/{id}/proposal {starts_on,ends_on,time_percent,manager_actor_id,manager_source_reference} создаёт владелец по selected интересу. Назначение руководителя подтверждено входным источником в той же организации. GET /proposals/{id} доступен владельцу/сотруднику, а руководителю — после согласия сотрудника направить ему именно эту версию.

POST /proposals/{id}/employee-response {expected_revision,accepted,reason?} принимает только employee. При согласии возникает awaiting_manager. POST /proposals/{id}/manager-response с теми же полями принимает назначенный руководитель; отказ требует объяснение, согласие даёт agreed.

PATCH /proposals/{id} {expected_revision,starts_on?,ends_on?,time_percent?,reason} выполняет владелец после согласованного уточнения. Существенная правка создаёт новую revision, сбрасывает прежние подтверждения, возвращает awaiting_employee. История хранит согласованные ранее условия и ответы. Руководитель, совпавший с участником, не подтверждает собственное время — требуется отдельный назначенный согласующий.

Демо — сотрудник согласен, руководитель просит иной период через отказ с пояснением, владелец меняет даты, обе стороны подтверждают новую версию. Старое согласие не закрывает новую.

## 4C · участие, результат и внутренняя вакансия

POST /proposals/{id}/start {expected_revision} создаёт Participation только для agreed версии. Participation = {id,proposal_id,proposal_revision,employee_actor_id,owner_actor_id,starts_on,ends_on,time_percent,status:active|completed|stopped,revision,result_note:null|string}. Повтор start возвращает прежнюю запись.

GET /participations/{id} доступен участнику, владельцу и согласующему в своей области. POST /participations/{id}/finish {expected_revision,outcome:completed|stopped,result_note} выполняет владелец; причина содержательна. Участник добавляет своё подтверждение/несогласие POST /participations/{id}/employee-feedback {expected_revision,accepted,note}. Отзыв владельца и ответ человека сохраняются раздельно.

POST /participations/{id}/result-package {purpose,share_allowed} выполняет сотрудник, создавая ограниченный пакет своей завершённой работы с автором отзыва и выбранной целью. Он может предъявить его развитию или признанию вручную. Общий уровень компетенции и награда не начисляются автоматически.

Постоянный переход — отдельный вход: POST /vacancy-interests {vacancy_ref,publication_revision,comment} от сотрудника, GET /vacancy-interests/{id}, POST /vacancy-interests/{id}/record-consideration {expected_revision,consideration_ref,confirmation_basis} от HR. Хранится source_mode=manual-confirmed, цель и ссылка на зарегистрированное рассмотрение. Простое желание перейти не меняет должность, фактический перевод выполняет кадровый владелец. Без готового подбора запрос остаётся prepared.

Демо — согласованная временная задача становится участием, владелец фиксирует итог, сотрудник получает выбранный пакет. На внутреннюю вакансию есть отдельный интерес и подтверждение принятия в подбор. Для этих примеров достаточно учебного vacancy_ref и ручного подтверждения HR.
