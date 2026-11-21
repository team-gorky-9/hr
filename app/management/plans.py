"""4C: плановый снимок потребностей и возможное покрытие на одну дату.

Пример. Две потребности: П-1 «экономист» (1 место) и П-2 «аналитик» (1 место). Одна запись с
подтверждённой личностью (person_ref) и доступным контактом, HR отметил её confirmed для обеих.
Номинально у обеих есть подтверждённый кандидат (2 из 2), но один человек на дату закрывает
только одно место: независимое покрытие 1 из 2, предупреждение «концентрация» называет обе
потребности. Если добавить второго подтверждённого человека, подходящего только П-1, максимальное
паросочетание даёт 2 из 2 (первый человек уходит на П-2), а жадный выбор «первый подходящий на П-1»
дал бы 1. Ожидаемый диплом (expected) виден отдельной строкой и confirmed не увеличивает.
Конкретное паросочетание не возвращается: оно одно из возможных и не является назначением."""
import hashlib
import json
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.db.models import PlanSnapshot, User
from app.management.schemas import PlanIn, PlanOut, PlanSummaryOut

READINESS = ("confirmed", "expected", "similarity", "unknown")
ALGORITHM = "max-bipartite-matching/augmenting-paths-v1"


def ref_key(ref) -> tuple[str, str]:
    return (ref.system, ref.id)


def maximum_matching(slots: list, edges: dict) -> int:
    """Максимальное паросочетание «место потребности — человек» увеличивающими путями (Кун).
    Места и рёбра упорядочены стабильными ключами, поэтому результат детерминирован. Возвращает
    размер; на графах в десятки вершин это мгновенно."""
    owner: dict = {}  # человек → место

    def augment(slot, visited) -> bool:
        for person in edges.get(slot, ()):
            if person in visited:
                continue
            visited.add(person)
            if person not in owner or augment(owner[person], visited):
                owner[person] = slot
                return True
        return False

    return sum(augment(slot, set()) for slot in slots)


