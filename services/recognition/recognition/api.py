import os
from pathlib import Path

from fastapi import FastAPI

from recognition.campaigns import router as campaigns_router
from recognition.events import router as events_router
from recognition.store import initialize
from recognition.thanks import router


def create_app(database_path=None):
    app = FastAPI(title="Recognition — stage 1", version="0.1.0")
    app.state.database_path = Path(database_path or os.getenv("RECOGNITION_DB", "data/recognition.db"))
    initialize(app.state.database_path)
    app.include_router(router, prefix="/api/v1/recognition", tags=["Thanks"])
    app.include_router(campaigns_router, prefix="/api/v1/recognition", tags=["Campaigns"])
    app.include_router(events_router, prefix="/api/v1/recognition", tags=["Events"])
    return app
