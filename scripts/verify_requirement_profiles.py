"""Check review data and provenance; does not score candidates or write to a DB.

Run from the product root:
    python -m scripts.verify_requirement_profiles [--archive /path/to/kadry.zip]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "requirement_profiles"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PACKAGE_SCHEMA = "requirement-profile-review/0.2"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"Duplicate JSON property: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)


def paragraphs_from_docx(content):
    with zipfile.ZipFile(io.BytesIO(content)) as doc:
        body = ET.fromstring(doc.read("word/document.xml")).find(f"{W}body")
        require(body is not None, "Missing Word document body")
        return {
            f"P{i}": text
            for i, p in enumerate(body.iter(f"{W}p"), 1)
            if (text := "".join(t.text or "" for t in p.iter(f"{W}t"))).strip()
        }


def check_ref(ref, sources):
    require(ref["source_id"] in sources, f"Unknown source: {ref}")
    source = sources[ref["source_id"]]
    require(ref["sha256"] == source["sha256"], f"Wrong source hash: {ref}")
    require(bool(ref["address"].strip()), "Source address is empty")
    require(bool(ref["paragraph_ids"]), "Source paragraph list is empty")
    for key in ref["paragraph_ids"]:
        require(key in source["paragraphs"], f"Unknown paragraph {key}")
    original = "\n".join(source["paragraphs"][key] for key in ref["paragraph_ids"])
    require(bool(ref["quote"]) and ref["quote"] in original,
            f"Quote does not match {ref['source_id']} {ref['paragraph_ids']}")


def all_rows(profile):
    yield from profile["formal_requirements"]
    yield from profile["source_notes"]
    for competency in profile["competencies"]:
        yield competency
        yield from competency["indicators"]


def check_profile_format(profile, sources):
    """Shared file format for real and synthetic profiles; not a DB contract."""
    require(type(profile.get("is_synthetic")) is bool and "synthetic" not in profile,
            "Missing is_synthetic or legacy synthetic flag")
    require(profile["status"] == "draft" and profile["operational_use_allowed"] is False,
            "Draft enabled for decisions")
    require(profile["approved_by_user_id"] is None and profile["approved_at"] is None,
            "Draft has approval metadata")
    declared = {s["source_id"] for s in profile["sources"]}
    used = {ref["source_id"] for row in all_rows(profile) for ref in row["source_refs"]}
    require(len(declared) == len(profile["sources"]) and declared == used,
            "Profile source list does not match row citations")
    for source in profile["sources"]:
        require(source["source_id"] in sources, "Unknown profile source")
        original = sources[source["source_id"]]
        require(source["revision"] == original["revision"], "Source revision mismatch")
        require(source["role"] == original["kind"], "Source role mismatch")
    for row in all_rows(profile):
        key = row["key"]
        require(row.get("origin") in {"source", "team"}, f"Invalid origin: {key}")
        require(bool(row.get("rationale", "").strip()), f"Missing origin rationale: {key}")
        require(not {"obligation", "verification_method", "verification_channels"} & row.keys(),
                f"Legacy metadata: {key}")
        require(row["origin"] != "source" or bool(row["source_refs"]), f"Missing source: {key}")
        for ref in row["source_refs"]:
            check_ref(ref, sources)
    leaves = profile["formal_requirements"] + [r for c in profile["competencies"] for r in c["indicators"]]
    for row in leaves:
        require(type(row.get("is_mandatory")) is bool, f"is_mandatory must be boolean: {row['key']}")
        require(row.get("verification") in {"resume", "documents", "interview", "test"},
                f"Invalid verification: {row['key']}")
        require(row["check_stage"] in {"screening", "interview"}, row["key"])
        if row["verification"] == "interview":
            require(row["check_stage"] == "interview", "Interview check cannot run at screening")


def check_package(package, source_manifest):
    require(package["package_schema"] == PACKAGE_SCHEMA, "Unsupported package schema")
    require(package["contract_status"] == "proposal", "Unapproved package marked as contract")
    require(package["compatible_with_db_v1"] is False, "DB v1 incompatibility must remain explicit")
    sources = {s["id"]: s for s in source_manifest["documents"]}
    require(len(sources) == len(source_manifest["documents"]), "Duplicate source id")
    for source in sources.values():
        path = source["path"]
        require(not path.startswith("Кадры/") and ".." not in Path(path).parts,
                f"Source path must be archive-root-relative: {path}")
        require(unicodedata.normalize("NFC", path) == path, f"Non-NFC path: {path}")
    issue_ids = {q["id"] for q in package["open_questions"]}
    require(len(issue_ids) == len(package["open_questions"]), "Duplicate issue id")
    keys = set()
    row_count = 0
    for profile in package["profiles"]:
        check_profile_format(profile, sources)
        require(profile["is_synthetic"] is False, "Real profile status")
        for row in all_rows(profile):
            key = row["key"]
            require(key not in keys, f"Duplicate row key {key}")
            keys.add(key)
            row_count += 1
            require(row["interpretation_status"] in {"transcribed", "proposed"}, key)
            require(bool(row["source_refs"]), f"Missing source: {key}")
            require(set(row["issues"]) <= issue_ids, f"Unknown issue: {key}")
            for outcome in ("met", "not_met", "unknown"):
                require(bool(row["acceptance"][outcome]), f"Missing expectation {key}: {outcome}")
        for rule in profile["formal_requirements"]:
            require(rule["kind"] in {"education_level", "education_field", "experience", "knowledge", "other"}, rule["key"])
            require(rule["check_stage"] == "screening", "Interview knowledge is not a formal gate")
            params = rule["params"]
            require(params["schema_version"] == "0.1", rule["key"])
            alts = params.get("alternatives", [])
            require(len({a["key"] for a in alts}) == len(alts), "Duplicate alternative key")
            if rule["kind"] == "experience":
                require(params["minimum_defined"] is False and "min_months" not in params,
                        "Real source has no numeric experience threshold")
                require(bool(params["relevance_hint"]), "Missing relevance description")
        require(all(rule["kind"] != "knowledge" for rule in profile["formal_requirements"]),
                "Knowledge must remain outside formal gates in this draft")
    hr, py = package["profiles"]
    require(hr["position_code"] == "hr-consultant" and py["position_code"] == "python-dev", "Wrong positions")
    require(len(hr["competencies"]) == 5, "Matrix must preserve five competencies")
    expected = {"ПАК": ("key", 90, 100), "ИТК": ("key", 90, 100), "РК": ("basic", 90, 100),
                "ОИК": ("basic", 90, 100), "ДК": ("special", 100, 100)}
    require({c["code"] for c in hr["competencies"]} == set(expected), "Matrix codes changed")
    matrix_paragraphs = set()
    for c in hr["competencies"]:
        require((c["rank"], c["target_level_min"], c["target_level_max"]) == expected[c["code"]], c["key"])
        for row in c["indicators"]:
            require(row["is_mandatory"] is True and row["mandatory_basis"]["origin"] == "team",
                    "Consultant mandatory flag must follow the team decision")
            if row["collection"] == "matrix_transcription":
                row_paragraphs = {p for ref in row["source_refs"] if ref["source_id"] == "hr-matrix"
                                  for p in ref["paragraph_ids"]}
                require(not row_paragraphs & matrix_paragraphs, f"Duplicate matrix paragraph: {row['key']}")
                matrix_paragraphs.update(row_paragraphs)
    original_matrix = {p for p, t in sources["hr-matrix"]["paragraphs"].items() if t.strip().startswith("–")}
    require(matrix_paragraphs == original_matrix, f"Missing/extra matrix paragraphs: {matrix_paragraphs ^ original_matrix}")
    # A group-level citation explains grouping; it cannot replace a checked requirement.
    py_leaf_rows = py["formal_requirements"] + [r for c in py["competencies"] for r in c["indicators"]]
    covered_py = {p for row in py_leaf_rows for ref in row["source_refs"] if ref["source_id"] == "py-di"
                  for p in ref["paragraph_ids"]}
    require({f"P{p}" for p in range(200, 210)} <= covered_py, "Python qualification requirements incomplete")
    require({f"P{p}" for p in range(97, 113)} <= covered_py, "Python technical knowledge incomplete")
    for c in py["competencies"]:
        require(c["rank"] is None and c["target_level_min"] is None and c["target_level_max"] is None,
                "Invented IT ranks/percentages")
        require(c["origin"] == "team" and c["interpretation_status"] == "proposed",
                "IT grouping falsely marked approved")
        for row in c["indicators"]:
            require(bool(row["mandatory_basis"]["rationale"]), "Missing mandatory basis")
            if c["code"] == "ENGLISH" or row["key"] == "py.di.P209":
                require(row["verification"] == "interview", "English/privacy requires interview")
            if row["key"] in {"py.posting.11", "py.posting.datalens"}:
                require(row["is_mandatory"] is False, "Posting advantage cannot be mandatory")
    return row_count, keys


def check_fixtures(fixtures, profile_keys):
    require(fixtures["schema_version"] == PACKAGE_SCHEMA, "Unsupported fixture schema")
    synthetic = fixtures["synthetic_profile"]
    check_profile_format(synthetic, {})
    require(synthetic["is_synthetic"] is True, "Synthetic profile not isolated")
    require(synthetic["formal_requirements"][0]["params"]["min_months"] == 24, "Synthetic threshold changed")
    synthetic_keys = {r["key"] for r in all_rows(synthetic)}
    cases = fixtures["cases"]
    require(len({c["id"] for c in cases}) == len(cases), "Duplicate fixture id")
    for case in cases:
        require(case["is_synthetic"] is True and "synthetic" not in case, "Fixture is not marked synthetic")
        require(case["rule_key"] in profile_keys | synthetic_keys, "Fixture references absent rule")
        require(case["expected"]["result"] in {"met", "not_met", "unknown", "processing_error"}, case["id"])
        if case["expected"]["result"] == "processing_error":
            require(case["expected"]["write_formal_check"] is False, "Processing error persisted as check")
        for evidence in case["evidence"]:
            require(evidence["candidate_text_id"] == case["candidate_text_id"], "Evidence version mismatch")
            start, end, quote = evidence["start"], evidence["end"], evidence["quote"]
            require(isinstance(start, int) and isinstance(end, int) and 0 <= start < end,
                    "Invalid evidence offsets")
            require(case["text"][start:end] == quote and end - start == len(quote),
                    f"Evidence mismatch: {case['id']}")
    indexed = {c["id"]: c for c in cases}
    required = {"experience-absent": "unknown", "experience-three-years": "met", "experience-one-year": "not_met",
                "experience-placeholder": "unknown", "experience-overlap": "met", "experience-conflict": "unknown"}
    for key, result in required.items():
        require(indexed[key]["expected"]["result"] == result, f"Agreed expectation changed: {key}")
    require(indexed["experience-overlap"]["expected"]["months"] == 36, "Overlap fixture must expect 36 months")
    require(indexed["experience-absent"]["evidence"][0]["end"] == 37, "Base quote must span 37 code points")
    return len(cases)


def check_archive(path, manifest):
    require(hashlib.sha256(path.read_bytes()).hexdigest() == manifest["archive"]["sha256"], "Archive SHA-256 mismatch")
    with zipfile.ZipFile(path, metadata_encoding="utf-8") as archive:
        entries = {unicodedata.normalize("NFC", name): name for name in archive.namelist() if not name.startswith("__MACOSX/")}
        for source in manifest["documents"]:
            name = "Кадры/" + source["path"]
            require(name in entries, f"Source absent in archive: {name}")
            content = archive.read(entries[name])
            require(hashlib.sha256(content).hexdigest() == source["sha256"], f"Source SHA-256 mismatch: {name}")
            paragraphs = (paragraphs_from_docx(content) if name.endswith(".docx") else
                          {f"L{i}": line for i, line in enumerate(content.decode("utf-8-sig").splitlines(), 1) if line.strip()})
            require(paragraphs == source["paragraphs"], f"Source snapshot mismatch: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--card-schemas", action="store_true", help="Validate fixture cards/evidence with existing Pydantic schemas")
    args = parser.parse_args()
    manifest = read_json(ROOT / "sources.json")
    package = read_json(ROOT / "profiles.draft.json")
    fixtures = read_json(ROOT / "synthetic" / "cases.json")
    rows, keys = check_package(package, manifest)
    cases = check_fixtures(fixtures, keys)
    if args.archive:
        check_archive(args.archive, manifest)
    if args.card_schemas:
        from app.schemas.card import CandidateCard, Evidence
        for case in fixtures["cases"]:
            CandidateCard.model_validate(case["card"])
            for evidence in case["evidence"]:
                Evidence.model_validate(evidence)
        print("Fixture cards and evidence validated with existing product Pydantic schemas.")
    print(f"Verified {len(package['profiles'])} draft profiles, {rows} rows, {cases} synthetic expectations.")
    print("Archive bytes and source snapshots verified." if args.archive else "Archive not checked; use --archive to verify originals.")
    print("No model run, scoring implementation, DB import, or contract approval is implied.")


if __name__ == "__main__":
    main()
