"""Волна 6 · путь HR и кандидата: один сквозной показ через HTTP с записью запросов и ответов.

    uv run python -m hiring.recruitment_demo \
        --hiring-url http://127.0.0.1:8103 --legacy-url http://127.0.0.1:8000 \
        --transcript ../../docs/reports/wave-6-recruitment-demo.transcript.json

Путь:
1. candidate подаёт обращение по учебной вакансии «Экономист» с новым PDF-резюме (Hiring, 5A).
   Новый файл сохраняется как оригинал — его текст не извлекается и не оценивается (OCR и
   обработка непрочитанного скана — пункт 7.7).
2. HR видит подачу в очереди и запрашивает уточнение (5B) → сообщение в кабинете кандидата.
3. candidate читает сообщение, отмечает прочтение и отправляет дополнение с текстом и вторым файлом.
4. HR отмечает готовность. Затем ищет в учебном корпусе старого подбора (legacy, контур training)
   заранее подготовленную запись по профессиональному тексту и берёт её основание — фрагмент и отклик.
5. HR записывает рассмотрение вручную (manual-confirmed) со ссылками на подготовленную запись
   legacy-hr-training. Это ЯВНО учебная связь для показа: заранее подготовленная запись — не тот же
   человек, что учётка candidate; реальная сверка личности на показе не выполняется.
6. HR публикует разрешённый исход continue со следующим шагом.
7. candidate перечитывает обращение и читает сообщение об исходе.
8. Отрицательный случай: candidate2 не открывает обращение candidate и его сообщения (404).

Все запросы и ответы пишутся в transcript (без секретов: вход — учебные fixture-логины)."""
import argparse
import json
import sys
import uuid
from pathlib import Path

import httpx

ECONOMIST = {"system": "catalog", "id": "00000000-0000-4000-8000-000000000c01", "revision": 1}
SEARCH_QUERY = "функциональные требования к СЭД"


def pdf(label: str) -> bytes:
    return b"%PDF-1.4\n% synthetic training resume: " + label.encode() + b"\n%%EOF\n"


class Recorder:
    def __init__(self, hiring_url: str, legacy_url: str):
        self.hiring = httpx.Client(base_url=hiring_url.rstrip("/"), timeout=30)
        self.legacy = httpx.Client(base_url=legacy_url.rstrip("/"), timeout=30)
        self.steps: list[dict] = []

    def hiring_call(self, step, login, method, path, *, json_body=None, files=None, data=None):
        headers = {"Authorization": f"Bearer fixture:{login}"}
        if method in ("POST", "PATCH"):
            headers["Idempotency-Key"] = str(uuid.uuid4())
        response = self.hiring.request(method, f"/api/v1{path}", headers=headers, json=json_body,
                                       files=files, data=data)
        return self._keep(step, "hiring", login, method, f"/api/v1{path}", json_body,
                          {"multipart": {"kind": data.get("kind"), "file": files["file"][0]}} if files else None,
                          response)

    def legacy_call(self, step, login, method, path, *, json_body=None):
        response = self.legacy.request(method, f"/api/v1{path}", headers={"X-User-Login": login}, json=json_body)
        return self._keep(step, "legacy-hr", login, method, f"/api/v1{path}", json_body, None, response)

    def _keep(self, step, service, login, method, path, json_body, upload, response):
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else None
        self.steps.append({"step": step, "service": service, "actor": login, "method": method, "path": path,
                           "request": json_body if upload is None else upload, "status": response.status_code,
                           "response": body})
        mark = "✓" if response.status_code < 400 else "✗"
        print(f"{mark} {step}: {method} {path} → {response.status_code}")
        return response.status_code, body


