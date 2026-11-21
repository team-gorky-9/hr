import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from feedback.actions import router as actions_router
from feedback.confidential import router as confidential_router
from feedback.cycles import router
from feedback.publications import router as publications_router
from feedback.store import initialize


def create_app(database_path=None):
    app = FastAPI(title="Employee feedback — training stage 1", version="0.1.0")
    app.state.database_path = Path(database_path or os.getenv("FEEDBACK_DB", "data/feedback.db"))
    initialize(app.state.database_path)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError):
        # Pydantic's default error includes the submitted input, possibly an access code or private text.
        return JSONResponse(status_code=422, content={"detail": {"code": "INVALID_INPUT"}})

    @app.middleware("http")
    async def no_cache(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(router, prefix="/api/v1/feedback", tags=["Pulse cycles"])
    app.include_router(publications_router, prefix="/api/v1/feedback", tags=["Fixed publications"])
    app.include_router(actions_router, prefix="/api/v1/feedback", tags=["Measures and outcomes"])
    app.include_router(confidential_router, prefix="/api/v1/feedback", tags=["Confidential cases"])
    return app
