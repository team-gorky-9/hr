import argparse
from pathlib import Path

from recognition.store import seed_demo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed-demo"])
    parser.add_argument("--database", default="data/recognition.db")
    args = parser.parse_args()
    seed_demo(Path(args.database))
    print("Synthetic recognition actors seeded. Demo tokens are for loopback use only.")


if __name__ == "__main__":
    main()
