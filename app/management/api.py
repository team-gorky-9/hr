"""HTTP /api/v1/management — только кадровик и администратор (X-User-Login legacy API).
Роль department в агрегированной сводке недопустима до отдельного ограниченного представления."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from fastapi import Path as PathParam
from sqlalchemy.orm import Session

from app.api.auth import StaffUser
from app.api.schemas import Contour
from app.db.session import get_session
from app.management.annual import create_release, read_release, release_out
from app.management.schemas import AnnualReleaseIn, AnnualReleaseOut, OverviewOut, ReleaseSummary
from app.management.service import overview
from app.reporting import store
from app.reporting.excel import make_workbook

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


SnapshotId = Annotated[str, PathParam(pattern=r"^[0-9a-f]{64}$")]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def report_catalog():
    """Каталог годового модуля из серверной настройки HR_REPORTS_DIR, не из запроса клиента."""
    return store.catalogue_dir()


Catalog = Annotated[object, Depends(report_catalog)]


@router.post("/annual-reports", response_model=ReleaseSummary, status_code=201)
def create_annual_report(body: AnnualReleaseIn, response: Response, user: StaffUser, catalog: Catalog,
                         session: Annotated[Session, Depends(get_session)]):
    """Годовой выпуск из разрешённых откликов и телефонных встреч (4B) существующим расчётом годового модуля."""
    result = create_release(session, body, user, catalog)
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.get("/annual-reports/{snapshot_id}", response_model=AnnualReleaseOut)
def read_annual_report(snapshot_id: SnapshotId, response: Response, user: StaffUser, catalog: Catalog,
                       session: Annotated[Session, Depends(get_session)]):
    row, report = read_release(session, snapshot_id, catalog)
    response.headers["Cache-Control"] = "private, no-store"
    return release_out(session, row, report)


@router.get("/annual-reports/{snapshot_id}/xlsx", response_class=Response,
            responses={200: {"content": {XLSX: {"schema": {"type": "string", "format": "binary"}}}}})
def read_annual_report_xlsx(snapshot_id: SnapshotId, user: StaffUser, catalog: Catalog,
                            session: Annotated[Session, Depends(get_session)]):
    """Excel из того же сохранённого снимка, что и JSON."""
    _, report = read_release(session, snapshot_id, catalog)
    return Response(content=make_workbook(report), media_type=XLSX, headers={
        "Cache-Control": "private, no-store",
        "Content-Disposition": f'attachment; filename="report-{report["year"]}-{snapshot_id[:12]}.xlsx"'})
