import argparse

from workforce.config import Settings
from workforce.database import make_engine, migrate, seed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "seed"])
    args = parser.parse_args()
    settings = Settings()
    engine = make_engine(settings.database_url)
    if args.command == "prepare":
        migrate(engine)
    seed(engine, settings)
    engine.dispose()


if __name__ == "__main__":
    main()
