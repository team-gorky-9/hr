"""Чтение и самопроверка контрольного набора fixtures/assessment/*.json.

Набор описывает, что должна выдать оценка на заданном очищенном тексте:
карточку, формальные проверки с цитатами, итог и причины отказа. Здесь проверяется,
что набор согласован сам с собой и с правилами app/assessment/verification.py:
- объекты читаются существующими схемами (CandidateCard, FormalCheckIn, CompetencyScoreIn);
- идентификаторы совпадают с uuid5 от ключей;
- вердикты по цитатам, понижение неподтверждённых выводов и итог совпадают с ожиданием;
- всё, что показано в макете как цитата, действительно стоит в тексте и подтверждено.

Совпадение с базой v1.0 проверяет отдельный тест с PostgreSQL.
"""
import json
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.assessment.verification import (
    EvidenceVerdict,
    TextVersion,
    assessment_refusal,
    check_evidence,
    competency_issue,
    confirm_result,
    formal_result,
    utf16_offsets,
)
from app.db.enums import CheckResult, RequirementStatus
from app.schemas.assessment import CompetencyScoreIn, FormalCheckIn
from app.schemas.card import CandidateCard

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "assessment"
ENFORCED_BY = {"schema", "db_v1", "stage_1"}


@dataclass
class CaseReport:
    case_id: str
    title: str
    enforced_by: str
    problems: list[str] = field(default_factory=list)
    observed: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


def load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def fixture_paths() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*.json"))


def texts_of(fixture: dict[str, Any]) -> dict[uuid.UUID, TextVersion]:
    """Все тексты набора в виде, который принимает check_evidence."""
    out = {}
    for item in fixture["texts"].values():
        candidate_id = uuid.UUID(fixture["candidates"][item["candidate"]]["id"])
        text_id = uuid.UUID(item["id"])
        out[text_id] = TextVersion(id=text_id, candidate_id=candidate_id, version=item["version"], text=item["text"])
    return out


def check_fixture(fixture: dict[str, Any]) -> tuple[list[str], list[CaseReport]]:
    """Вернуть (общие проблемы набора, отчёт по каждому случаю)."""
    problems = _check_identifiers(fixture) + _check_texts(fixture)
    return problems, [check_case(fixture, case) for case in fixture["cases"]]


def check_case(fixture: dict[str, Any], case: dict[str, Any]) -> CaseReport:
    report = CaseReport(case["id"], case["title"], case["enforced_by"])
    problems = report.problems
    expect = case["expect"]
    if case["enforced_by"] not in ENFORCED_BY:
        problems.append(f"enforced_by «{case['enforced_by']}» не из {sorted(ENFORCED_BY)}")

    texts = texts_of(fixture)
    candidate_id = uuid.UUID(fixture["candidates"][case["candidate"]]["id"])
    for key in case["texts"]:
        if key not in fixture["texts"]:
            problems.append(f"текст {key} не описан в наборе")
    assessed = fixture["texts"].get(case["assessed_text"])
    if assessed is None or assessed["candidate"] != case["candidate"]:
        problems.append("assessed_text должен быть текстом этого же кандидата")
        return report
    assessed_id = uuid.UUID(assessed["id"])

    # 1. Карточка читается схемой.
    card = None
    if case["card"] is not None:
        try:
            card = CandidateCard.model_validate(case["card"])
        except ValidationError as error:
            problems.append(f"карточка не читается схемой: {error.errors()[0]['msg']}")
        else:
            unknown_gaps = set(card.missing) - set(fixture["missing_vocabulary"])
            if unknown_gaps:
                problems.append(f"в missing значения вне словаря: {sorted(unknown_gaps)}")

    # 2. Можно ли вообще выдавать оценку.
    refusal = assessment_refusal(
        profile_status=RequirementStatus(case["profile_status"]), model_available=case["model_available"]
    )
    report.observed["refusal"] = refusal.value if refusal else None
    if report.observed["refusal"] != expect["refusal"]:
        problems.append(f"отказ: ожидали {expect['refusal']}, получили {report.observed['refusal']}")
    if not case["model_available"] and (case["card"] is not None or case["assessment"] is not None):
        problems.append("при недоступной модели не может быть карточки и оценки")

    assessment = case["assessment"]
    if assessment is None:
        _check_ui(case, fixture, verified_quotes=set(), report=report)
        return report

    # 3. Объекты оценки читаются схемами. Ошибка схемы ожидается только там, где это заявлено.
    parsed_checks, parsed_scores, schema_errors = [], [], []
    for index, item in enumerate(assessment["formal_checks"]):
        try:
            parsed_checks.append((item, FormalCheckIn.model_validate(item["check"])))
        except ValidationError:
            schema_errors.append(f"formal_checks[{index}].check")
    for index, item in enumerate(assessment["competency_scores"]):
        try:
            parsed_scores.append((item, CompetencyScoreIn.model_validate(item["score"])))
        except ValidationError:
            schema_errors.append(f"competency_scores[{index}].score")
    report.observed["schema_errors"] = schema_errors
    expected_schema_error = expect.get("schema_error")
    if schema_errors != ([expected_schema_error] if expected_schema_error else []):
        problems.append(f"ошибки схемы: ожидали {expected_schema_error}, получили {schema_errors}")
    if schema_errors or refusal is not None:
        # Оценки нет: ответ модели не прошёл схему или оценивать нельзя (черновой профиль).
        # Объект assessment в таком случае — то, что попытались бы сохранить; его разбирает тест БД.
        report.observed.setdefault("formal_result", None)
        _check_ui(case, fixture, verified_quotes=set(), report=report)
        return report

    if "formal_checks" not in expect or "competency_scores" not in expect:
        problems.append("оценка выдаётся, но в expect нет formal_checks / competency_scores")
        return report
    if len(expect["formal_checks"]) != len(parsed_checks) or len(expect["competency_scores"]) != len(parsed_scores):
        problems.append("число ожиданий в expect не совпадает с числом проверок в assessment")
        return report

    verified_quotes: set[tuple[str, int, int]] = set()

    def verdicts_for(evidence) -> list[EvidenceVerdict]:
        verdicts = []
        for item in evidence:
            verdict = check_evidence(item, texts=texts, candidate_id=candidate_id, assessed_text_id=assessed_id)
            verdicts.append(verdict)
            if verdict == EvidenceVerdict.OK:
                verified_quotes.add((str(item.candidate_text_id), item.start, item.end))
        return verdicts

    # 4. Формальные проверки: вердикты, понижение неподтверждённого вывода, пробел у unknown.
    effective: dict[str, CheckResult] = {}
    for index, ((item, check), expected) in enumerate(zip(parsed_checks, expect["formal_checks"], strict=True)):
        confirmation = confirm_result(check.result, verdicts_for(check.evidence))
        effective[item["requirement"]] = confirmation.effective
        got = {
            "verdicts": [v.value for v in confirmation.verdicts],
            "effective": confirmation.effective.value,
            "issue": confirmation.issue.value if confirmation.issue else None,
        }
        if got != expected:
            problems.append(f"formal_checks[{index}]: ожидали {expected}, получили {got}")
        if check.result == CheckResult.UNKNOWN:
            gap = item.get("gap")
            if not gap:
                problems.append(f"formal_checks[{index}]: у unknown должен быть указан пробел")
            elif gap not in fixture["missing_vocabulary"]:
                problems.append(f"formal_checks[{index}]: пробел «{gap}» вне словаря")
            elif card is not None and gap not in card.missing:
                problems.append(f"formal_checks[{index}]: пробела «{gap}» нет в card.missing")

    # 5. Компетенции: свидетельство без годной цитаты не считается подтверждённым.
    for index, ((item, score), expected) in enumerate(zip(parsed_scores, expect["competency_scores"], strict=True)):
        verdicts = verdicts_for(score.evidence)
        issue = competency_issue(score.level, verdicts)
        got = {"verdicts": [v.value for v in verdicts], "issue": issue.value if issue else None}
        if got != expected:
            problems.append(f"competency_scores[{index}]: ожидали {expected}, получили {got}")

    # 6. Итог по обязательным требованиям (только если оценку вообще можно выдавать).
    mandatory = [r["key"] for r in fixture["profile"]["formal_requirements"] if r["is_mandatory"]]
    observed_result = formal_result(effective, mandatory).value if refusal is None else None
    report.observed["formal_result"] = observed_result
    if observed_result != expect["formal_result"]:
        problems.append(f"formal_result: ожидали {expect['formal_result']}, получили {observed_result}")

    _check_ui(case, fixture, verified_quotes=verified_quotes, report=report)
    return report


