"""Вспомогательный скрипт для сравнения с legacy app.requirements.schemas из корневого venv."""
import json
from pathlib import Path
import sys


def main() -> int:
    hr_root = Path(sys.argv[1])
    draft_path = Path(sys.argv[2])
    sys.path.insert(0, str(hr_root))
    from app.requirements.schemas import validate_draft

    data = json.loads(draft_path.read_text(encoding="utf-8"))
    print(json.dumps(validate_draft(data).model_dump(mode="json"), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
