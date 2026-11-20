"""Ошибки вызова модели. Текст резюме и ключи в сообщения не попадают."""


class LLMError(Exception):
    """Общий предок ошибок модели."""


class LLMUnavailableError(LLMError):
    """Сеть, таймаут, HTTP 5xx/429 или ошибка авторизации — ответа нет."""


class LLMInvalidResponseError(LLMError):
    """Ответ получен, но не прошёл схему даже после повтора."""
