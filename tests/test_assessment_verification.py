"""Правила доверия к выводу оценки — без базы и без модели."""
import uuid

import pytest

from app.assessment.verification import (
    ConfirmationIssue,
    EvidenceVerdict,
    Refusal,
    TextVersion,
    assessment_refusal,
    check_evidence,
    competency_issue,
    confirm_result,
    formal_result,
    utf16_offsets,
)
from app.db.enums import CheckResult, RequirementStatus
from app.schemas.card import Evidence

BASE = "Написал API-тесты для сервиса заявок."
CANDIDATE = uuid.uuid4()
OTHER_CANDIDATE = uuid.uuid4()


def text(candidate_id: uuid.UUID, version: int, value: str) -> TextVersion:
    return TextVersion(id=uuid.uuid4(), candidate_id=candidate_id, version=version, text=value)


def evidence(text_row: TextVersion, quote: str, start: int | None = None) -> Evidence:
    start = text_row.text.index(quote) if start is None else start
    return Evidence(candidate_text_id=text_row.id, quote=quote, start=start, end=start + len(quote))


@pytest.fixture
def texts():
    v1 = text(CANDIDATE, 1, BASE)
    v2 = text(CANDIDATE, 2, BASE + "\nОбщий коммерческий опыт — 3 года.")
    foreign = text(OTHER_CANDIDATE, 1, BASE)
    return {"v1": v1, "v2": v2, "foreign": foreign}


def verdict(texts, item: Evidence, assessed: TextVersion) -> EvidenceVerdict:
    by_id = {t.id: t for t in texts.values()}
    return check_evidence(item, texts=by_id, candidate_id=CANDIDATE, assessed_text_id=assessed.id)


def test_quote_on_its_place_in_assessed_text_is_ok(texts):
    assert verdict(texts, evidence(texts["v2"], BASE), texts["v2"]) == EvidenceVerdict.OK


def test_same_letters_in_old_version_are_not_enough(texts):
    # Побуквенно совпадает и стоит на месте, но оценка построена по версии 2.
    assert verdict(texts, evidence(texts["v1"], BASE), texts["v2"]) == EvidenceVerdict.STALE_TEXT_VERSION


def test_same_letters_in_other_candidate_text_are_foreign(texts):
    assert verdict(texts, evidence(texts["foreign"], BASE), texts["v1"]) == EvidenceVerdict.FOREIGN_TEXT


def test_shifted_quote_is_rejected(texts):
    shifted = Evidence(candidate_text_id=texts["v1"].id, quote=BASE, start=1, end=1 + len(BASE))
    assert verdict(texts, shifted, texts["v1"]) == EvidenceVerdict.QUOTE_NOT_AT_OFFSETS


def test_unknown_text_id(texts):
    lost = Evidence(candidate_text_id=uuid.uuid4(), quote=BASE, start=0, end=len(BASE))
    assert verdict(texts, lost, texts["v1"]) == EvidenceVerdict.UNKNOWN_TEXT


@pytest.mark.parametrize("claimed", [CheckResult.MET, CheckResult.NOT_MET])
def test_factual_claim_without_evidence_becomes_unknown(claimed):
    result = confirm_result(claimed, [])
    assert (result.effective, result.issue) == (CheckResult.UNKNOWN, ConfirmationIssue.MISSING_EVIDENCE)
    assert not result.confirmed


def test_factual_claim_with_only_bad_evidence_becomes_unknown():
    result = confirm_result(CheckResult.NOT_MET, [EvidenceVerdict.STALE_TEXT_VERSION])
    assert (result.effective, result.issue) == (CheckResult.UNKNOWN, ConfirmationIssue.INVALID_EVIDENCE)


def test_one_good_quote_is_enough():
    result = confirm_result(CheckResult.MET, [EvidenceVerdict.QUOTE_NOT_AT_OFFSETS, EvidenceVerdict.OK])
    assert (result.effective, result.issue) == (CheckResult.MET, None)


def test_unknown_needs_no_evidence():
    result = confirm_result(CheckResult.UNKNOWN, [])
    assert (result.effective, result.issue) == (CheckResult.UNKNOWN, None)


def test_competency_without_claim_has_nothing_to_confirm():
    assert competency_issue(None, []) is None
    assert competency_issue(100, []) == ConfirmationIssue.MISSING_EVIDENCE
    assert competency_issue(None, [EvidenceVerdict.FOREIGN_TEXT]) == ConfirmationIssue.INVALID_EVIDENCE
    assert competency_issue(None, [EvidenceVerdict.OK]) is None


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        ({"a": CheckResult.MET, "b": CheckResult.MET}, CheckResult.MET),
        ({"a": CheckResult.MET, "b": CheckResult.UNKNOWN}, CheckResult.UNKNOWN),
        ({"a": CheckResult.MET}, CheckResult.UNKNOWN),  # b не проверено
        ({"a": CheckResult.UNKNOWN, "b": CheckResult.NOT_MET}, CheckResult.NOT_MET),
    ],
)
def test_formal_result_over_mandatory(results, expected):
    assert formal_result(results, ["a", "b"]) == expected


def test_optional_requirement_does_not_change_formal_result():
    results = {"a": CheckResult.MET, "optional": CheckResult.NOT_MET}
    assert formal_result(results, ["a"]) == CheckResult.MET


def test_refusal_order_and_statuses():
    assert assessment_refusal(profile_status=RequirementStatus.APPROVED, model_available=True) is None
    assert assessment_refusal(profile_status=RequirementStatus.APPROVED, model_available=False) == Refusal.MODEL_UNAVAILABLE
    # Черновик не оцениваем, даже если модель доступна; модель тогда и не вызывается.
    assert assessment_refusal(profile_status=RequirementStatus.DRAFT, model_available=False) == Refusal.PROFILE_NOT_APPROVED
    assert assessment_refusal(profile_status=RequirementStatus.ARCHIVED, model_available=True) == Refusal.PROFILE_NOT_APPROVED


def test_utf16_offsets_shift_after_emoji():
    value = "🙂 " + BASE
    start = value.index(BASE)
    assert (start, start + len(BASE)) == (2, 39)
    assert utf16_offsets(value, start, start + len(BASE)) == (3, 40)
    assert utf16_offsets(BASE, 0, len(BASE)) == (0, 37)
