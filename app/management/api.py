"""HTTP /api/v1/management — только кадровик и администратор (X-User-Login legacy API).
Роль department в агрегированной сводке недопустима до отдельного ограниченного представления."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.auth import StaffUser
from app.api.schemas import Contour
from app.db.session import get_session
from app.management.schemas import OverviewOut
from app.management.service import overview

router = APIRouter(prefix="/api/v1/management", tags=["management"])


@router.get("/overview", response_model=OverviewOut)
def overview_route(
    response: Response,
    user: StaffUser,
    session: Annotated[Session, Depends(get_session)],
    contour: Annotated[Contour, Query(description="working или training — задаётся явно")],
    period_from: Annotated[date, Query(alias="from", description="Начало периода, включительно (МСК)")],
    period_to: Annotated[date, Query(alias="to", description="Конец периода, исключительно (МСК)")],
):
    """Текущая работа (существующая воронка) и факты телефонных встреч за период (4A)."""
    result = overview(session, contour, period_from, period_to)
    response.headers["Cache-Control"] = "private, no-store"
    return result
