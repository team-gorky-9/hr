# Практика · поставка 3A

База ec0a764, ветка feature/wave-3a-practice-placement. Реализованы место, публикация, заявка/отзыв/отклонение, назначение и чтение участия по wave-3-students-stage-1. Хранилище students отдельно от коллег, миграция 0001_students, учебные акторы и второй candidate. Постоянные данные и журнал редакций сохраняются.

Команда из hr: `uv --directory services/students run pytest tests/test_3a.py -q -s` — 1 passed. Реальные HTTP к отдельному uvicorn; две конкурентные заявки на одно место дали один успех и CAPACITY_UNAVAILABLE. Повтор назначения вернул прежнее участие. Вторая возможность с тем же занятым наставником дала MENTOR_CAPACITY_UNAVAILABLE. Проверены чужой студент/организация, сохранение неназначенной заявки и чтение после нового процесса.

Учебные ID: opportunity 86de1504-80d5-42ed-a6d2-7cf13b750a35, placement 9054e6e3-4754-4a3f-a6ba-251cf45a5d87, оставшаяся application 35384d11-6c3b-40ee-a103-10a29f5556d5. Даты 2026-12-01…2026-12-31, capacity=1. Авторитет студента — fixture actor_id, сведения о вузе помечены synthetic_student_statement, назначение — synthetic_manual_confirmation.

Первый запуск выявил ошибку определения wheel-пакета; исправлено явным packages=[students], тот же сценарий прошёл. PostgreSQL/Docker, реальный вуз и кадровая интеграция не проверялись. SQLite транзакция гарантирует последнюю квоту; PostgreSQL использует advisory lock организации, но не проверен запуском. Следующая часть — 3B, API/инструкция доступны в services/students/README.md и /openapi.json.
