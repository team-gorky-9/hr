import argparse
import os

from feedback.store import seed_demo

parser = argparse.ArgumentParser()
parser.add_argument("command", choices=["seed-demo"])
parser.add_argument("--database", default=os.getenv("FEEDBACK_DB", "data/feedback.db"))
args = parser.parse_args()
seed_demo(args.database)
print("Training actors prepared; use README for the local demonstration credentials.")
