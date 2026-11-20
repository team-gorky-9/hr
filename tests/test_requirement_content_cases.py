"""The review CLI rejects unusable evidence and expectations outside an active stage.

These checks validate a manual oracle, not an evaluator or a model's answers.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.verify_requirement_profiles import ROOT, read_json


class RequirementContentCasesTests(unittest.TestCase):
    def setUp(self):
        package = read_json(ROOT / "profiles.draft.json")
        self.cases = {
            "schema_version": "requirement-content-cases/0.1",
            "profile_versions": {p["position_code"]: p["version"] for p in package["profiles"]},
            "cases": [{
                "id": "practice", "is_synthetic": True,
                "position_code": "python-dev", "rule_key": "py.di.P106",
                "check_stage": "screening", "basis": "resume",
                "text": "Разрабатывал ETL на Python и pandas.",
                "evidence": [{"quote": "Python и pandas", "start": 20, "end": 35}],
                "expected": {"result": "met", "included_in_screening": True,
                             "rationale": "Практика языка и библиотеки подтверждена."},
            }],
        }

    def run_cli(self, data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cases.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return subprocess.run(
                [sys.executable, "-X", "utf8", "-m", "scripts.verify_requirement_profiles", "--content-cases", str(path)],
                cwd=ROOT.parents[1], text=True, encoding="utf-8", capture_output=True,
            )

    def assert_rejected(self, data, reason):
        result = self.run_cli(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(reason, result.stderr)

    def test_valid_addressed_oracle_is_accepted(self):
        result = self.run_cli(self.cases)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 content expectations", result.stdout)

    def test_stale_quote_offset_is_rejected(self):
        self.cases["cases"][0]["evidence"][0]["start"] = 18
        self.assert_rejected(self.cases, "Content evidence mismatch")

    def test_unknown_target_is_rejected(self):
        self.cases["cases"][0]["rule_key"] = "py.absent"
        self.assert_rejected(self.cases, "Unknown content target")

    def test_excluded_row_cannot_have_a_screening_result(self):
        case = self.cases["cases"][0]
        case.update(position_code="hr-consultant", rule_key="hr.DK.19")
        case["expected"]["included_in_screening"] = False
        self.assert_rejected(self.cases, "Inactive target must be not_evaluated")

    def test_interview_row_is_not_a_screening_denominator_unit(self):
        case = self.cases["cases"][0]
        case["rule_key"] = "py.di.P99"
        case["expected"]["result"] = "not_evaluated"
        self.assert_rejected(self.cases, "Incorrect screening membership")

    def test_positive_outcome_without_evidence_is_rejected(self):
        self.cases["cases"][0]["evidence"] = []
        self.assert_rejected(self.cases, "Content outcome requires evidence")

    def test_wrong_profile_version_is_rejected(self):
        self.cases["profile_versions"]["python-dev"] += 1
        self.assert_rejected(self.cases, "Content profile versions mismatch")

    def test_duplicate_case_id_is_rejected(self):
        self.cases["cases"].append(deepcopy(self.cases["cases"][0]))
        self.assert_rejected(self.cases, "Duplicate content case id")


if __name__ == "__main__":
    unittest.main()
