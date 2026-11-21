# Серверная сборка без frontend

База приложения — `da058333393aa89113900a58331bb288e302424e`, 21 ноября 2026.
`deploy/compose.yaml` объединяет девять существующих Python-приложений. HTTP проходит
через Nginx, БД и API не публикуют собственных портов. Порт gateway `127.0.0.1:8080`
предназначен для Nginx хоста или SSH-туннеля. Frontend не собирается.

## Компоненты

| URL-префикс | Приложение | Постоянные данные | Способ входа существующего приложения |
|---|---|---|---|
| `/legacy` | Подбор, оценка, поиск, matching, management, отчётность | PostgreSQL + pgvector | `X-User-Login: hr_demo/admin_demo/dept_demo/dept2_demo`; рабочий поиск дополнительно требует серверного токена |
| `/workforce` | Сотрудники, оргструктура, адаптация, развитие | PostgreSQL; RabbitMQ и worker | `POST /api/v1/sessions`, роли `hr/admin/department/employee/candidate`, пароль `123` → Bearer |
| `/requirements` | Требования и вакансии | PostgreSQL, том документов | Та же Bearer-сессия Workforce |
| `/hiring` | Оформление и кабинет кандидата | PostgreSQL, том документов | Та же Bearer-сессия Workforce; кадровое подтверждение остаётся ручным |
| `/students` | Практика | SQLite | `Bearer fixture:<login>` из собственного actors.json |
| `/mobility` | Внутренняя мобильность | SQLite | `Bearer fixture:<login>` из собственного actors.json |
| `/social-support` | Социальная помощь | SQLite + документы | `Bearer fixture:<login>` из собственного actors.json |
| `/recognition` | Признание, мероприятия, материалы | SQLite | `Bearer demo-<actor>` из существующего seed |
| `/feedback` | Обратная связь и обращения | SQLite | `Bearer demo-<actor>`; анонимный ответ имеет отдельный одноразовый код |

Например, исходный `/api/v1/sessions` Workforce доступен как
`/workforce/api/v1/sessions`. Для каждого приложения доступны `/<prefix>/docs` и
`/<prefix>/openapi.json`; префикс снят Nginx и задан как ASGI root_path.

**Граница этой поставки.** Общий адрес и общий жизненный цикл контейнеров не меняют
контракты пользователей и обмена. Общая отзываемая сессия уже реализована в трёх
сервисах: Workforce/Hiring/Requirements. Остальные способы перечислены явно.
Автоматическое сопоставление по одинаковому UUID недопустимо: в общих fixtures
`…0101` — HR, в Mobility тот же UUID — employee. Требуется отдельная явная связь
локальной идентичности, а не замена всех токенов на один или назначение всем роли HR.
Эта сборка не заявляется реализацией единой идентичности во всех девяти сервисах.

## Первый запуск

Требуются Docker Engine, Compose v2 с `up --wait`, Python 3 на хосте. Пароли БД —
случайные hex-строки, совместимые с URL, не пароль входа пользователя. Генератор
создаёт файл с правами 600 и отказывается перезаписывать существующий.

```sh
python3 deploy/create-env.py deploy/local/runtime.env --release local
docker compose --env-file deploy/local/runtime.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/local/runtime.env -f deploy/compose.yaml --parallel 2 build
docker compose --env-file deploy/local/runtime.env -f deploy/compose.yaml up -d --wait --wait-timeout 240
python3 deploy/smoke.py
bash deploy/seed-roles.sh deploy/local/runtime.env
```

Все приложения работают от UID 10001, с одним Uvicorn worker. SQLite-файлы и документы
лежат в `/data` собственных томов. PostgreSQL — один кластер с четырьмя отдельными
БД и ролями; у ролей нет superuser и доступа к чужой БД через PUBLIC. Установку
pgvector выполняет bootstrap администратора. Миграции запускаются одноразовыми
контейнерами до API. Случайные пароли и содержимое `.env` не попадают в образ.

`seed-roles.sh` запускается явно: Workforce role/123, Legacy справочники и учебные
пользователи, Recognition/Feedback существующие учебные акторы. Он не импортирует
исходные резюме, не утверждает реальные требования и не выдаёт учебные данные за реальные.
Social support в текущем коде сам создаёт учебный перечень помощи; его замена требует
предметного источника. Остальные внутренние fixtures сохраняют авторское поведение.

