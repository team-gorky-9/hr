# Requirements · контракт первой волны 1.0

Спецификация к реализации Денисом. Обязателен [общий контракт](wave-1-common.md). Сервис отвечает за подготовку требований и версии утверждённого результата. Кадровый пользователь в этой волне работает через API и OpenAPI; фронтенд — следующая поставка.

## Сохранить существующую предметную схему

Тело содержимого профиля использует requirement-draft/1.0 из [публичного загрузчика](requirement-loader.md). Операции существующего app.requirements и его CLI продолжают работать. Новый сервис не пишет напрямую в БД legacy-hr.

Переиспользовать существующие валидаторы app/requirements/schemas.py, app/schemas/requirements.py и семантику проверки цитат, версий и утверждения, когда это допускает автономное окружение. Прочитать app/requirements/service.py и app/db/repository.py как первичное основание. Их session/ORM не являются сетевым контрактом. Если внутреннее хранение нового сервиса отличается, воспроизвести исходные инварианты на тех же учебных профилях. Соответствие legacy источников и ID профилей при будущей миграции задаётся отдельно, без скрытого переключения текущего оценщика.

## Ресурсы и состояния

Position — {id,organization_id,code,title,revision}. В первой волне это справочник требований к должности; штатные назначения принадлежат workforce.

Source — документ по common, плюс position_code, extraction_status ready/unavailable/failed, extracted_text string/null, reason string/null. Для TXT/DOCX/текстового PDF используются доступные механизмы чтения продукта. Скан с отсутствующим текстом возвращает unavailable и путь ручного подтверждённого ввода; OCR/внешняя модель для завершения этой поставки не требуются.

Draft — {id,organization_id,position_code,revision,status:editing|in_review|returned|approved,content:requirement-draft/1.0,review_note:string|null}. Изменять content можно в editing/returned. Статус approved фиксирует неизменяемую опубликованную версию. ApprovedProfile — {id,draft_id,organization_id,position_code,version,contour:"training"|"working",content,approval_basis,approved_by_actor_id,approved_at,is_current}. Новая публикация одного position/contour заменяет current, но сохраняет предыдущую.

## Операции

| Метод и путь | Тело / ответ | Правило |
|---|---|---|
| POST /positions | {code,title} → 201 Position | hr/admin своей организации, code уникален |
| GET /positions | → список | hr/admin либо department в разрешённой области организации для согласования |
| POST /sources | multipart file, position_code → 201 Source | hr/admin. Байты и извлечённый текст имеют происхождение. /documents маршруты common также доступны |
| GET /sources/{id} | → Source | Разрешённые акторы своей организации. Ошибка извлечения видна, а не скрыта пустой строкой |
| POST /drafts | {position_code,content} → 201 Draft | hr/admin, проверить структуру, цитаты и локальные source UUID |
| GET /drafts | ?status=…&position_code=… → список | Область организации |
| GET /drafts/{id} | → Draft | Согласующий department читает только назначенное рассмотрение |
| PATCH /drafts/{id} | {expected_revision,content,change_reason} → Draft | editing/returned, полная новая редакция, источник исходного файла сохраняется |
| POST /drafts/{id}/submit | {expected_revision,reviewer_actor_id} → Draft | editing/returned → in_review, reviewer — активный department/hr/admin той же организации из проверенных акторов |
| POST /drafts/{id}/review | {expected_revision,result:"accepted"|"returned",note} → Draft | Только назначенный согласующий либо admin с явной причиной замещения. returned → returned. accepted оставляет in_review и сохраняет положительное согласование этой редакции |
| POST /drafts/{id}/approve | {expected_revision,approval_basis} → 201 ApprovedProfile | hr/admin. Требуется положительное согласование той же ревизии содержимого. Статус draft → approved, immutable content. Атомарно меняется current и создаётся requirements.approved |
| POST /profiles/{id}/revise | {change_reason} → 201 Draft | HR/admin. Содержимое копируется в новый editing, старый профиль остаётся опубликованным до нового утверждения |
| GET /profiles/{id} | → ApprovedProfile | Полный утверждённый payload с источниками |
| GET /positions/{code}/approved-profile | ?contour=training|working → ApprovedProfile | Если нет — 404 NO_APPROVED_PROFILE |
| GET /drafts/{id}/history | → события | Автор, действие, версии, причины, источник |
| POST /sources/{id}/transcription | {expected_revision,text,transcription_basis} → Source | HR/admin, ручной текст помечен как зарегистрированный человеком, source original immutable. Любой ранее созданный профиль сохраняет свою редакцию текста/цитат |

Согласующий не меняет критерии, а возвращает их автору с замечаниями. HR может отдельно иметь назначение согласующего, но это должно быть явно задано примером, а не автоматически присвоено роли. Перед approve ещё раз сверяются источники и scope. При смене содержимого прежнее согласование не переносится. Контур следует is_synthetic в content.

Draft дополнительно хранит content_revision, увеличиваемую только при изменении content. Согласование фиксирует именно content_revision и версии источников. Общая revision увеличивается и при процессуальных действиях, используется для expected_revision. После submit/review согласование остаётся применимым, пока content_revision и закреплённые версии источников совпадают.

Конкурирующие публикации сериализуются по position+contour. Один текущий профиль на область, номер версии монотонный. Повтор той же операции не создаёт дополнительную версию. Если источник недоступен, утверждение отклоняется 409 SOURCE_NOT_READY. Если цитата не найдена в выбранной редакции — 422 SOURCE_MISMATCH.

## Автономная проверка

Учебный профиль по формату из fixtures/requirement_profiles/py-9001.draft.json проверяет типы и диапазоны. Собственный источник создаётся через API, UUID в content заменяются на реально полученные ID. Это допустимая привязка примера, не изменение его смысла. В [общем наборе](../../fixtures/wave-1/README.md) есть должность и учебная ДИ. После утверждения событие читается тестовым подписчиком из настоящего RabbitMQ, профиль получается через HTTP и валидируется потребителем.

Путь сдачи — источник → черновик → возврат замечания → исправление → положительное согласование → утверждение v1 → новая редакция v2. Потребитель v1 сохраняет исходный результат, current читает v2. Проверить неправильную цитату, чужую организацию, скан без текста, повтор ключа, stale revision, две параллельные публикации и восстановление outbox после остановки.

## Чего ждать от соседей

Для начала достаточно fixture-акторов и локального справочника. Прямых запросов в workforce или hiring кроме интеграционного /session не требуется. Значения position_code из первой волны фиксированы в наборе. Техническая проверка профиля не утверждает реальные нормативные требования без уполномоченного кадровика.
