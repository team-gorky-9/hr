"""Server settings. Everything that changes trust (auth, source of the hiring decision) comes
from the server environment only — a client cannot switch it."""
import os
from dataclasses import dataclass, field
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]

AUTH_MODES = {"fixture", "workforce"}
# legacy-api is part of the contract, but the legacy selection API is not available to this
# service in stage 1, so the server refuses to start with it instead of pretending to check.
SOURCE_MODES = {"fixture", "manual-confirmed"}


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: _env("DATABASE_URL", "postgresql+psycopg://hiring:hiring@localhost:5413/hiring")
    )
    auth_mode: str = field(default_factory=lambda: _env("AUTH_MODE", "fixture"))
    workforce_url: str = field(default_factory=lambda: _env("WORKFORCE_URL", "http://localhost:8101"))
    source_mode: str = field(default_factory=lambda: _env("SELECTION_SOURCE", "fixture"))
    fixture_dir: Path = field(
        default_factory=lambda: Path(_env("FIXTURE_DIR", str(REPO_ROOT / "fixtures/wave-1")))
    )
    # Training snapshots accepted in fixture mode: the shared fixtures/wave-1/selection.json plus
    # this service's extra synthetic candidates (the second candidate of the withdrawal path).
    extra_selections_file: Path = field(
        default_factory=lambda: Path(
            _env("EXTRA_SELECTIONS_FILE", str(SERVICE_ROOT / "fixtures/extra-selections.json"))
        )
    )
    extra_actors_file: Path | None = field(
        default_factory=lambda: Path(_env("EXTRA_ACTORS_FILE", str(SERVICE_ROOT / "fixtures/extra-actors.json")))
    )
    # Учебный снимок публичных вакансий для candidate-portal, пока каталог вакансий не подключён.
    public_vacancies_file: Path = field(
        default_factory=lambda: Path(
            _env("PUBLIC_VACANCIES_FILE", str(SERVICE_ROOT / "fixtures/public-vacancies.json"))
        )
    )
    file_root: Path = field(default_factory=lambda: Path(_env("FILE_ROOT", str(SERVICE_ROOT / ".files"))))
    file_max_bytes: int = field(default_factory=lambda: int(_env("FILE_MAX_BYTES", str(20 * 1024 * 1024))))
    auth_timeout_seconds: float = field(default_factory=lambda: float(_env("AUTH_TIMEOUT_SECONDS", "3")))
    interaction_enabled: bool = field(default_factory=lambda: _env("INTERACTION_ENABLED", "false").lower() == "true")
    interaction_mapping_file: Path = field(default_factory=lambda: Path(_env("INTERACTION_MAPPING_FILE", str(SERVICE_ROOT / "fixtures/interaction-mapping.json"))))
    interaction_legacy_url: str = field(default_factory=lambda: _env("INTERACTION_LEGACY_URL", "http://legacy:8000"))
    interaction_legacy_instance: str = field(default_factory=lambda: _env("INTERACTION_INSTANCE_ID", "training-legacy"))
    interaction_organization_id: str = field(default_factory=lambda: _env("INTERACTION_ORGANIZATION_ID", ""))
    interaction_gateway_key: str = field(default_factory=lambda: _env("INTERACTION_GATEWAY_KEY", ""))
    interaction_cursor_secret: str = field(default_factory=lambda: _env("INTERACTION_CURSOR_SECRET", ""))
    interaction_connect_seconds: float = field(default_factory=lambda: float(_env("INTERACTION_CONNECT_SECONDS", "1")))
    interaction_read_seconds: float = field(default_factory=lambda: float(_env("INTERACTION_READ_SECONDS", "2")))
    interaction_overall_seconds: float = field(default_factory=lambda: float(_env("INTERACTION_OVERALL_SECONDS", "3")))
    interaction_max_bytes: int = field(default_factory=lambda: int(_env("INTERACTION_MAX_BYTES", "262144")))

    def __post_init__(self):
        if self.auth_mode not in AUTH_MODES:
            raise ValueError(f"AUTH_MODE must be one of {sorted(AUTH_MODES)}")
        if self.source_mode not in SOURCE_MODES:
            raise ValueError(f"SELECTION_SOURCE must be one of {sorted(SOURCE_MODES)} in stage 1")
        if self.file_max_bytes <= 0:
            raise ValueError("FILE_MAX_BYTES must be positive")
        if self.interaction_enabled:
            from urllib.parse import urlsplit
            import uuid
            uuid.UUID(self.interaction_organization_id)
            url = urlsplit(self.interaction_legacy_url)
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.query or url.fragment or url.path not in {"", "/"}:
                raise ValueError("INTERACTION_LEGACY_URL must be an internal HTTP origin")
            if not self.interaction_gateway_key or not self.interaction_cursor_secret:
                raise ValueError("Interaction window requires gateway and cursor secrets")
            if min(self.interaction_connect_seconds, self.interaction_read_seconds, self.interaction_overall_seconds, self.interaction_max_bytes) <= 0:
                raise ValueError("Interaction budgets must be positive")
