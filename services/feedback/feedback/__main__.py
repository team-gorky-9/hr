import argparse
import os

from feedback.store import seed_demo
from feedback.demo_surveys import seed_demo_surveys

parser = argparse.ArgumentParser()
parser.add_argument("command", choices=["seed-demo", "seed-demo-surveys"])
parser.add_argument("--database", default=os.getenv("FEEDBACK_DB", "data/feedback.db"))
args = parser.parse_args()
if args.command == "seed-demo-surveys":
    seed_demo_surveys(args.database)
    print("Synthetic survey catalog prepared.")
else:
    seed_demo(args.database)
    print("Training actors prepared; use README for the local demonstration credentials.")
