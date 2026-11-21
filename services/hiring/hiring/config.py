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

    def __post_init__(self):
        if self.auth_mode not in AUTH_MODES:
            raise ValueError(f"AUTH_MODE must be one of {sorted(AUTH_MODES)}")
        if self.source_mode not in SOURCE_MODES:
            raise ValueError(f"SELECTION_SOURCE must be one of {sorted(SOURCE_MODES)} in stage 1")
        if self.file_max_bytes <= 0:
            raise ValueError("FILE_MAX_BYTES must be positive")
