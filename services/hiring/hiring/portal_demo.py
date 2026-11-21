"""Учебный проход candidate-portal 5A через HTTP (AUTH_MODE=fixture, учебный снимок вакансий).

    uv run python -m hiring.portal_demo [--base-url http://127.0.0.1:8103]

candidate подаёт обращение по учебной вакансии «Экономист» с резюме, candidate2 — без вакансии.
Каждый видит своё; candidate2 не открывает чужое обращение и файл; HR видит очередь подач.
Дополнительное резюме после подачи сохраняется отдельным документом. Каждый запуск создаёт новые
обращения: это собственные подачи, дублей «по человеку» сервис не склеивает."""
import argparse
import sys
import uuid

import httpx

ECONOMIST = {"system": "catalog", "id": "00000000-0000-4000-8000-000000000c01", "revision": 1}


def pdf(label: str) -> bytes:
    return b"%PDF-1.4\n% synthetic resume: " + label.encode() + b"\n%%EOF\n"


class Client:
    def __init__(self, base_url):
        self.http = httpx.Client(base_url=base_url.rstrip("/") + "/api/v1", timeout=10)

    def call(self, login, method, path, **kwargs):
        headers = {"Authorization": f"Bearer fixture:{login}"}
        if method in ("POST", "PATCH"):
            headers["Idempotency-Key"] = str(uuid.uuid4())
        return self.http.request(method, path, headers=headers, **kwargs)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hiring.portal_demo")
    parser.add_argument("--base-url", default="http://127.0.0.1:8103")
    api = Client(parser.parse_args(argv).base_url)

    vacancies = api.call("candidate", "GET", "/candidate-portal/vacancies").json()
    print(f"• вакансии ({vacancies['source']}): {[v['title'] for v in vacancies['items']]}")
    first = api.call("candidate", "POST", "/candidate-requests", json={
        "vacancy_ref": ECONOMIST, "message": "Хочу работать экономистом (учебно)",
        "contact": {"channel": "email", "value": "candidate@example.test"}}).json()
    resume = api.call("candidate", "POST", f"/candidate-requests/{first['id']}/documents",
                      data={"kind": "candidate_resume"}, files={"file": ("resume.pdf", pdf("v1"), "application/pdf")}).json()
    first = api.call("candidate", "POST", f"/candidate-requests/{first['id']}/submit",
                     json={"expected_revision": first["revision"] + 1}).json()
    print(f"• candidate: {first['number']} status={first['status']} вакансия «{first['vacancy']['title']}» файл {resume['id'][:8]}…")

    second = api.call("candidate2", "POST", "/candidate-requests", json={
        "message": "Ищу работу по специальности, вакансию не выбрал (учебно)",
        "contact": {"channel": "phone", "value": "+7 000 000-00-00"}}).json()
    second = api.call("candidate2", "POST", f"/candidate-requests/{second['id']}/submit",
                      json={"expected_revision": second["revision"]}).json()
    print(f"• candidate2: {second['number']} status={second['status']} target_question={second['target_question']}")

    mine = [r["number"] for r in api.call("candidate", "GET", "/candidate-requests").json()["items"]]
    print(f"• candidate видит только свои: {first['number'] in mine and second['number'] not in mine}")
    foreign = api.call("candidate2", "GET", f"/candidate-requests/{first['id']}")
    foreign_file = api.call("candidate2", "GET", f"/candidate-requests/{first['id']}/documents/{resume['id']}/content")
    print(f"• candidate2 открывает чужое обращение / файл: {foreign.status_code} / {foreign_file.status_code}")

    extra = api.call("candidate", "POST", f"/candidate-requests/{first['id']}/documents",
                     data={"kind": "candidate_addendum"}, files={"file": ("resume-v2.pdf", pdf("v2"), "application/pdf")}).json()
    documents = api.call("candidate", "GET", f"/candidate-requests/{first['id']}").json()["documents"]
    original = api.call("candidate", "GET", f"/candidate-requests/{first['id']}/documents/{resume['id']}/content").content
    print(f"• дополнительное резюме {extra['id'][:8]}…: документов {len(documents)}, оригинал не изменён: {original == pdf('v1')}")

    queue = api.call("hr", "GET", "/candidate-requests?status=submitted").json()["items"]
    print(f"• очередь HR: {[r['number'] for r in queue][-2:]}, контакт {queue[-1]['contact']}")
    denied = api.call("hr", "POST", "/candidate-requests", json={"message": "от HR", "contact": {"channel": "email", "value": "x@y.z"}})
    print(f"• HR создаёт обращение за кандидата: {denied.status_code} {denied.json()['error']['code']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
