"""Аудит очищенных текстов: не осталось ли в `candidate_texts` персональных данных.

    uv run python -m app.ingest.audit            # сводка в stderr, JSON-отчёт в stdout
    uv run python -m app.ingest.audit --report audit.json

Проверка независима от очистки (`redact.py`) — иначе она проверяла бы саму себя:
1. **Сверка с `candidate_pii`.** Значения, которые импорт у этого кандидата извлёк
   (email, телефон, ссылки, ник из ссылки, слова ФИО, номер в архиве, дата рождения),
   не должны встречаться в его текущем очищенном тексте. Самая точная проверка.
2. **Широкие шаблоны** — свои, не из `redact.py`: email, телефон с любыми разделителями
   (в том числе неразрывными U+2011, U+00A0), ссылки на профили, шапка
   «Женщина, 31 год», «родилась …», «ФИО N», «Кандидат №N».
3. **На ручную проверку** (не влияют на код выхода): `@слово` — в IT-резюме это чаще
   декоратор кода (`@pytest.fixture`), чем ник.

Отчёт содержит только категории, счётчики и коды кандидатов — без фрагментов текста
и значений ПДн. Аудит — служебный скрипт: он читает `candidate_pii` напрямую, без записи
в журнал раскрытий, потому что ничего не показывает человеку.

Код выхода: 0 — находок в категориях 1–2 нет, 1 — есть, 2 — нет базы.
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Candidate, CandidatePii, CandidateText

_SEP = r"[\s\-‐-― ()]*"
PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-zа-я]{2,}", re.IGNORECASE),
    # Телефон РФ: [+7|8|7] (XXX) XXX-XX-XX с любыми разделителями, кроме точки (точки — у дат).
    # Не внутри слова или ссылки: «Л035-01234-52/00176874» (лицензия) и hex в адресе Notion — не телефоны.
    "phone": re.compile(
        rf"(?<![\w\-/])(?:\+\s*7|8|7)?{_SEP}\d{{3}}{_SEP}\d{{3}}{_SEP}\d{{2}}{_SEP}\d{{2}}(?![\w/]|\.\d)"
    ),
    "profile_link": re.compile(
        r"(?:github\.com|gitlab\.com|t\.me|vk\.com|linkedin\.com/in|hh\.ru/resume|behance\.net|dribbble\.com"
        r"|career\.habr\.com|instagram\.com|ok\.ru|facebook\.com)/[\w-]{2,}|[\w-]{2,}\.github\.io",
        re.IGNORECASE,
    ),
    # Ссылка с путём или на личный хостинг: файл, макет, страница ведут к человеку.
    "personal_url": re.compile(
        r"(?:https?://|www\.)[^\s/]+/[^\s\])]{2,}"
        r"|(?<![A-Za-z0-9.\-/])(?:[a-z0-9-]+\.)+(?:ru|com|net|org|io|me|so|site|app|dev)/[\w%/-]{2,}"
        r"|[\w-]+\.(?:notion\.site|netlify\.app|vercel\.app|tilda\.ws|wixsite\.com|github\.io|gitlab\.io)",
    ),
    "person_header": re.compile(r"\b(?:мужчина|женщина)\s*,\s*\d{1,3}\s*(?:год|года|лет)\b", re.IGNORECASE),
    "birth_date": re.compile(
        r"(?:родил(?:ся|ась)|дата\s+рождения|д\.\s?р\.)[\s:–—-]*(?:\d{1,2}[\s./-]|[а-я]+\s+\d{4})", re.IGNORECASE
    ),
    "archive_id": re.compile(r"\bФИО\s+\d+|\bКандидат\s*№\s*\d+", re.IGNORECASE),
}
REVIEW_PATTERNS: dict[str, re.Pattern] = {
    "at_word": re.compile(r"(?<![\w.@])@[A-Za-z_][\w]{2,}"),
}


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _phone_tail(value: str) -> str | None:
    """Последние 10 цифр телефона: +7 999 000-00-01 и 8 (999) 000 00 01 — одно и то же."""
    digits = _digits(value)
    return digits[-10:] if len(digits) >= 10 else None


# Ник берём только из адресов профилей: в «figma.com/design/…» «design» — не ник.
_PROFILE_NICK = re.compile(
    r"(?:github\.com|gitlab\.com|t\.me|vk\.com|linkedin\.com/in|instagram\.com|behance\.net|dribbble\.com"
    r"|career\.habr\.com|habr\.com/(?:ru/)?users)/([\w.-]{4,})",
    re.IGNORECASE,
)


def _nick_from_link(link: str) -> str | None:
    match = _PROFILE_NICK.search(link) or re.search(r"([\w-]{4,})\.git(?:hub|lab)\.io", link, re.IGNORECASE)
    return match.group(1).strip("./") if match else None


def pii_leaks(text: str, pii: CandidatePii) -> list[str]:
    """Категории значений этого кандидата, которые остались в его тексте."""
    found: set[str] = set()
    lowered = text.casefold()
    emails = [pii.email, *(pii.extra or {}).get("emails", [])]
    if any(email and email.casefold() in lowered for email in emails):
        found.add("pii_email")
    tails = {_phone_tail(phone) for phone in [pii.phone, *(pii.extra or {}).get("phones", [])] if phone} - {None}
    if tails and any(_phone_tail(match.group(0)) in tails for match in PATTERNS["phone"].finditer(text)):
        found.add("pii_phone")
    for link in pii.links or []:
        if link.startswith("@"):  # ник из «@ник»
            if len(link) > 4 and re.search(rf"(?<![\w-]){re.escape(link[1:])}(?![\w-])", text, re.IGNORECASE):
                found.add("pii_nick")
            continue
        if not re.search(r"\w\.\w", link) or re.search(r"\s", link):
            continue  # не адрес: v1 сохраняла так «CI/CD» из «Git: CI/CD» и целые фразы после «VK:»
        bare = re.sub(r"^(?:https?://)?(?:www\.)?", "", link, flags=re.IGNORECASE).rstrip("/").casefold()
        if bare and bare in lowered:
            found.add("pii_link")
        nick = _nick_from_link(link)
        if nick and re.search(rf"(?<![\w-]){re.escape(nick)}(?![\w-])", text, re.IGNORECASE):
            found.add("pii_nick")
    if pii.full_name:
        # Каждое слово ФИО длиной от 3 букв — целым словом и с большой буквы: «Роман» — имя, «роман» — нет.
        for word in re.findall(r"[А-ЯЁA-Z][а-яёa-z-]{2,}", pii.full_name):
            if re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text):
                found.add("pii_name")
    extra = pii.extra or {}
    for key, category in (("archive_label", "pii_archive_id"), ("birth_date_raw", "pii_birth_date")):
        value = extra.get(key)
        if value and str(value).casefold() in lowered:
            found.add(category)
    if pii.birth_date is not None and pii.birth_date.strftime("%d.%m.%Y") in text:
        found.add("pii_birth_date")
    return sorted(found)


@dataclass
class AuditReport:
    texts: int = 0
    findings: dict[str, list[str]] = field(default_factory=dict)  # категория → коды кандидатов
    review: dict[str, list[str]] = field(default_factory=dict)

    def add(self, bucket: dict[str, list[str]], category: str, code: str) -> None:
        bucket.setdefault(category, []).append(code)

    @property
    def flagged_codes(self) -> list[str]:
        return sorted({code for codes in self.findings.values() for code in codes})

    def as_dict(self) -> dict:
        return {
            "texts": self.texts,
            "flagged_candidates": len(self.flagged_codes),
            "findings": {key: {"count": len(codes), "candidate_codes": sorted(codes)}
                         for key, codes in sorted(self.findings.items())},
            "review": {key: {"count": len(codes), "candidate_codes": sorted(codes)}
                       for key, codes in sorted(self.review.items())},
        }


def audit_text(text: str, pii: CandidatePii | None) -> tuple[list[str], list[str]]:
    """(находки, на ручную проверку) для одного текста."""
    findings = [name for name, pattern in PATTERNS.items() if pattern.search(text)]
    if pii is not None:
        findings += pii_leaks(text, pii)
    review = [name for name, pattern in REVIEW_PATTERNS.items() if pattern.search(text)]
    return findings, review


def run_audit(session: Session) -> AuditReport:
    report = AuditReport()
    rows = session.execute(
        select(Candidate.code, CandidateText.text, CandidatePii)
        .join(CandidateText, CandidateText.candidate_id == Candidate.id)
        .outerjoin(CandidatePii, CandidatePii.candidate_id == Candidate.id)
        .where(CandidateText.is_current.is_(True))
        .order_by(Candidate.code)
    )
    for code, text, pii in rows:
        report.texts += 1
        findings, review = audit_text(text, pii)
        for category in findings:
            report.add(report.findings, category, code)
        for category in review:
            report.add(report.review, category, code)
    return report


def main(argv: list[str] | None = None, session_factory=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ingest.audit", description="Аудит очистки ПДн")
    parser.add_argument("--report", help="сохранить JSON-отчёт ещё и в файл")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    if session_factory is None:
        from app.db.session import SessionLocal
        session_factory = SessionLocal
    try:
        with session_factory() as session:
            report = run_audit(session)
    except SQLAlchemyError as error:  # нет базы или схемы: понятное сообщение вместо трассировки
        print(f"аудит не выполнен: {type(error).__name__}", file=sys.stderr)
        return 2

    payload = json.dumps(report.as_dict(), ensure_ascii=False, indent=2)
    print(payload)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as file:
            file.write(payload)
    summary = ", ".join(f"{key}={len(codes)}" for key, codes in sorted(report.findings.items())) or "находок нет"
    print(f"аудит: текстов {report.texts}, кандидатов с находками {len(report.flagged_codes)}; {summary}",
          file=sys.stderr)
    return 1 if report.findings else 0


if __name__ == "__main__":
    sys.exit(main())
