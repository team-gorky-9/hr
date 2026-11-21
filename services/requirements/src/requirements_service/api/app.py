"""Сборка экземпляра FastAPI с управлением жизненным циклом ресурсов."""
from contextlib import asynccontextmanager
import uuid

from fastapi import FastAPI, Request

from ..auth import ActorDirectory, FixtureActorDirectory, WorkforceActorDirectory
from ..config import Settings, load_settings
from ..db.session import create_db_engine, create_session_factory
from ..errors import install_error_handlers
from ..messaging.outbox import OutboxRelay
from ..messaging.transport import MessagePublisher, RabbitMQPublisher
from ..seed import seed_positions
from ..service import RequirementsService
from ..storage import LocalFileStorage
from .routes import api_router, health_router
from ..catalog import router as catalog_router


def build_actor_directory(settings: Settings) -> ActorDirectory:
    if settings.auth_mode == "fixture":
        return FixtureActorDirectory(settings.fixture_actors_path)
    return WorkforceActorDirectory(
        settings.workforce_base_url,
        timeout_sec=settings.workforce_timeout_sec,
    )


def create_app(
    settings: Settings | None = None,
    *,
    publisher: MessagePublisher | None = None,
    actor_directory: ActorDirectory | None = None,
) -> FastAPI:
    """Создать приложение FastAPI с настраиваемыми зависимостями."""
    cfg = settings or load_settings()
    engine = create_db_engine(cfg.database_url)
    session_factory = create_session_factory(engine)
    storage = LocalFileStorage(cfg.file_root, max_bytes=cfg.file_max_bytes)
    directory = actor_directory or build_actor_directory(cfg)
    msg_publisher = publisher or RabbitMQPublisher(cfg.rabbitmq_url)
    relay = OutboxRelay(
        session_factory=session_factory,
        publisher=msg_publisher,
        max_attempts=cfg.outbox_max_attempts,
        base_backoff_sec=cfg.outbox_base_backoff_sec,
        poll_interval_sec=cfg.outbox_poll_interval_sec,
    )
    service = RequirementsService(
        settings=cfg,
        storage=storage,
        actor_directory=directory,
        outbox_relay=relay,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if cfg.seed_on_startup:
            with session_factory() as session:
                try:
                    seed_positions(
                        session,
                        org_path=cfg.fixture_org_path,
                        default_organization_id=uuid.UUID(cfg.seed_organization_id),
                    )
                    session.commit()
                except Exception:
                    session.rollback()
                    raise
        relay.start()
        try:
            yield
        finally:
            relay.stop()
            msg_publisher.close()
            engine.dispose()

    app = FastAPI(
        title="Requirements Service",
        version="1.0.0",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = cfg
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.storage = storage
    app.state.actor_directory = directory
    app.state.publisher = msg_publisher
    app.state.outbox_relay = relay
    app.state.service = service

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        raw_rid = request.headers.get("X-Request-Id")
        try:
            rid = str(uuid.UUID(raw_rid)) if raw_rid else str(uuid.uuid4())
        except ValueError:
            rid = str(uuid.uuid4())
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router)
    app.include_router(catalog_router)
    return app
