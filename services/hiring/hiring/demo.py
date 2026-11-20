"""Training walkthrough through HTTP only, on fixtures/wave-1 (AUTH_MODE=fixture, SELECTION_SOURCE=fixture).

    uv run python -m hiring.demo                       # against http://127.0.0.1:8103
    uv run python -m hiring.demo --base-url http://localhost:8103

Path (wave-1-stage-1): HR creates Marina's case → requests a checklist of two items → the candidate
uploads two files → HR returns one with a reason → the candidate uploads a corrected version → HR
accepts it, ready → start with an employment basis → HR records the Workforce assignment manually →
correction of the start date and the HR decision to keep the existing assignment (corrections.json).
The second training candidate withdraws before start. All names and ids are synthetic.

A second run finds Marina's active case (one case per application_ref) and prints its state."""
import argparse
import json
import sys
import uuid
from pathlib import Path

import httpx

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures/wave-1"
EXTRA = Path(__file__).resolve().parents[1] / "fixtures/extra-selections.json"
CANDIDATE_ID = "00000000-0000-4000-8000-000000000105"
EMPLOYEE_ID = "00000000-0000-4000-8000-000000000201"  # events.json assignment.registered
ASSIGNMENT_ID = "00000000-0000-4000-8000-000000000302"
CHECKLIST = [
    {"key": "passport", "title": "Копия паспорта (учебная)", "required": True},
    {"key": "education", "title": "Документ об образовании (учебный)", "required": True},
]


def pdf(label: str) -> bytes:
    """A tiny synthetic PDF; the service checks the signature, not the content."""
    return (b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n% synthetic: " + label.encode() +
            b"\ntrailer<</Root 1 0 R>>\n%%EOF\n")


class Client:
    def __init__(self, base_url: str):
        self.http = httpx.Client(base_url=base_url.rstrip("/"), timeout=10)

    def call(self, login: str, method: str, path: str, expect: int | tuple = (200, 201), **kwargs):
        headers = {"Authorization": f"Bearer fixture:{login}"}
        if method == "POST":
            headers["Idempotency-Key"] = str(uuid.uuid4())
        response = self.http.request(method, f"/api/v1{path}", headers=headers, **kwargs)
        expected = expect if isinstance(expect, tuple) else (expect,)
        if response.status_code not in expected:
            raise SystemExit(f"{method} {path} as {login}: {response.status_code} {response.text}")
        return response.json() if response.headers.get("content-type", "").startswith("application/json") else None

    def upload(self, login: str, kind: str, name: str, content: bytes) -> dict:
        return self.call(login, "POST", "/documents", 201, data={"kind": kind},
                         files={"file": (name, content, "application/pdf")})


def say(step: str, detail: str = "") -> None:
    print(f"• {step}" + (f" — {detail}" if detail else ""), flush=True)


def item(case: dict, key: str) -> dict:
    return next(entry for entry in case["checklist"] if entry["key"] == key)


