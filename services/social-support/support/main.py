from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .core import Problem, Store
from .api import router

def create_app(data_dir=None):
    app = FastAPI(title="Social support · synthetic stage 1", version="0.1.0")
    app.state.store = Store(data_dir)

    @app.exception_handler(Problem)
    async def problem(request: Request, exc: Problem):
        return JSONResponse(status_code=exc.status,
                            content={"error": {"code": exc.code, "message": exc.message}})

    app.include_router(router)
    return app

app = create_app()
