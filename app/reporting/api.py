"""Embeddable report endpoints. Optional service credentials are scoped to one organisation."""
import os
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Query, Response
from fastapi import Path as PathParam
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.reporting import store
from app.reporting.analytics import AnalyticsQuery, catalog as analytics_catalog, query_report
from app.reporting.analysis_excel import analysis_book, operations_book
from app.reporting.briefing import chart_specs, executive_brief
from app.reporting.operations import query_operations
from app.reporting.signals import build_signals
from app.reporting.excel import make_workbook
from app.api.errors import ApiError, install_error_handlers
from app.reporting.schema import Snapshot, Version

SnapshotId = Annotated[str, PathParam(pattern=r"^[0-9a-f]{64}$")]
MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSX_RESPONSE = {200: {"content": {MIME: {"schema": {"type": "string", "format": "binary"}}}}}
bearer = HTTPBearer(auto_error=False)


def allowed_scope(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> str | None:
    if credentials is None:
        return None
    expected = os.environ.get("HR_REPORTS_WORK_TOKEN")
    scope = os.environ.get("HR_REPORTS_WORK_SCOPE")
    if not scope or not expected or not secrets.compare_digest(expected.encode(), credentials.credentials.encode()):
        raise ApiError(401, "REPORT_AUTH", "Недействительный ключ доступа к отчётам")
    return scope


Scope = Annotated[str | None, Depends(allowed_scope)]


class OperationsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_month: int = Field(default=1, strict=True, ge=1, le=12)
    end_month: int = Field(default=12, strict=True, ge=1, le=12)
    departments: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_period(self):
        if self.start_month > self.end_month or len(self.departments) != len(set(self.departments)):
            raise ValueError("Проверьте период и перечень подразделений")
        return self


def download(data, filename):
    return Response(content=data, media_type=MIME, headers={"Cache-Control": "private, no-store",
                    "Content-Disposition": f'attachment; filename="{filename}.xlsx"'})


def cache_policy(response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"


def create_router(root: Path | None = None) -> APIRouter:
    catalog = root if root is not None else store.catalogue_dir()
    router = APIRouter(prefix="/api/v1/reports/annual", dependencies=[Depends(cache_policy)])

    def get_version(snapshot_id: str, scope: str | None) -> dict:
        try:
            return store.read(snapshot_id, catalog, demo_only=scope is None, work_scope=scope)
        except FileNotFoundError as exc:
            raise ApiError(404, "REPORT_NOT_FOUND", "Версия отчёта не найдена") from exc
        except store.InvalidSnapshot as exc:
            raise ApiError(500, "CORRUPT_REPORT", "Сохранённая версия повреждена") from exc

    @router.get("", response_model=list[Version])
    def versions(scope: Scope, year: Annotated[int | None, Query(ge=1, le=9999)] = None):
        try:
            return store.list_versions(catalog, year, demo_only=scope is None, work_scope=scope)
        except store.InvalidSnapshot as exc:
            raise ApiError(500, "CORRUPT_REPORT", "Сохранённая версия повреждена") from exc

    @router.get("/{snapshot_id}", response_model=Snapshot, response_model_exclude_unset=True)
    def snapshot(snapshot_id: SnapshotId, scope: Scope):
        return get_version(snapshot_id, scope)

    @router.get("/{snapshot_id}/xlsx", response_class=Response,
                responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                                                  {"schema": {"type": "string", "format": "binary"}}}}})
    def workbook(snapshot_id: SnapshotId, scope: Scope):
        data = get_version(snapshot_id, scope)
        return Response(content=make_workbook(data),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Cache-Control": "no-store",
                                 "Content-Disposition": f'attachment; filename="report-{data["year"]}-{snapshot_id[:12]}.xlsx"'})

    @router.get("/{snapshot_id}/catalog")
    def capabilities(snapshot_id: SnapshotId, scope: Scope):
        data = get_version(snapshot_id, scope)
        return {**analytics_catalog(), "snapshot_id": snapshot_id,
                "available": "analytics_index" in data,
                "vacancies": [{"key": v["vacancy_key"], "label": v["label"]} for v in data["vacancies"]],
                "departments": (data.get("operations") or {}).get("departments", {}),
                "operations_available": bool(data.get("operations"))}

    @router.get("/{snapshot_id}/brief")
    def brief(snapshot_id: SnapshotId, scope: Scope):
        return executive_brief(get_version(snapshot_id, scope))

    @router.get("/{snapshot_id}/signals")
    def signals(snapshot_id: SnapshotId, scope: Scope):
        return build_signals(get_version(snapshot_id, scope))

    def analyze(data, query):
        try:
            return query_report(data, query)
        except LookupError as exc:
            raise ApiError(409, "REBUILD_FOR_ANALYTICS", str(exc)) from exc
        except ValueError as exc:
            raise ApiError(422, "INVALID_REPORT_QUERY", str(exc)) from exc

    @router.post("/{snapshot_id}/query")
    def analyze_json(snapshot_id: SnapshotId, query: AnalyticsQuery, scope: Scope):
        return analyze(get_version(snapshot_id, scope), query)

    @router.post("/{snapshot_id}/charts")
    def charts(snapshot_id: SnapshotId, query: AnalyticsQuery, scope: Scope):
        data = get_version(snapshot_id, scope)
        result = analyze(data, query)
        return {"snapshot_id": snapshot_id, "query": result["query"], "charts": chart_specs(data, result)}

    @router.post("/{snapshot_id}/query/xlsx", response_class=Response, responses=XLSX_RESPONSE)
    def analyze_excel(snapshot_id: SnapshotId, query: AnalyticsQuery, scope: Scope):
        data = get_version(snapshot_id, scope)
        return download(analysis_book(data, analyze(data, query)), f"analysis-{data['year']}-{snapshot_id[:12]}")

    def operations(data, query):
        try:
            return query_operations(data, query.start_month, query.end_month, query.departments)
        except ValueError as exc:
            raise ApiError(422, "INVALID_OPERATIONS_QUERY", str(exc)) from exc

    @router.post("/{snapshot_id}/operations")
    def ops_json(snapshot_id: SnapshotId, query: OperationsQuery, scope: Scope):
        result = operations(get_version(snapshot_id, scope), query)
        return {"snapshot_id": snapshot_id, "query": query.model_dump(), **result}

    @router.post("/{snapshot_id}/operations/xlsx", response_class=Response, responses=XLSX_RESPONSE)
    def ops_excel(snapshot_id: SnapshotId, query: OperationsQuery, scope: Scope):
        data = get_version(snapshot_id, scope)
        return download(operations_book(data, operations(data, query), query.model_dump()),
                        f"departments-{data['year']}-{snapshot_id[:12]}")

    return router


def create_app(root: Path | None = None) -> FastAPI:
    app = FastAPI(title="Годовые отчёты о подборе", version="1")
    install_error_handlers(app)
    app.include_router(create_router(root))
    return app


app = create_app()
