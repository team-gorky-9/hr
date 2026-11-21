# Волна 6 · путь HR и кандидата · демонстрационная сборка

**21 ноября 2026 · Илья.**
- База — `hr` `main` `ecf5794`: включает помощь #69–72, фронтенд #68, кандидата #66/67/73 и обратную связь #74–76.
- Карточка — `hq/tasks/stage-1/wave-6a-ilya-recruitment-demo.md` в штабе.
- Контракты — [wave-5-candidate-portal-stage-1](../contracts/wave-5-candidate-portal-stage-1.md), [wave-3-matching-stage-1](../contracts/wave-3-matching-stage-1.md), [Hiring](../../services/hiring/README.md).

**Предшествующая задача (5C), кратко.** В Hiring есть публичный исход (`public-outcome`), сообщения кабинета с отметкой прочтения и отзыв обращения. Сделано в hr#73, тесты сервиса — 50 passed.

## Что показываем

Один сквозной путь через HTTP двух сервисов:
- Hiring (`services/hiring`, порт 8103) — обращение кандидата;
- старый подбор (`app.main`, порт 8000) — учебный корпус поиска.

Скрипт `services/hiring/hiring/recruitment_demo.py` выполняет шаги и пишет все запросы и ответы в [`wave-6-recruitment-demo.transcript.json`](wave-6-recruitment-demo.transcript.json) — это материал для Аси.

```bash
# база старого подбора с учебным корпусом поиска
DATABASE_URL=…/hr uv run alembic upgrade head
DATABASE_URL=…/hr uv run python -m app.search load-demo
DATABASE_URL=…/hr uv run uvicorn app.main:app --port 8000 &
# Hiring на отдельной базе
cd services/hiring
DATABASE_URL=…/hiring uv run python -m hiring serve &        # миграции 0001–0004, AUTH_MODE=fixture
uv run python -m hiring.recruitment_demo --transcript ../../docs/reports/wave-6-recruitment-demo.transcript.json
```

| № | Кто | Запрос | Результат |
|---|---|---|---|
| 1 | candidate | `POST /candidate-requests` (вакансия «Экономист» `…0c01` ред. 1) → `POST …/documents` (`resume-new.pdf`) → `POST …/submit` | 201 / 201 / 200, `ОБР-000001`, `submitted` |
| 2 | hr | `GET /candidate-requests?status=submitted` → `POST …/information-request` («опыт работы», «обновлённое резюме») | 200, `needs_information`, сообщение в кабинете |
| 3 | candidate | `GET …/messages` → `POST …/messages/{id}/read` → `POST …/documents` (`resume-updated.pdf`) → `POST …/addendum` | 200, прочитано; `submitted`, дополнение с файлом |
| 4 | hr | `POST …/ready`; поиск в старом подборе `POST /api/v1/search/candidates` (training, «функциональные требования к СЭД») | `ready`; подготовленная запись `search-9001`, фрагмент «Сбор функциональных требований к СЭД, BPMN, постановка задач подрядчику.», отклик `response` |
| 5 | hr | `POST …/record-consideration` со ссылками `legacy-hr-training` на `search-9001` и её отклик | 200, `forwarded`, `manual-confirmed`; основание — запрос и фрагмент поиска |
| 6 | hr | `POST …/public-outcome` `continue` + следующий шаг | `forwarded`, сообщение «Рассмотрение продолжается» |
| 7 | candidate | `GET /candidate-requests/{id}` → `GET …/messages` → `POST …/read` → повторный `GET` | исход и шаг «Ожидайте приглашения в течение 10 рабочих дней»; ссылок на записи подбора и источника решения нет |
| 8 | candidate2 | `GET` обращения, сообщений и файла candidate | **404 / 404 / 404** |

**Полученные ID** (прогон 21.11, база `hiring_w6`):

| Объект | ID |
|---|---|
| обращение | `2eb66a6c-bc87-4c8e-b094-8f76e9751aec` (`ОБР-000001`) |
| резюме | `3b1842fd-97c9-40e1-aa60-28c91e17b1b6` |
| дополнение | `400a1d67-9e54-439d-ba9a-9463ecf84b47` |
| сообщения | запрос `c12017a6-c69a-41cf-9f1f-35e0eeaef964`, исход `ada732a2-3f00-425e-af71-f2765119acfd` |
| подготовленная запись старого подбора | `search-9001` `d2895829-ca66-4a38-b82a-cdbbf3436528`, отклик `f0f62a96-5844-45b1-92f8-7d5aa3608e05` |

ID записей старого подбора зависят от базы, где выполнен `load-demo`. Скрипт берёт их из ответа поиска, а не из констант.

## Что обработано, а что подготовлено заранее

- **Новые файлы кандидата** (`resume-new.pdf`, `resume-updated.pdf`) сохраняются как неизменяемые оригиналы обращения. Текст из них не извлекается, они не оценивались и в поиск не попадают. OCR и обработка непрочитанного скана — пункт 7.7.
- **Основание совпадения** взято из заранее подготовленной учебной записи `search-9001` корпуса `load-demo`: текст и индекс поиска уже есть.
- **Связь обращения с этой записью — явно учебная ручная связь для показа** (`identity_basis` так и подписан). Это не тот же человек, что учётка `candidate`, и сверка личности не выполнялась. Автоматического соединения Hiring и подбора нет: регистрация `manual-confirmed`.

## Интерфейс (наблюдение в браузере)

Прототип #68 открыт в Chromium (Playwright, `vite`, режим «Портал соискателя» → «Войти»). Снимок — [`wave-6-recruitment-demo-cabinet-prototype.png`](wave-6-recruitment-demo-cabinet-prototype.png).

Экран «Личный кабинет» показывает данные макета. Во время прохода не было **ни одного** запроса к `/api/`. Соответствие для подключения:

| Элемент прототипа | Поле API Hiring | Расхождение с контрактом |
|---|---|---|
| Баннер «Нужно ответить» + поле ответа | `information_request.public_message`, `requested_items`; ответ — `POST …/addendum` | В прототипе «Вопрос задан автоматически». По контракту вопрос задаёт HR |
| Карточка «Мои отклики» со статусом и шкалой | `GET /candidate-requests` → `number`, `status`, `vacancy.title`, `submitted_at` | Шкала «Телефонное интервью → Решение департамента» в Hiring не хранится. Статусы: `submitted` / `needs_information` / `ready` / `forwarded` / `closed` / `withdrawn` |
| «Причина от департамента: …» | `outcomes[].public_explanation` | Контракт: полный отзыв департамента кандидату не копируется, показывается только публичный текст HR |
| «Вам подойдёт вакансия …: совпадение 82%» | — | Процента совпадения в API нет: matching не считает суммарный процент |
| «Мои документы» | `documents[]` (`original_name`, `kind`, `created_at`) | — |
| «Тесты для отбора» | — | В API нет |
| Сообщения | `GET …/messages`, `unread_messages`, `POST …/read` | В прототипе нет отдельного блока |

## Проверка и ограничения

- Отрицательный случай: candidate2 не открывает обращение, сообщения и файл candidate — 404 (шаг 8 в transcript).
- Тесты Hiring не перезапускались: код сервиса в этой задаче не менялся, добавлен только демо-скрипт. Мешающих показу дефектов на прогоне не обнаружено, исправлений не было.
- Ограничения:
  - вход — учебные fixture-акторы;
  - вакансии — учебный снимок `public-vacancies.json`;
  - автоматической передачи Hiring ↔ подбор нет (этап 2);
  - фронтенд не подключён к API.
