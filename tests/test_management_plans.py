"""4C: плановый снимок потребностей и возможное покрытие (wave-4-reporting-stage-1)."""
import itertools
import uuid

from app.management.plans import maximum_matching
from tests.posting_helpers import posting_registry  # noqa: F401 (фикстура клиента)
from tests.test_api import client  # noqa: F401 (фикстура)

PATH = "/api/v1/management/plans"
HR = {"X-User-Login": "hr_demo"}


def need(key, quantity=1):
    return {"key": key, "department_key": "economy", "position_code": "economist-training", "quantity": quantity,
            "source_reference": f"Учебная заявка {key}"}


def person(record, person_id=None, contact=True, label=None):
    return {"person_ref": {"system": "legacy-hr", "id": person_id} if person_id else None,
            "record_ref": {"system": "legacy-hr", "id": record}, "label": label or f"Учебная запись {record}",
            "contact_available": contact}


def match(need_key, record, readiness="confirmed"):
    return {"need_key": need_key, "record_ref": {"system": "legacy-hr", "id": record}, "readiness": readiness,
            "basis": f"Оценка HR по {need_key} (учебно)"}


def plan(needs, people, matches):
    return {"target_date": "2026-12-01", "scope_label": "Учебный план отдела экономики", "needs": needs,
            "people": people, "matches": matches, "coverage_note": "Учебный пакет HR, не полный кадровый учёт"}


def test_matching_is_maximum_not_greedy():
    # Жадно: место n1 берёт A, n2 остаётся без людей → 1. Максимум: A → n2, B → n1 → 2.
    slots = [("n1", 0), ("n2", 0)]
    assert maximum_matching(slots, {("n1", 0): ["A", "B"], ("n2", 0): ["A"]}) == 2
    assert maximum_matching(slots, {("n1", 0): ["A"], ("n2", 0): ["A"]}) == 1
    # Совпадает с полным перебором на маленьком графе.
    edges = {("n1", 0): ["A", "B"], ("n1", 1): ["A", "B"], ("n2", 0): ["B", "C"], ("n3", 0): ["C"]}
    best = max(sum(1 for slot, p in zip(edges, choice) if p in edges[slot] and choice.count(p) == 1)
               for choice in itertools.product(["A", "B", "C", None], repeat=4))
    assert maximum_matching(list(edges), edges) == best == 3


def test_one_person_for_two_needs_then_second_person(client):  # noqa: F811
    first = client.post(PATH, headers=HR, json=plan(
        [need("n1"), need("n2")], [person("r-a", "p-a")], [match("n1", "r-a"), match("n2", "r-a")]))
    assert first.status_code == 201, first.text
    totals = first.json()["result"]["totals"]
    assert (totals["nominally_covered_needs"], totals["independent_covered_places"], totals["places"]) == (2, 1, 2)
    assert totals["concentrated_persons"] == 1
    assert [w["need_keys"] for w in first.json()["result"]["warnings"] if w["code"] == "concentration"] == [["n1", "n2"]]

    second = client.post(PATH, headers=HR, json=plan(
        [need("n1"), need("n2")], [person("r-a", "p-a"), person("r-b", "p-b"), person("r-c", "p-c")],
        [match("n1", "r-a"), match("n2", "r-a"), match("n1", "r-b"), match("n2", "r-c", "expected")])).json()
    assert second["result"]["totals"]["independent_covered_places"] == 2
    n2 = next(n for n in second["result"]["needs"] if n["key"] == "n2")
    assert n2["records_by_readiness"] == {"confirmed": 1, "expected": 1, "similarity": 0, "unknown": 0}
    assert n2["confirmed_persons"] == 1  # ожидаемый диплом не увеличивает confirmed
    assert [(w["need_key"], w["count"]) for w in second["result"]["warnings"]
            if w["code"] == "expected_not_counted"] == [("n2", 1)]

    # Снимок неизменяем и перечитывается; первый не изменился после второго.
    again = client.get(f"{PATH}/{first.json()['id']}", headers=HR).json()
    assert again == first.json()
    assert client.patch(f"{PATH}/{first.json()['id']}", headers=HR, json={}).status_code == 405


def test_identity_contact_and_quantity(client):  # noqa: F811
    body = plan(
        [need("n1", quantity=3)],
        [person("r-1", "p-1"), person("r-2", "p-1"),           # две записи одного человека
         person("r-3"),                                         # личность не установлена
         person("r-4", "p-4", contact=False)],                  # контакт недоступен
        [match("n1", "r-1"), match("n1", "r-2"), match("n1", "r-3"), match("n1", "r-4")])
    result = client.post(PATH, headers=HR, json=body).json()["result"]
    [n1] = result["needs"]
    assert (n1["records_by_readiness"]["confirmed"], n1["confirmed_persons"], n1["unresolved_records"],
            n1["contact_unavailable_records"]) == (4, 1, 1, 1)
    assert result["totals"]["independent_covered_places"] == 1 and result["totals"]["places"] == 3
    assert {w["code"] for w in result["warnings"]} == {"unresolved_identity", "contact_unavailable"}


def test_summary_hides_people_and_bases(client):  # noqa: F811
    created = client.post(PATH, headers=HR, json=plan(
        [need("n1")], [person("r-secret", "p-secret", label="Иванова Мария")], [match("n1", "r-secret")])).json()
    summary = client.get(f"{PATH}/{created['id']}/summary", headers=HR)
    assert summary.status_code == 200
    text = summary.text
    assert "Иванова" not in text and "r-secret" not in text and "p-secret" not in text
    assert "Оценка HR" not in text and "Учебная заявка" not in text
    body = summary.json()
    assert body["totals"]["independent_covered_places"] == 1 and body["needs"][0]["confirmed_persons"] == 1
    assert "Иванова" in client.get(f"{PATH}/{created['id']}", headers=HR).text  # полная версия — только HR/admin


def test_rejections(client):  # noqa: F811
    good = plan([need("n1")], [person("r-1", "p-1")], [match("n1", "r-1")])
    assert client.post(PATH, headers={"X-User-Login": "dept_demo"}, json=good).status_code == 403
    assert client.get(f"{PATH}/{uuid.uuid4()}/summary", headers={"X-User-Login": "dept_demo"}).status_code == 403
    assert client.get(f"{PATH}/{uuid.uuid4()}", headers=HR).json()["error"]["code"] == "PLAN_NOT_FOUND"
    for bad in (plan([need("n1")], [person("r-1", "p-1")], [match("n9", "r-1")]),          # чужая потребность
                plan([need("n1")], [person("r-1", "p-1")], [match("n1", "r-9")]),          # чужая запись
                plan([need("n1"), need("n1")], [], []),                                    # повтор ключа
                plan([need("n1", quantity=0)], [], []),
                plan([need("n1")], [person("r-1"), person("r-1")], []),
                plan([need("n1")], [person("r-1", "p-1")], [match("n1", "r-1", "maybe")]),
                plan([], [], [])):
        assert client.post(PATH, headers=HR, json=bad).status_code == 422
