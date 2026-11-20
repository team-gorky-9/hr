"""Verify six draft profiles, literal citations and bundled original documents offline.

This proves structural/provenance validity, not content approval or model quality.
Uses the public requirements-01 package conversion before any database write.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import uuid

from app.requirements.package import convert_profile, validate_sources, keys, PACKAGE_FIELDS
from scripts.verify_requirement_profiles import (
    PACKAGE_SCHEMA, all_rows, check_profile_format, read_json, require,
)

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "fixtures/requirement_profiles/all_six"
POSITION_CODES = {"junior-python-dev", "python-dev", "qa-manual", "frontend-dev", "junior-ux-ui", "hr-consultant"}


def verify_package(package: dict, manifest: dict, originals: Path) -> dict:
    require(package["package_schema"] == PACKAGE_SCHEMA, "Unsupported package schema")
    profiles = package["profiles"]
    require(len(profiles) == 6 and {p["position_code"] for p in profiles} == POSITION_CODES,
            "Expected one draft for each of six position codes")
    sources = {d["id"]: d for d in manifest["documents"]}
    require(len(sources) == len(manifest["documents"]), "Duplicate source id")
    keys(package, PACKAGE_FIELDS, {"package_schema", "profiles"})
    verified = validate_sources(manifest, originals)
    documents = {key: uuid.uuid5(uuid.NAMESPACE_URL, f"requirement-source:{key}") for key in sources}
    result = []
    for profile in profiles:
        check_profile_format(profile, sources)
        require(profile["is_synthetic"] is False, "Working draft must retain its real-source contour")
        row_keys = [row["key"] for row in all_rows(profile)]
        require(len(row_keys) == len(set(row_keys)), "Duplicate row key")
        codes = [c["code"] for c in profile["competencies"]]
        require(len(codes) == len(set(codes)), "Duplicate competency code")
        rules = {r["key"]: r for r in profile["formal_requirements"]}
        for row in rules.values():
            dependency = row["params"].get("requires_requirement")
            require(not dependency or (dependency in rules and rules[dependency]["kind"] == "education_level"),
                    "Unresolved education requirement dependency")
        convert_profile(profile, verified, documents, Counter())
        result.append({"position_code": profile["position_code"], "version": profile["version"],
                       "status": profile["status"], "is_synthetic": profile["is_synthetic"],
                       "sources": [s["source_id"] for s in profile["sources"]],
                       "formal_requirements": len(rules), "competencies": len(profile["competencies"]),
                       "indicators": sum(len(c["indicators"]) for c in profile["competencies"]),
                       "operational_use_allowed": profile["operational_use_allowed"]})
    return {"verification": "schema_and_original_provenance_only", "sources_verified": len(sources),
            "operational_approval": False, "profiles": result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    report = verify_package(read_json(args.root / "profiles.draft.json"),
                            read_json(args.root / "sources.json"), args.root / "originals")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