Внешние LLM-ключи в этот запуск не загружаются. Получение API не доказывает живой LLM-
расчёт. E5 остаётся выключен согласно существующему default; тяжёлые ML-зависимости
не включены. Для работы LLM подключить предусмотренные `.env.example` переменные
к Legacy как серверные secrets отдельно от публичных отчётов.

## Проверки

```sh
python3 deploy/smoke.py
python3 deploy/check-sessions.py create --state deploy/local/probe.json
docker compose --env-file deploy/local/runtime.env -f deploy/compose.yaml down
docker compose --env-file deploy/local/runtime.env -f deploy/compose.yaml up -d --wait --wait-timeout 240
python3 deploy/check-sessions.py verify --state deploy/local/probe.json
```

HTTP-прогон проверяет девять настоящих OpenAPI, пути Swagger за прокси, 404, четыре
готовности с БД и отрицательные запросы без пользователя. Отдельный прогон проверяет
неверный пароль, `hr/123`, доступ одной сессией к Hiring/Requirements, сохранение
сессии после пересоздания контейнеров и отзыв во всех трёх сервисах. Промежуточный
токен хранится в файле 600, после отзыва файл удаляется. Содержимое токена не печатается.
Это инфраструктурная и сессионная проверка, не полный регресс всех предметных модулей.

## HTTPS/Nginx

После успешного внутреннего прогона `deploy/host-nginx.conf` включается в существующий
HTTPS server block. Сначала сохранить исходную конфигурацию, выполнить `nginx -t`,
затем reload. Сертификаты/продление остаются у Certbot хоста. Внешние порты — 80/443,
HTTP и www перенаправляются на HTTPS. Внутренний прокси принимает TLS scheme только
от loopback-входа; Uvicorn доверяет forwarded headers внутри закрытой Docker-сети.
Логи доступа выключены, чтобы URL с кодом опроса или идентификатором документа не
попал в общий access log. Лимит 21 MiB учитывает multipart поверх лимита файла 20 MiB.
Прокси не повторяет запросы записи к другому upstream.

## CI/CD

`.github/workflows/backend.yaml`: PR/main → сборка всех девяти образов по uv.lock →
полный Compose → HTTP и сессии → пересоздание → повтор. Только успешный main
публикует образы `ghcr.io/<owner>/<repo>-<service>:<полный SHA>`. Деплой не стартует
из произвольной ветки и сериализован. На сервере работают проверенные образы;
локальная сборка на VPS нужна только для первичной проверки до подключения CI.

В GitHub environment `backend` нужны secrets:
`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`.
Последний содержит заранее проверенный host key, а не результат непроверенного
ssh-keyscan в workflow. Repository variable `DEPLOY_ENABLED=true` включает CD.
Секрет SSH для CI должен быть отдельным от личного ключа участника.

На сервере требуются `/opt/hr/runtime.env` (600), каталог `/opt/hr/releases`, доступ
deploy-пользователя к Docker и registry. Для приватного GHCR администратор один раз
выполняет `docker login ghcr.io` отдельным токеном с чтением пакетов. Секреты в tar-
артефакт CI не включаются. Скрипт `release.sh` не обновляет main через git pull;
он получает bundle и образы одного прошедшего CI коммита.

Перед последующим выпуском `backup.sh` останавливает писателей и сохраняет БД,
SQLite и файлы в закрытый каталог. При ошибке backup прежние сервисы перезапускаются.
После успешного запуска и HTTP-проверки меняется symlink `current`, сохраняется
предыдущий путь. Это не обещание автоматического отката несовместимой миграции:
при её сбое потребуется восстановление проверенной резервной копии. Удаление
старых образов и backup выполняется отдельно с сохранением предыдущего выпуска.

Открытые условия приёмки: успешный прогон workflow именно в GitHub, проверенный
SSH/CD, восстановление backup в отдельную БД, включение публичного маршрута и
проверка извне. Фактическое состояние конкретного стенда фиксируется отдельно.
