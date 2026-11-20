# Hiring · контракт первой волны 1.0

Спецификация к реализации Ильёй. Обязателен [общий контракт](wave-1-common.md). Сервис hiring владеет оформлением. Существующий отклик и его решение читаются через доступный вход или учебный снимок.

## Вход и данные

PositiveSelection содержит application_ref {system,id}, candidate_ref {system,id,display_name}, organization_id, department_id, position_code, outcome="hired", decided_at, decided_by_actor_id, decision_basis. В первой волне это подтверждённый снимок решения для API hr/admin. Источник fixture явно помечается is_synthetic=true. При использовании действующего legacy читать отклик через его доступный API и сохранять соответствие; отсутствие признака нужного решения даёт 409 SELECTION_NOT_READY. В реализации документировать, какой источник проверен. Запись снимка по доверенному вводу HR имеет источник manual-confirmed и не изображается автоматической интеграцией.

is_synthetic — обязательный boolean поля PositiveSelection. provenance — серверные поля source_mode (fixture/manual-confirmed/legacy-api), verified_by_actor_id, verified_at; их клиент не подменяет. Режим приёма выбирается серверной конфигурацией/операцией уполномоченного HR и явно виден в Case.

Case содержит id, revision, selection, status preparing/awaiting_documents/ready/withdrawn/started, checklist_version, candidate_actor_id UUID/null, starts_on date/null, basis object/null, workforce_status not_sent/pending/registered/review_required, employee_id/assignment_id UUID/null. Человек связывается с кабинетным actor отдельно, только HR с основанием. Статус started означает зарегистрированный HR подтверждённый факт начала, а workforce_status показывает отдельную доставку кадровому владельцу.

Уточнение 21 ноября — workforce_status дополнен registered_with_difference для завершённой проверки с сохранением прежних кадровых сведений. Case хранит workforce_resolution null/corrected/kept_existing, workforce_review_reason string/null и workforce_assignment_snapshot с фактически полученными department_id, position_code, starts_on, revision.

ChecklistItem содержит id, case_id, key, title, required bool, status requested/received/accepted/needs_revision, document_ids[], review_reason string/null, reviewed_by_actor_id UUID/null, revision. История хранит все версии файлов и решений.

## API

| Метод и путь | Тело / ответ | Правила |
|---|---|---|
| POST /cases | {selection,candidate_actor_id?,identity_basis?,checklist:[{key,title,required}],checklist_version} → 201 Case | hr/admin, организация совпадает с областью. Учебный комплект явно synthetic. Один активный case на application_ref, повтор того же ключа возвращает прежний |
| GET /cases | ?status=… → список | HR своей организации; candidate — только свои явно связанные дела |
| GET /cases/{id} | → Case, checklist | candidate получает только цель, статусы, собственные позиции/пояснения и разрешённый результат, без внутренних decision_basis/actor IDs и чужих сведений |
| POST /cases/{id}/request-documents | {expected_revision,message} → Case | preparing/awaiting_documents → awaiting_documents, понятный запрос |
| POST /cases/{id}/items/{item_id}/submit | {expected_revision,document_id,comment?} → ChecklistItem | Здесь expected_revision относится к item. Candidate своей записи либо HR; файл свой/доступен делу, иной case_id запрещён |
| POST /cases/{id}/items/{item_id}/review | {expected_revision,result:"accepted"|"needs_revision",reason} → ChecklistItem | HR/admin, по версии item, обязательная причина возврата. Предыдущие решения сохраняются |
| POST /cases/{id}/ready | {expected_revision} → Case | preparing/awaiting_documents → ready только если все обязательные позиции accepted |
| POST /cases/{id}/start | {expected_revision,starts_on,basis:{document_id,reference,issued_on},confirmation_basis} → Case | HR/admin, ready → started, подтверждённый файл основания и явная дата. Outbox employment.ready атомарен с записью. Само наступление даты ничего не выполняет |
| POST /cases/{id}/withdraw | {expected_revision,reason} → Case | HR либо кандидат своего дела, preparing/awaiting_documents/ready → withdrawn. started требует отдельного кадрового исправления и даёт INVALID_STATE |
| GET /cases/{id}/history | → события | Отдавать только видимые роли поля и объяснения |
| POST /cases/{id}/link-account | {expected_revision,candidate_actor_id,identity_basis} → Case | HR/admin, проверенная связь, чужая организация запрещена |
| POST /cases/{id}/correct-start | {expected_revision,starts_on?,basis?,reason} → Case | HR/admin, started, новая версия и employment.ready, workforce_status=review_required до сверки. Старый факт сохраняется |

После изменения принятого документа item возвращается received и прежнее accepted больше не даёт готовность. Для started новый документ принимается как дополнение/исправление с отдельным кадровым разбором, без самовольной отмены назначения. При редактировании item сервис также увеличивает case revision, чтобы ready/start проверяли актуальный комплект. Подтверждение готовности и добавление исправления в конкуренции не должны пропустить устаревшие документы.

## Файлы и внешняя передача

Реализовать документы по common. kind — hiring_application, hiring_evidence, employment_basis. Скачивание кандидатом только собственного материала/разрешённого для него документа; скрытое внутреннее основание недоступно по прямому ID. Факт проверки оригинала фиксирует уполномоченный HR через review/confirmation_basis. Загруженный скан сам не доказывает оформление.

employment.ready содержит реквизиты и ссылку basis.document_ref, сформированную из локального документа. На assignment.registered сервис находит свой source_case_id и актуальную передачу, заполняет кадровую ссылку и workforce_status=registered. Неизвестное дело, чужая организация или конфликт версии сохраняют вопрос в очереди, не создают новое дело. Исправленная дата не должна быть подтверждена старым ответом: сохранять correlation_id и ожидаемую ревизию передачи. В assignment.registered возвращается correlation_id исходного employment.ready.

Локальный тестовый приёмник читает настоящий RabbitMQ и отдаёт assignment.registered по fixtures, умеет задержку, повтор и отсутствие ответа. Это позволяет закончить автономную поставку без сервиса Давида. При интеграции те же события обрабатывает workforce.

После /correct-start новое employment.ready требует отдельного решения Workforce. Hiring потребляет assignment.review-resolved только от workforce для своей организации, case_id и последнего ожидаемого source_event_id/source_case_revision/correlation_id. resolution=corrected даёт workforce_status=registered, resolution=kept_existing — registered_with_difference. HR видит предложенную дату, фактическую кадровую дату и объяснение; started и собственные источники Hiring сохраняются. При следующей /correct-start статус снова review_required, прежний результат хранится в истории. Повтор ответа не повторяет переход; устаревший ответ не закрывает текущую сверку.

В локальной подмене добавить два альтернативных результата из corrections.json. Ветвь kept_existing завершается видимым расхождением, а не бесконечным ожиданием и не молчаливой заменой данных Hiring. Начальный assignment.registered продолжает использоваться для первой регистрации.

## Учебный путь сдачи

HR открывает выбранного кандидата, создаёт комплект из двух пунктов, получает один документ, возвращает нечитаемый второй, принимает исправление и подтверждает готовность. Кандидат видит своё замечание и загруженные версии. HR фиксирует подтверждённый выход. При отключённом брокере факт сохраняется, доставка pending. После восстановления локальный приёмник отвечает, workforce_status меняется. Повтор команд/сообщений сохраняет одно дело и один подтверждённый исход. Второй кандидат отказывается до выхода; его дело withdrawn и кадровое событие не отправлено.

Перечень учебных документов служит проверке механизма. Реальный обязательный комплект и проверяющие назначаются организацией позднее.