def compute(body: PlanIn) -> dict:
    people = {ref_key(p.record_ref): p for p in body.people}
    by_need: dict = defaultdict(lambda: {r: [] for r in READINESS})
    for match in body.matches:
        by_need[match.need_key][match.readiness].append(ref_key(match.record_ref))

    # Подтверждённое ребро: confirmed + подтверждённая личность + доступный контакт. Узел — человек.
    eligible: dict = {}
    for need in body.needs:
        persons = set()
        for record in by_need[need.key]["confirmed"]:
            person = people[record]
            if person.person_ref is not None and person.contact_available:
                persons.add(ref_key(person.person_ref))
        eligible[need.key] = sorted(persons)

    slots, edges = [], {}
    for need in sorted(body.needs, key=lambda n: n.key):
        for index in range(need.quantity):
            slot = (need.key, index)
            slots.append(slot)
            edges[slot] = eligible[need.key]
    independent_total = maximum_matching(slots, edges)

    degree = defaultdict(list)
    for need_key, persons in eligible.items():
        for person in persons:
            degree[person].append(need_key)
    concentrated = {person: sorted(needs) for person, needs in degree.items() if len(needs) > 1}

    # Независимое покрытие — свойство всего набора потребностей: максимальных паросочетаний может быть
    # несколько, и распределение мест между потребностями у них разное. Поэтому итог — размер общего
    # паросочетания, а по потребности — только верхняя граница min(quantity, подтверждённых людей).
    needs_out, warnings = [], []
    for need in body.needs:
        groups = by_need[need.key]
        confirmed_records = groups["confirmed"]
        unresolved = [r for r in confirmed_records if people[r].person_ref is None]
        no_contact = [r for r in confirmed_records
                      if people[r].person_ref is not None and not people[r].contact_available]
        shared = [p for p in eligible[need.key] if p in concentrated]
        needs_out.append({
            "key": need.key, "department_key": need.department_key, "position_code": need.position_code,
            "quantity": need.quantity, "source_reference": need.source_reference,
            "records_by_readiness": {r: len(groups[r]) for r in READINESS},
            "confirmed_persons": len(eligible[need.key]),
            "nominally_covered": bool(eligible[need.key]),
            "upper_bound_covered": min(need.quantity, len(eligible[need.key])),
            "unresolved_records": len(unresolved),
            "contact_unavailable_records": len(no_contact),
            "shared_confirmed_persons": len(shared),
            "detail": {
                "eligible_person_refs": [{"system": s, "id": i} for s, i in eligible[need.key]],
                "unresolved_record_refs": [{"system": s, "id": i} for s, i in unresolved],
            },
        })
        if unresolved:
            warnings.append({"code": "unresolved_identity", "need_key": need.key, "count": len(unresolved),
                             "message": "Записи без подтверждённой личности не считаются подтверждёнными людьми"})
        if no_contact:
            warnings.append({"code": "contact_unavailable", "need_key": need.key, "count": len(no_contact),
                             "message": "Подтверждённые без доступного контакта не входят в покрытие"})
        if groups["expected"]:
            warnings.append({"code": "expected_not_counted", "need_key": need.key, "count": len(groups["expected"]),
                             "message": "Ожидаемые к дате (например, диплом) показаны отдельно и не подтверждают покрытие"})
    for person, need_keys in sorted(concentrated.items()):
        warnings.append({"code": "concentration", "need_keys": need_keys,
                         "message": "Один подтверждённый человек указан для нескольких потребностей; "
                                    "на дату он закрывает только одно место"})

    total_slots = sum(n.quantity for n in body.needs)
    return {
        "algorithm": ALGORITHM,
        "totals": {
            "needs": len(body.needs), "places": total_slots,
            "nominally_covered_needs": sum(1 for n in needs_out if n["nominally_covered"]),
            "independent_covered_places": independent_total,
            "confirmed_persons": len({p for persons in eligible.values() for p in persons}),
            "concentrated_persons": len(concentrated),
            "unresolved_records": sum(n["unresolved_records"] for n in needs_out),
        },
        "needs": needs_out,
        "warnings": warnings,
        "note": ("Возможное покрытие на дату по заключениям HR: независимое — максимальное число мест, которые "
                 "подтверждённые люди с доступным контактом могут закрыть одновременно, по одному месту на "
                 "человека. Это не назначение и не рекомендация конкретного человека."),
    }


def fingerprint(body: PlanIn) -> str:
    data = body.model_dump(mode="json")
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def create_plan(session: Session, body: PlanIn, user: User) -> PlanOut:
    row = PlanSnapshot(id=uuid.uuid4(), target_date=body.target_date, scope_label=body.scope_label,
                       coverage_note=body.coverage_note, input=body.model_dump(mode="json"),
                       input_sha256=fingerprint(body), result=compute(body), created_by_user_id=user.id,
                       created_at=datetime.now(UTC))
    session.add(row)
    session.commit()
    session.refresh(row)
    return plan_out(session, row)


def get_plan(session: Session, plan_id: uuid.UUID) -> PlanSnapshot:
    row = session.get(PlanSnapshot, plan_id)
    if row is None:
        raise ApiError(404, "PLAN_NOT_FOUND", "Плановый снимок не найден", {"plan_id": str(plan_id)})
    return row


def plan_out(session: Session, row: PlanSnapshot) -> PlanOut:
    author = session.get(User, row.created_by_user_id) if row.created_by_user_id else None
    return PlanOut(id=row.id, target_date=row.target_date, scope_label=row.scope_label,
                   coverage_note=row.coverage_note, created_at=row.created_at,
                   created_by=author.login if author else None, input_sha256=row.input_sha256,
                   input=row.input, result=row.result)


def summary_out(row: PlanSnapshot) -> PlanSummaryOut:
    """Без имён, record_ref, person_ref, оснований HR и ссылок на первичные документы потребностей."""
    hidden = {"detail", "source_reference"}
    needs = [{k: v for k, v in need.items() if k not in hidden} for need in row.result["needs"]]
    return PlanSummaryOut(id=row.id, target_date=row.target_date, scope_label=row.scope_label,
                          coverage_note=row.coverage_note, created_at=row.created_at,
                          totals=row.result["totals"] | {"algorithm": row.result["algorithm"]},
                          needs=needs, warnings=row.result["warnings"])