def run(rec: Recorder) -> dict:
    ids: dict = {}
    status, row = rec.hiring_call("1. Кандидат создаёт обращение по вакансии", "candidate", "POST",
                                  "/candidate-requests", json_body={
                                      "vacancy_ref": ECONOMIST,
                                      "message": "Хочу работать экономистом в администрации (учебно)",
                                      "contact": {"channel": "email", "value": "candidate@example.test"}})
    ids["request_id"] = row["id"]
    status, resume = rec.hiring_call("1. Кандидат прикладывает новое резюме (оригинал, без извлечения)", "candidate",
                                     "POST", f"/candidate-requests/{row['id']}/documents", data={"kind": "candidate_resume"},
                                     files={"file": ("resume-new.pdf", pdf("resume v1"), "application/pdf")})
    ids["resume_document_id"] = resume["id"]
    status, row = rec.hiring_call("1. Кандидат отправляет обращение", "candidate", "POST",
                                  f"/candidate-requests/{row['id']}/submit",
                                  json_body={"expected_revision": resume["request_revision"]})
    ids["request_number"] = row["number"]

    rec.hiring_call("2. Очередь HR", "hr", "GET", "/candidate-requests?status=submitted")
    status, row = rec.hiring_call("2. HR запрашивает уточнение", "hr", "POST",
                                  f"/candidate-requests/{row['id']}/information-request", json_body={
                                      "expected_revision": row["revision"],
                                      "public_message": "Опишите опыт работы с требованиями к информационным системам",
                                      "requested_items": ["опыт работы", "обновлённое резюме"]})

    status, inbox = rec.hiring_call("3. Кандидат видит сообщение", "candidate", "GET",
                                    f"/candidate-requests/{row['id']}/messages")
    ids["information_message_id"] = inbox["items"][0]["id"]
    rec.hiring_call("3. Кандидат отмечает прочтение", "candidate", "POST",
                    f"/candidate-requests/{row['id']}/messages/{inbox['items'][0]['id']}/read")
    status, second = rec.hiring_call("3. Кандидат прикладывает обновлённое резюме", "candidate", "POST",
                                     f"/candidate-requests/{row['id']}/documents", data={"kind": "candidate_addendum"},
                                     files={"file": ("resume-updated.pdf", pdf("resume v2"), "application/pdf")})
    ids["addendum_document_id"] = second["id"]
    status, row = rec.hiring_call("3. Кандидат отправляет дополнение", "candidate", "POST",
                                  f"/candidate-requests/{row['id']}/addendum", json_body={
                                      "expected_revision": second["request_revision"],
                                      "information_request_ref": row["information_request_ref"],
                                      "text": "Собирала функциональные требования к СЭД и согласовывала их с подрядчиком (учебно)",
                                      "document_ids": [second["id"]]})

    status, row = rec.hiring_call("4. HR отмечает готовность", "hr", "POST", f"/candidate-requests/{row['id']}/ready",
                                  json_body={"expected_revision": row["revision"],
                                             "review_basis": "Опыт и обновлённое резюме получены (учебно)"})
    status, found = rec.legacy_call("4. HR ищет подготовленную запись в учебном корпусе подбора", "hr_demo", "POST",
                                    "/search/candidates", json_body={"contour": "training", "query": SEARCH_QUERY,
                                                                     "limit": 3})
    prepared = next(item for item in found["items"] if item["applications"])
    application = next(a for a in prepared["applications"] if a["source"] == "response")
    ids |= {"prepared_candidate_code": prepared["candidate_code"], "prepared_candidate_id": prepared["candidate_id"],
            "prepared_application_id": application["application_id"],
            "prepared_fragment": prepared["evidence"]["fragment"] if prepared["evidence"] else None}

    status, row = rec.hiring_call("5. HR вручную записывает рассмотрение (учебная связь)", "hr", "POST",
                                  f"/candidate-requests/{row['id']}/record-consideration", json_body={
                                      "expected_revision": row["revision"],
                                      "candidate_ref": {"system": "legacy-hr-training", "id": prepared["candidate_id"]},
                                      "application_ref": {"system": "legacy-hr-training",
                                                          "id": application["application_id"]},
                                      "selected_vacancy_ref": ECONOMIST,
                                      "identity_basis": (f"Учебная связь для показа с подготовленной записью "
                                                         f"{prepared['candidate_code']}; реальная сверка личности не выполнялась"),
                                      "source_reference": (f"POST /api/v1/search/candidates (training, «{SEARCH_QUERY}»): "
                                                           f"«{ids['prepared_fragment']}»")})
    status, row = rec.hiring_call("6. HR публикует исход", "hr", "POST", f"/candidate-requests/{row['id']}/public-outcome",
                                  json_body={"expected_revision": row["revision"], "outcome": "continue",
                                             "public_explanation": "Обращение передано на собеседование в отдел планирования.",
                                             "next_action": "Ожидайте приглашения в течение 10 рабочих дней",
                                             "source_reference": "Решение HR после проверки дополнения (учебно)"})

    status, own = rec.hiring_call("7. Кандидат перечитывает обращение", "candidate", "GET",
                                  f"/candidate-requests/{row['id']}")
    status, inbox = rec.hiring_call("7. Кандидат видит сообщение об исходе", "candidate", "GET",
                                    f"/candidate-requests/{row['id']}/messages")
    outcome_message = inbox["items"][-1]
    ids["outcome_message_id"] = outcome_message["id"]
    rec.hiring_call("7. Кандидат отмечает прочтение исхода", "candidate", "POST",
                    f"/candidate-requests/{row['id']}/messages/{outcome_message['id']}/read")
    rec.hiring_call("7. Повторное чтение сохранённого результата", "candidate", "GET", f"/candidate-requests/{row['id']}")

    rec.hiring_call("8. candidate2 открывает чужое обращение", "candidate2", "GET", f"/candidate-requests/{row['id']}")
    rec.hiring_call("8. candidate2 читает чужие сообщения", "candidate2", "GET",
                    f"/candidate-requests/{row['id']}/messages")
    rec.hiring_call("8. candidate2 открывает чужой файл", "candidate2", "GET",
                    f"/candidate-requests/{row['id']}/documents/{ids['resume_document_id']}/content")
    rec.hiring_call("История обращения (HR)", "hr", "GET", f"/candidate-requests/{row['id']}/history")
    return ids


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hiring.recruitment_demo")
    parser.add_argument("--hiring-url", default="http://127.0.0.1:8103")
    parser.add_argument("--legacy-url", default="http://127.0.0.1:8000")
    parser.add_argument("--transcript", type=Path)
    args = parser.parse_args(argv)
    rec = Recorder(args.hiring_url, args.legacy_url)
    ids = run(rec)
    print(json.dumps(ids, ensure_ascii=False, indent=2))
    if args.transcript:
        args.transcript.write_text(json.dumps({"ids": ids, "steps": rec.steps}, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
        print(f"transcript: {args.transcript}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