def _check_ui(case, fixture, *, verified_quotes: set[tuple[str, int, int]], report: CaseReport) -> None:
    """Всё, что макет показывает как цитату, стоит в тексте и прошло проверку."""
    for item in case["ui"]["evidence"]:
        text = fixture["texts"][item["text"]]
        start, end = item["start"], item["end"]
        if text["text"][start:end] != item["quote"]:
            report.problems.append(f"ui: цитата «{item['quote'][:30]}» не на месте {start}:{end}")
        if utf16_offsets(text["text"], start, end) != (item["utf16_start"], item["utf16_end"]):
            report.problems.append(f"ui: неверные границы UTF-16 у «{item['quote'][:30]}»")
        if (text["id"], start, end) not in verified_quotes:
            report.problems.append(f"ui: показана непроверенная цитата «{item['quote'][:30]}»")


def _check_identifiers(fixture: dict[str, Any]) -> list[str]:
    namespace = uuid.UUID(fixture["uuid_namespace"])
    pairs: list[tuple[str, str]] = [(f"candidate/{code}", c["id"]) for code, c in fixture["candidates"].items()]
    pairs += [(key, t["id"]) for key, t in fixture["texts"].items()]
    profile = fixture["profile"]
    pairs.append((profile["key"], profile["id"]))
    pairs += [(r["key"], r["id"]) for r in profile["formal_requirements"]]
    for competency in profile["competencies"]:
        pairs.append((competency["key"], competency["id"]))
        pairs += [(i["key"], i["id"]) for i in competency["indicators"]]
    known_ids = {key: value for key, value in pairs}
    problems = [
        f"id у «{key}» не равен uuid5(namespace, key)"
        for key, value in pairs
        if str(uuid.uuid5(namespace, key)) != value
    ]
    for case in fixture["cases"]:
        for item in (case["assessment"] or {}).get("formal_checks", []):
            if known_ids.get(item["requirement"]) != item["check"]["requirement_id"]:
                problems.append(f"{case['id']}: requirement_id не совпадает с ключом {item['requirement']}")
        for item in (case["assessment"] or {}).get("competency_scores", []):
            if known_ids.get(item["competency"]) != item["score"]["competency_id"]:
                problems.append(f"{case['id']}: competency_id не совпадает с ключом {item['competency']}")
    return problems


def _check_texts(fixture: dict[str, Any]) -> list[str]:
    """Тексты в NFC (как после импорта) и принадлежат описанным кандидатам."""
    problems = []
    for key, item in fixture["texts"].items():
        if not unicodedata.is_normalized("NFC", item["text"]):
            problems.append(f"текст {key} не в NFC")
        if item["candidate"] not in fixture["candidates"]:
            problems.append(f"текст {key}: неизвестный кандидат {item['candidate']}")
    return problems
