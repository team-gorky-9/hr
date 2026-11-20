"""python -m hiring migrate | serve [--port 8103]"""
import argparse

import uvicorn

from hiring.config import Settings
from hiring.database import make_engine, migrate


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m hiring")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply this service's Alembic migrations")
    serve = sub.add_parser("serve", help="migrate, then run the API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8103)
    args = parser.parse_args()
    settings = Settings()
    engine = make_engine(settings.database_url)
    migrate(engine)
    engine.dispose()
    if args.command == "serve":
        uvicorn.run("hiring.api:create_app", factory=True, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
