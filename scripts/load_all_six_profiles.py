"""Load the bundled six-role package through the public requirements API.

Default is a dry run. --commit saves drafts; approval remains a separate command.
"""
import argparse
import json

from sqlalchemy.exc import OperationalError

from app.requirements import RequirementError, load_package
from app.requirements.cli import profile_summary
from app.requirements.package import read_json
from scripts.verify_all_six_profiles import DEFAULT_ROOT, verify_package


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--created-by", default="requirements-02")
    args = parser.parse_args(argv)
    try:
        package = read_json(DEFAULT_ROOT / "profiles.draft.json")
        manifest = read_json(DEFAULT_ROOT / "sources.json")
        provenance = verify_package(package, manifest, DEFAULT_ROOT / "originals")
        from app.db.session import SessionLocal
        with SessionLocal() as session:
            result = load_package(session, package, manifest, DEFAULT_ROOT / "originals", created_by=args.created_by)
            report = {"status": "loaded" if args.commit else "dry_run", "persisted": args.commit,
                      "sources_verified": provenance["sources_verified"], "profiles": [],
                      "review_fields": result.review_fields}
            for source, loaded in zip(package["profiles"], result.profiles, strict=True):
                report["profiles"].append({**profile_summary(loaded), "position_code": source["position_code"],
                                           "sources": source["sources"]})
            if args.commit:
                session.commit()
            else:
                session.rollback()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except RequirementError as error:
        print(json.dumps({"status": "refused", "error": error.as_dict()}, ensure_ascii=False))
        return 1
    except ValueError:
        print(json.dumps({"status": "refused", "error": {"code": "invalid_package",
                         "message": "Пакет не прошёл проверку шести профилей."}}, ensure_ascii=False))
        return 1
    except OperationalError:
        print(json.dumps({"status": "unavailable", "error": {"code": "database_unavailable"}}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
