# Волна 3 · развитие · этап 1

Спецификация трёх последовательных небольших задач Давида. Основа — готовые акторы/назначения Workforce и пользовательский сценарий развития. Новый брокер, сервисная миграция и внешний учебный провайдер для сдачи не требуются. Реализация может находиться отдельным development-модулем в текущем Workforce, префикс /api/v1/development.

## Общие данные и права

UUID, timestamps с зоной, revision с 1 и expected_revision на изменениях. Обычная ошибка доступа к чужому объекту — 404, неверный ввод — 422, неправильное состояние — 409. Использовать готовую сессию либо явно включённые fixture-акторы. employee создаёт свои цели, department может действовать назначенным руководителем/проверяющим конкретного плана. Назначение хранится в самом плане с основанием и организацией. Общая HR-роль не открывает неотправленные личные цели. Конфликт проверки собственного свидетельства запрещён.

Цель и её история принадлежат сотруднику. План хранит снимок согласованной цели, критерии и назначенных участников. Текст/ссылка свидетельства имеют автора и время. Одинаковый текст разных людей не доказывает одинаковый вклад.

## 3A · личная цель и согласованный план

Goal = {id,owner_actor_id,organization_id,title,description,revision,status:private|shared,shared_with_actor_id:null|UUID}. Plan = {id,goal_id,owner_actor_id,manager_actor_id,reviewer_actor_id,title,criteria:[{key,text,required}],activities:[{key,title,criterion_keys,resource_note}],goal_revision,revision,status:proposed|returned|active|closed,decision_note:null|string}. title/description и массивы содержательны; ключи внутри объекта уникальны, связи критериев существуют.

| Операция | Вход / результат |
|---|---|
| POST /goals | {title,description} → 201 Goal владельца |
| GET /goals и GET /goals/{id} | Свои цели; после share адресат читает только направленную цель |
| PATCH /goals/{id} | {expected_revision,title?,description?} → Goal, только владелец |
| POST /goals/{id}/share | {expected_revision,recipient_actor_id} → Goal, адресат своей организации и допустимого назначения |
| POST /plans | {goal_id,goal_revision,reviewer_actor_id,title,criteria,activities} → 201 Plan; автор — получатель share, владелец цели читает предложение |
| GET /plans и GET /plans/{id} | Только назначенные участники, свои поля |
| PATCH /plans/{id} | {expected_revision,title?,criteria?,activities?,reviewer_actor_id?} → Plan, manager в proposed/returned |
| POST /plans/{id}/respond | {expected_revision,decision:accept|return,note} → Plan, только owner. accept → active, return → returned с причиной |

accept фиксирует согласованную редакцию цели/критериев. Позднее изменение личной цели не переписывает активный план. Подтверждение resource_note означает записанную договорённость участников; реальное место курса/проекта не резервируется автоматически.

Минимальная демонстрация — сотрудник создал личную цель; другой человек не читает; сотрудник направил руководителю; руководитель предложил план; сотрудник вернул с замечанием, затем принял исправление. На выходе один active Plan.

## 3B · работа, доработка и заключение

Submission = {id,plan_id,activity_key,attempt_no,criterion_keys,statement,artifact:{kind:text|url,value,mutable_source:boolean},created_by,created_at}. Текст сохраняется снимком. Для URL без сохранённой копии mutable_source=true и проверяющий видит это ограничение. Доступ к внешней закрытой ссылке этим API не выдаётся. Новая сдача получает новый id и attempt_no, оригинал сохраняется.

Review = {id,submission_id,reviewer_actor_id,created_at,results:[{criterion_key,result:confirmed|needs_revision|not_verified,reason}]}. Проверяющий назначен в активном плане, result относится к конкретной попытке. Каждый предъявленный criterion_key получает результат; он существует в закреплённом плане. История неизменяема, новая сдача не получает старое подтверждение автоматически.

| Операция | Вход / результат |
|---|---|
| POST /plans/{id}/submissions | {activity_key,criterion_keys,statement,artifact} → 201 Submission, владелец активного плана |
| GET /plans/{id}/submissions | items попыток и относящихся результатов для назначенных участников |
| POST /submissions/{id}/review | {results} → 201 Review, назначенный reviewer, один итог на попытку. Точный повтор возвращает прежний, иной повтор — 409 REVIEW_EXISTS |
| GET /plans/{id}/progress | {criteria:[{key,state:unsubmitted|waiting|confirmed|needs_revision|not_verified,submission_id?,review_id?}],completed_count,total_count} |

Прогресс строится по последней относящейся попытке, а не по лучшему старому результату. Перед новой сдачей виден прежний отзыв; новая попытка ожидает проверки. Самопроверка и чужой reviewer запрещены. Новые файлы и универсальный реестр профессиональных компетенций не нужны для этого законченного пути сдачи текста/ссылки.

Демонстрация — предъявить работу, получить доработку, создать новую попытку, получить подтверждение. Прежний текст и отзыв читаются, прогресс соответствует последней попытке.

## 3C · итог и адресное продолжение

POST /plans/{id}/close {expected_revision,outcome:reached|partial|stopped,reason} → Plan с closure {outcome,reason,actor_id,closed_at,criteria_snapshot}. Участники owner/manager могут закрыть свой план. reached разрешён только при подтверждении всех required критериев; иначе 409 REQUIRED_CRITERIA_OPEN. partial/stopped сохраняют ограничения и причину. Закрытый план не принимает новую сдачу.

POST /plans/{id}/share-result {criterion_keys,purpose} → {package_id,plan_id,owner_actor_id,purpose,created_at,items:[{criterion_key,result,source_submission_id,review_id,reviewer_actor_id,reviewed_at}],limitations}. Только owner выбирает разрешённые подтверждённые результаты закрытого плана. GET /result-packages/{id} читает собственный пакет. Полный приватный план и артефакт не копируются автоматически; это подготовленный пакет для передачи человеком, не подтверждение получения соседом.

Вход от новой ДИ в этой маленькой задаче — HR/руководитель передаёт человеку ссылку на изменённую версию и критерии через существующий разрешённый канал; сотрудник создаёт цель, указав источник в description. Автоматическое определение затронутых сотрудников и массовое назначение проверки остаются отдельной функциональной карточкой.

Демонстрация — нельзя закрыть reached при открытом обязательном критерии; после подтверждения закрыть, выбрать один результат для пакета и увидеть его источник. Частичный итог остаётся частичным. Интеграция с mobility не нужна для сдачи.
