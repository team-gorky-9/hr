"""Кто вызывает маршрут: учебная авторизация стенда (контракт api.md v0.3, п. 1.2).

Клиент передаёт логин в заголовке X-User-Login. API находит активного пользователя
в таблице users и берёт роль оттуда. Пароля нет, поэтому это не защита: заголовок
нужен, чтобы журналы (stage_events.actor_user_id, audit_log.user_id, reserve_entries.added_by)
знали, кто действовал, и чтобы маршрут мог отказать роли без допуска.

Маршруты чтения Этапа 1 заголовок не требуют. Маршруты backend-02 (этапы, история,
кросс-оценки, резерв, воронка) требуют его и роль hr или admin: область доступа
департамента по подразделениям ещё не согласована, поэтому роль department получает 403
и по прямому ID данных не видит.
"""
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.db.enums import UserRole
from app.db.models import User
from app.db.session import get_session

USER_HEADER = "X-User-Login"

# Кадровые действия и чтение их данных — кадровик и администратор. Роль department
# (представитель департамента-заказчика) получит доступ в своей области в workflow-01.
STAFF = (UserRole.HR, UserRole.ADMIN)


def current_user(
    session: Annotated[Session, Depends(get_session)],
    x_user_login: Annotated[
        str | None, Header(description="Логин пользователя стенда (учебная авторизация): hr_demo, admin_demo; dept_demo — роль department")
    ] = None,
) -> User:
    """Активный пользователь из заголовка X-User-Login или 401."""
    login = (x_user_login or "").strip()
    if not login:
        raise ApiError(401, "USER_REQUIRED", f"Укажите пользователя в заголовке {USER_HEADER}")
    user = session.scalar(select(User).where(User.login == login))
    if user is None or not user.is_active:
        # Логин в ответ не возвращаем: details не повторяют ввод клиента.
        raise ApiError(401, "UNKNOWN_USER", "Пользователь не найден или отключён")
    return user


def require_role(*roles: UserRole) -> Callable[..., User]:
    """Зависимость FastAPI: пользователь из заголовка с одной из ролей, иначе 403."""
    allowed = tuple(roles)

    def dependency(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in allowed:
            raise ApiError(
                403,
                "FORBIDDEN_ROLE",
                "Действие недоступно для роли пользователя",
                {"role": str(user.role), "allowed_roles": [str(r) for r in allowed]},
            )
        return user

    return dependency


StaffUser = Annotated[User, Depends(require_role(*STAFF))]
