"""Create deployment credentials once, without printing them or overwriting a file."""
import argparse
import os
from pathlib import Path
import re
import secrets

parser = argparse.ArgumentParser()
parser.add_argument("path", type=Path)
parser.add_argument("--release", required=True)
parser.add_argument("--image-prefix", default="hr-backend")
args = parser.parse_args()
if not re.fullmatch(r"[a-zA-Z0-9_.-]+", args.release):
    parser.error("release must be a Docker tag")
if not re.fullmatch(r"[a-z0-9./_-]+", args.image_prefix):
    parser.error("invalid image prefix")
values = {"RELEASE": args.release, "IMAGE_PREFIX": args.image_prefix, "GATEWAY_PORT": "8080"}
for key in ["DB_ADMIN_PASSWORD", "LEGACY_DB_PASSWORD", "WORKFORCE_DB_PASSWORD",
            "REQUIREMENTS_DB_PASSWORD", "HIRING_DB_PASSWORD", "RABBITMQ_PASSWORD"]:
    values[key] = secrets.token_hex(24)
args.path.parent.mkdir(parents=True, exist_ok=True)
fd = os.open(args.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write("".join(f"{key}={value}\n" for key, value in values.items()))
print(f"Created {args.path}; values were not printed.")
