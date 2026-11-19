"""Контрольный набор против базы v1.0: что функции доступа уже обеспечивают, а что нет.

Каждый случай с expect.db_v1.save_assessment ≠ not_called проводится через настоящие
функции доступа: исходный документ → кандидат → версии очищенного текста → профиль →
карточка → save_assessment. UUID набора заменяются на выданные базой.

Тест фиксирует факт, а не желание: для случаев stage_1 база v1.0 сохраняет оценку,
хотя этап 1 должен её не выдавать или понизить вывод. Если базу научат отклонять
такие оценки, этот тест упадёт — и ожидание в наборе нужно будет перевести в db_v1.
"""
import uuid

import pytest
from sqlalchemy import select

from app.assessment.fixtures import FIXTURES_DIR, load
from app.assessment.verification import formal_result
from app.db import repository as repo
from app.db.enums import (
    Channel,
    CheckResult,
    CompetencyRank,
    DocumentKind,
    FileFormat,
    FormalRequirementKind,
    RequirementStatus,
)
from app.db.models import (
    Competency,
    CompetencyIndicator,
    FormalRequirement,
    Position,
    RequirementProfile,
)
from app.db.repository import EvidenceError
from app.schemas.assessment import CompetencyScoreIn, FormalCheckIn
from app.schemas.card import CandidateCard

FIXTURE = load(FIXTURES_DIR / "py-9001.json")
DB_CASES = [c for c in FIXTURE["cases"] if c["expect"]["db_v1"]["save_assessment"] != "not_called"]


def _load_texts(session, case) -> dict[str, uuid.UUID]:
    """Создать кандидатов и версии их текстов. Вернуть {uuid текста в наборе: uuid в базе}."""
    ids: dict[str, uuid.UUID] = {}
    candidates: dict[str, uuid.UUID] = {}
    keys = sorted(case["texts"], key=lambda k: FIXTURE["texts"][k]["version"])
    for key in keys:
        item = FIXTURE["texts"][key]
        code = item["candidate"]
        if code not in candidates:
            assert item["version"] == 1, "первая версия текста кандидата создаётся вместе с ним"
            document, _ = repo.add_source_document(
                session,
                kind=DocumentKind.RESUME,
                channel=Channel.HH_RU,
                file_format=FileFormat.TXT,
                original_path=f"Синтетика/{case['id']}/{code}.txt",
                raw_text=f"{code} (синтетика, {case['id']})\n{item['text']}",
            )
            candidate = repo.create_candidate(
                session, code=code, source_document_id=document.id,
                redacted_text=item["text"], redaction_method="fixture",
            )
            candidates[code] = candidate.id
            ids[item["id"]] = repo.get_current_text(session, candidate.id).id
        else:
            row = repo.add_candidate_text(session, candidates[code], text=item["text"], redaction_method="fixture")
            assert row.version == item["version"]
            ids[item["id"]] = row.id
    return ids | {"candidate": candidates[case["candidate"]]}


def _load_profile(session, status: str) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """Учебный профиль из набора. Вернуть (id профиля, {uuid в наборе: uuid в базе})."""
    spec = FIXTURE["profile"]
    position = session.scalar(select(Position).where(Position.code == spec["position_code"]))
    profile = RequirementProfile(position_id=position.id, version=900, created_by="fixture",
                                 status=RequirementStatus(status), note=spec["synthetic_role"])
    mapping: dict[str, FormalRequirement | Competency] = {}
    for order, item in enumerate(spec["formal_requirements"]):
        requirement = FormalRequirement(kind=FormalRequirementKind(item["kind"]), description=item["description"],
                                        params=item["params"], is_mandatory=item["is_mandatory"], sort_order=order)
        profile.formal_requirements.append(requirement)
        mapping[item["id"]] = requirement
    for order, item in enumerate(spec["competencies"]):
        competency = Competency(rank=CompetencyRank(item["rank"]), code=item["code"], name=item["name"],
                                target_level_min=item["target_level_min"], target_level_max=item["target_level_max"],
                                sort_order=order)
        competency.indicators = [CompetencyIndicator(text=i["text"], sort_order=n) for n, i in enumerate(item["indicators"])]
        profile.competencies.append(competency)
        mapping[item["id"]] = competency
    session.add(profile)
    session.flush()
    return profile.id, {key: row.id for key, row in mapping.items()}


def _remap(obj: dict, ids: dict[str, uuid.UUID]) -> dict:
    """Заменить UUID набора на UUID базы в проверке и её цитатах."""
    out = dict(obj)
    for field in ("requirement_id", "competency_id"):
        if field in out:
            out[field] = ids[out[field]]
    out["evidence"] = [{**e, "candidate_text_id": ids.get(e["candidate_text_id"], uuid.uuid4())} for e in obj["evidence"]]
    return out


@pytest.mark.parametrize("case", DB_CASES, ids=[c["id"] for c in DB_CASES])
def test_case_against_database_v1(session, case):
    expected = case["expect"]["db_v1"]
    ids = _load_texts(session, case)
    profile_id, profile_ids = _load_profile(session, case["profile_status"])
    ids |= profile_ids

    assessed_text_id = ids[FIXTURE["texts"][case["assessed_text"]]["id"]]
    card = repo.add_candidate_card(session, ids["candidate"], CandidateCard.model_validate(case["card"]),
                                   extractor="fixture", candidate_text_id=assessed_text_id)
    checks = [FormalCheckIn.model_validate(_remap(i["check"], ids)) for i in case["assessment"]["formal_checks"]]
    scores = [CompetencyScoreIn.model_validate(_remap(i["score"], ids)) for i in case["assessment"]["competency_scores"]]

    def save():
        return repo.save_assessment(session, candidate_id=ids["candidate"], profile_id=profile_id, card_id=card.id,
                                    model="fixture", formal_checks=checks, competency_scores=scores)

    if expected["save_assessment"] == "rejected":
        with pytest.raises(EvidenceError):
            save()
        return

    assessment = save()
    assert assessment.formal_result == CheckResult(expected["formal_result"])
    # Итог БД совпадает с чистой функцией на тех же (не перепроверенных) выводах модели.
    mandatory = [ids[r["id"]] for r in FIXTURE["profile"]["formal_requirements"] if r["is_mandatory"]]
    assert formal_result({c.requirement_id: c.result for c in checks}, mandatory) == assessment.formal_result


def test_every_db_case_is_covered():
    """В наборе нет случая, ожидание которого для БД не описано."""
    allowed = {"accepted", "rejected", "not_called"}
    assert all(c["expect"]["db_v1"]["save_assessment"] in allowed for c in FIXTURE["cases"])
