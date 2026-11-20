import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "postgresql+psycopg://workforce:workforce@localhost:5411/workforce"
        )
    )
    rabbitmq_url: str = field(
        default_factory=lambda: os.getenv("RABBITMQ_URL", "amqp://workforce:workforce@localhost:5681/%2F")
    )
    fixture_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("FIXTURE_DIR", str(Path(__file__).resolve().parents[3] / "fixtures/wave-1"))
        )
    )
    auth_mode: str = field(default_factory=lambda: os.getenv("AUTH_MODE", "workforce"))
    session_hours: int = field(default_factory=lambda: int(os.getenv("SESSION_HOURS", "8")))
    retry_seconds: float = field(default_factory=lambda: float(os.getenv("RETRY_SECONDS", "5")))
    max_attempts: int = field(default_factory=lambda: int(os.getenv("MAX_ATTEMPTS", "5")))
    poll_seconds: float = field(default_factory=lambda: float(os.getenv("POLL_SECONDS", "1")))

    def __post_init__(self):
        if self.auth_mode not in {"workforce", "fixture"}:
            raise ValueError("AUTH_MODE must be workforce or fixture")
        if min(self.session_hours, self.retry_seconds, self.max_attempts, self.poll_seconds) <= 0:
            raise ValueError("Session and retry settings must be positive")