def run(base_url: str) -> int:
    api = Client(base_url)
    health = api.http.get("/health").json()
    say("health", json.dumps(health, ensure_ascii=False))
    selection = json.loads((FIXTURES / "selection.json").read_text(encoding="utf-8"))
    second = json.loads(EXTRA.read_text(encoding="utf-8"))["selections"][0]

    case = api.call("hr", "POST", "/cases", json={
        "selection": selection, "candidate_actor_id": CANDIDATE_ID,
        "identity_basis": "Учебная проверка личности по fixtures/wave-1/actors.json",
        "checklist": CHECKLIST, "checklist_version": "training-1",
    })
    if case["status"] != "preparing":
        say("дело Марины уже есть", f"status={case['status']}, workforce_status={case['workforce_status']}")
        print(json.dumps(case, ensure_ascii=False, indent=2))
        return 0
    say("HR создал дело Марины", f"{case['id']} status={case['status']} items={len(case['checklist'])}")

    mine = api.call("candidate", "GET", "/cases")
    say("кандидат видит только своё дело", f"{[c['id'] for c in mine['items']]}")
    api.call("hr_other", "GET", f"/cases/{case['id']}", 404)
    say("HR другой организации получает 404")

    case = api.call("hr", "POST", f"/cases/{case['id']}/request-documents", json={
        "expected_revision": case["revision"], "message": "Загрузите паспорт и документ об образовании"})
    say("HR запросил комплект", f"status={case['status']}")

    passport = api.upload("candidate", "hiring_application", "passport.pdf", pdf("passport v1"))
    education = api.upload("candidate", "hiring_evidence", "diploma.pdf", pdf("diploma v1, blurred"))
    for key, document in (("passport", passport), ("education", education)):
        entry = item(case, key)
        api.call("candidate", "POST", f"/cases/{case['id']}/items/{entry['id']}/submit", json={
            "expected_revision": entry["revision"], "document_id": document["id"]})
    case = api.call("hr", "GET", f"/cases/{case['id']}")
    say("кандидат загрузил два файла", ", ".join(f"{i['key']}={i['status']}" for i in case["checklist"]))

    entry = item(case, "passport")
    api.call("hr", "POST", f"/cases/{case['id']}/items/{entry['id']}/review",
             json={"expected_revision": entry["revision"], "result": "accepted", "reason": None})
    entry = item(case, "education")
    api.call("hr", "POST", f"/cases/{case['id']}/items/{entry['id']}/review", json={
        "expected_revision": entry["revision"], "result": "needs_revision", "reason": "Скан нечитаем, нужна чёткая копия"})
    case = api.call("hr", "GET", f"/cases/{case['id']}")
    say("HR принял паспорт и вернул документ об образовании",
        ", ".join(f"{i['key']}={i['status']}" for i in case["checklist"]))

    refused = api.call("hr", "POST", f"/cases/{case['id']}/ready", 409, json={"expected_revision": case["revision"]})
    say("ready до принятия всех пунктов отклонён", refused["error"]["message"])

    seen = api.call("candidate", "GET", f"/cases/{case['id']}")
    say("кандидат видит замечание", item(seen, "education")["review_reason"])
    corrected = api.upload("candidate", "hiring_evidence", "diploma-clear.pdf", pdf("diploma v2"))
    entry = item(seen, "education")
    api.call("candidate", "POST", f"/cases/{case['id']}/items/{entry['id']}/submit", json={
        "expected_revision": entry["revision"], "document_id": corrected["id"], "comment": "Новая чёткая копия"})
    case = api.call("hr", "GET", f"/cases/{case['id']}")
    entry = item(case, "education")
    api.call("hr", "POST", f"/cases/{case['id']}/items/{entry['id']}/review",
             json={"expected_revision": entry["revision"], "result": "accepted", "reason": None})
    case = api.call("hr", "GET", f"/cases/{case['id']}")
    say("исправление принято, обе версии сохранены", f"education.document_ids={item(case, 'education')['document_ids']}")

    case = api.call("hr", "POST", f"/cases/{case['id']}/ready", json={"expected_revision": case["revision"]})
    say("комплект готов", f"status={case['status']}")

    order = api.upload("hr", "employment_basis", "order-DEMO-21.pdf", pdf("order DEMO-21"))
    case = api.call("hr", "POST", f"/cases/{case['id']}/start", json={
        "expected_revision": case["revision"], "starts_on": "2026-11-23",
        "basis": {"document_id": order["id"], "reference": "DEMO-21", "issued_on": "2026-11-21"},
        "confirmation_basis": "Оригиналы сверены кадровиком (учебно)"})
    say("выход зафиксирован без ожидания Workforce",
        f"status={case['status']} workforce_status={case['workforce_status']} transfer_mode={case['transfer_mode']}")
    api.call("candidate", "GET", f"/documents/{order['id']}/content", 404)
    say("кандидат не открывает внутреннее основание по прямому ID")

    data = api.call("hr", "GET", f"/cases/{case['id']}/registration-data")
    say("реквизиты для ручной регистрации", json.dumps(data, ensure_ascii=False))

    case = api.call("hr", "POST", f"/cases/{case['id']}/record-assignment", json={
        "expected_revision": case["revision"],
        "employee_ref": {"system": "workforce", "id": EMPLOYEE_ID},
        "assignment_ref": {"system": "workforce", "id": ASSIGNMENT_ID},
        "actual_starts_on": "2026-11-23", "confirmation_basis": "Назначение зарегистрировано в Workforce (учебно)"})
    say("кадровое подтверждение записано", f"workforce_status={case['workforce_status']} "
        f"employee_id={case['employee_id']} assignment_id={case['assignment_id']}")

    case = api.call("hr", "POST", f"/cases/{case['id']}/correct-start", json={
        "expected_revision": case["revision"], "starts_on": "2026-11-24",
        "reason": "Исправлена дата выхода по заявлению (учебно)"})
    say("исправление даты выхода", f"starts_on={case['starts_on']} workforce_status={case['workforce_status']}")
    case = api.call("hr", "POST", f"/cases/{case['id']}/record-assignment", json={
        "expected_revision": case["revision"],
        "employee_ref": {"system": "workforce", "id": EMPLOYEE_ID},
        "assignment_ref": {"system": "workforce", "id": ASSIGNMENT_ID},
        "actual_starts_on": "2026-11-23",
        "confirmation_basis": "Кадровое основание подтверждает 23 ноября, прежняя дата сохранена"})
    say("HR сохранил прежнее назначение", f"workforce_status={case['workforce_status']} "
        f"resolution={case['workforce_resolution']} reason={case['workforce_review_reason']}")

    other = api.call("hr", "POST", "/cases", json={"selection": second, "checklist": CHECKLIST,
                                                   "checklist_version": "training-1"})
    other = api.call("hr", "POST", f"/cases/{other['id']}/withdraw", json={
        "expected_revision": other["revision"], "reason": "Кандидат отказался до выхода (учебно)"})
    say("второй кандидат отозван до выхода", f"status={other['status']} workforce_status={other['workforce_status']}")

    history = api.call("hr", "GET", f"/cases/{case['id']}/history")
    say("история дела Марины", ", ".join(e["event_type"] for e in history["items"]))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hiring.demo", description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8103")
    return run(parser.parse_args(argv).base_url)


if __name__ == "__main__":
    sys.exit(main())
