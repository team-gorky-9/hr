"""Integrity checks for review artifacts; these do not test a scoring model."""
from copy import deepcopy
import unittest

from scripts.verify_requirement_profiles import ROOT, check_fixtures, check_package, read_json


class RequirementProfileIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = read_json(ROOT / "sources.json")
        cls.package = read_json(ROOT / "profiles.draft.json")
        cls.fixtures = read_json(ROOT / "synthetic/cases.json")
        _, cls.keys = check_package(cls.package, cls.sources)

    def test_altered_source_quote_is_rejected(self):
        changed = deepcopy(self.package)
        changed["profiles"][0]["formal_requirements"][0]["source_refs"][0]["quote"] = "Требуется десять лет стажа"
        with self.assertRaisesRegex(ValueError, "Quote does not match"):
            check_package(changed, self.sources)

    def test_mandatory_must_be_boolean_not_truthy_text(self):
        changed = deepcopy(self.package)
        changed["profiles"][1]["competencies"][0]["indicators"][0]["is_mandatory"] = "false"
        with self.assertRaisesRegex(ValueError, "is_mandatory must be boolean"):
            check_package(changed, self.sources)

    def test_legacy_verification_value_is_rejected(self):
        changed = deepcopy(self.package)
        changed["profiles"][0]["formal_requirements"][0]["verification"] = "document_required"
        with self.assertRaisesRegex(ValueError, "Invalid verification"):
            check_package(changed, self.sources)

    def test_team_group_requires_rationale(self):
        changed = deepcopy(self.package)
        changed["profiles"][1]["competencies"][0]["rationale"] = ""
        with self.assertRaisesRegex(ValueError, "Missing origin rationale"):
            check_package(changed, self.sources)

    def test_profile_must_declare_its_sources(self):
        changed = deepcopy(self.package)
        changed["profiles"][1]["sources"] = []
        with self.assertRaisesRegex(ValueError, "Profile source list"):
            check_package(changed, self.sources)

    def test_source_revision_cannot_be_invented(self):
        changed = deepcopy(self.package)
        changed["profiles"][1]["sources"] = [
            {"source_id": "py-di", "role": "job_description", "revision": "9.9"},
            {"source_id": "py-posting", "role": "vacancy_posting", "revision": None},
        ]
        with self.assertRaisesRegex(ValueError, "Source revision mismatch"):
            check_package(changed, self.sources)

    def test_missing_matrix_indicator_is_rejected(self):
        changed = deepcopy(self.package)
        changed["profiles"][0]["competencies"][0]["indicators"].pop(0)
        with self.assertRaisesRegex(ValueError, "matrix paragraphs"):
            check_package(changed, self.sources)

    def test_python_qualification_requires_a_leaf_row_not_only_group_reference(self):
        changed = deepcopy(self.package)
        work = changed["profiles"][1]["competencies"][-1]
        work["indicators"] = [r for r in work["indicators"] if r["key"] != "py.di.P202"]
        with self.assertRaisesRegex(ValueError, "qualification requirements incomplete"):
            check_package(changed, self.sources)

    def test_duplicate_matrix_indicator_cannot_be_counted_twice(self):
        changed = deepcopy(self.package)
        indicators = changed["profiles"][0]["competencies"][0]["indicators"]
        duplicate = deepcopy(indicators[0])
        duplicate["key"] = "hr.PAK.duplicate"
        indicators.append(duplicate)
        with self.assertRaisesRegex(ValueError, "Duplicate matrix paragraph"):
            check_package(changed, self.sources)

    def test_invented_python_percentages_are_rejected(self):
        changed = deepcopy(self.package)
        changed["profiles"][1]["competencies"][0]["target_level_min"] = 90
        with self.assertRaisesRegex(ValueError, "Invented IT"):
            check_package(changed, self.sources)

    def test_wrong_evidence_offset_is_rejected(self):
        changed = deepcopy(self.fixtures)
        changed["cases"][0]["evidence"][0]["end"] -= 1
        with self.assertRaisesRegex(ValueError, "Evidence mismatch"):
            check_fixtures(changed, self.keys)

    def test_evidence_from_another_text_version_is_rejected(self):
        changed = deepcopy(self.fixtures)
        changed["cases"][0]["evidence"][0]["candidate_text_id"] = changed["cases"][1]["candidate_text_id"]
        with self.assertRaisesRegex(ValueError, "version mismatch"):
            check_fixtures(changed, self.keys)

    def test_processing_error_cannot_be_saved_as_formal_check(self):
        changed = deepcopy(self.fixtures)
        next(c for c in changed["cases"] if c["id"] == "rule-unknown-key")["expected"]["write_formal_check"] = True
        with self.assertRaisesRegex(ValueError, "Processing error persisted"):
            check_fixtures(changed, self.keys)

    def test_unsupported_rule_cannot_create_a_partial_assessment(self):
        changed = deepcopy(self.fixtures)
        next(c for c in changed["cases"] if c["id"] == "rule-unknown-key")["expected"]["write_assessment"] = True
        with self.assertRaisesRegex(ValueError, "Processing error must refuse the whole assessment"):
            check_fixtures(changed, self.keys)

    def test_card_with_no_declared_role_is_not_an_extraction_oracle(self):
        changed = deepcopy(self.fixtures)
        changed["cases"][0].pop("card_role", None)
        with self.assertRaisesRegex(ValueError, "Missing card role"):
            check_fixtures(changed, self.keys)

    def test_removing_supported_education_from_card_is_detected(self):
        changed = deepcopy(self.fixtures)
        case = next(c for c in changed["cases"] if c["id"] == "hr-field-no")
        case["card"] = {"pii_hidden": True}
        case["card_role"] = "expected_available_fields"
        case["card_evidence"] = [{"path": "/education/0/field", "evidence_indexes": [0]}]
        with self.assertRaisesRegex(ValueError, "Card evidence points to missing field"):
            check_fixtures(changed, self.keys)

    def test_empty_course_list_cannot_replace_explicit_negative_evidence(self):
        changed = deepcopy(self.fixtures)
        case = next(c for c in changed["cases"] if c["id"] == "hr-field-no")
        case["expected"]["requires_text_evidence"] = True
        case["expected"]["formal_evidence_indexes"] = []
        with self.assertRaisesRegex(ValueError, "Explicit text evidence is required"):
            check_fixtures(changed, self.keys)

    def test_changed_text_cannot_keep_stale_content_hash(self):
        changed = deepcopy(self.fixtures)
        case = changed["cases"][0]
        case["text_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Text hash mismatch"):
            check_fixtures(changed, self.keys)


if __name__ == "__main__":
    unittest.main()
