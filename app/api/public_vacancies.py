"""Public projection of a legacy training vacancy and its professional criteria."""

import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.errors import ApiError
from app.api.routes import SessionDep
from app.db.enums import Channel, DocumentKind, VacancyStatus
from app.db.models import SourceDocument, Vacancy
from app.db.repository import get_approved_profile

router = APIRouter(prefix="/api/v1")
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
# Paragraph addresses verified against the all_six source manifest. Public excerpts stop
# before signatures, approvals, and internal procedures. The UX source has senior duties too.
DUTY_PARAGRAPHS = {
    "jpy-di": range(112, 118),
    "ux-di": range(118, 128),
    "fe-di": range(109, 114),
    "py-di": range(120, 126),
    "qa-di": range(107, 121),
    "hr-di": range(102, 109),
}
TRAINING_PYTHON_POSTING = "59d7c66c37905b170ca3cbf615480421820944928927e0d73c82c9ed0ed3a764"
POSTING_HEADINGS = re.compile(
    r"^(обязанности|что (?:нужно|предстоит) делать|задачи|требования|что (?:мы )?ожидаем|"
    r"будет плюсом|условия(?: работы)?|мы предлагаем|что (?:мы )?предлагаем|о вакансии|о компании)"
    r"\s*(?::\s*(.*))?$",
    re.IGNORECASE,
)
PRIVATE_LINE = re.compile(
    r"\b(?:резюме|ф\.?и\.?о\.?|паспортн\w*|снилс|инн|подпись|телефон|почт[ау]|электронн\w+ адрес)\b"
    r"|https?://|www\.|[\w.+-]+@[\w.-]+\.[\w-]+|(?:\+7|\b8)[\s(.-]*\d{3}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}",
    re.IGNORECASE,
)


class PublicationCriterion(BaseModel):
    text: str
    mandatory: bool


class PublicTrainingVacancy(BaseModel):
    vacancy_id: UUID
    position_code: str
    title: str
    employer: str
    approved_profile_version: int
    opened_at: date | None = None
    description: str | None = None
    duties: list[str] = Field(default_factory=list)
    requirements: list[PublicationCriterion] = Field(default_factory=list)
    advertised_requirements: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    duties_source: str | None = None


@lru_cache
def source_manifests():
    postings = json.loads((FIXTURES / "posting_positions/runtime-sources.json").read_text(encoding="utf-8"))
    training = FIXTURES / "requirement_profiles/all_six"
    documents = json.loads((training / "sources.json").read_text(encoding="utf-8"))["documents"]
    profiles = json.loads((training / "profiles.draft.json").read_text(encoding="utf-8"))["profiles"]
    documents_by_id = {row["id"]: row for row in documents}
    postings_by_position = {
        row["position_code"]: row["publication"]
        for row in postings["decisions"].values()
        if "publication" in row
    }
    instructions_by_position = {
        row["position_code"]: documents_by_id[source["source_id"]]
        for row in profiles
        for source in row["sources"]
        if source["role"] == "job_description"
    }
    return postings_by_position, instructions_by_position


def professional_line(value):
    text = " ".join(value.strip().split()).strip("•–—-; ")
    return text if text and not PRIVATE_LINE.search(text) else None


def trusted_document(session, kind, digest):
    if not digest:
        return None
    return session.scalar(select(SourceDocument).where(SourceDocument.kind == kind, SourceDocument.sha256 == digest))


def posting_sections(text):
    sections = {"intro": [], "duties": [], "requirements": [], "conditions": []}
    current = "intro"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        heading = POSTING_HEADINGS.fullmatch(line)
        if heading:
            title, trailing = heading.groups()
            title = title.lower()
            if title in ("о вакансии", "о компании"):
                current = "intro"
            elif title.startswith(("условия", "мы предлагаем", "что мы предлагаем", "что предлагаем")):
                current = "conditions"
            elif title.startswith(("требования", "будет плюсом", "что мы ожидаем", "что ожидаем")):
                current = "requirements"
            else:
                current = "duties"
            line = trailing or ""
        elif line.lower().startswith(("контакты", "как откликнуться", "как с нами связаться")):
            break
        allowed = professional_line(line)
        if allowed:
            sections[current].append(allowed)
    return sections


def instruction_duties(session, manifest):
    if not manifest:
        return [], None
    document = trusted_document(session, DocumentKind.JOB_DESCRIPTION, manifest["sha256"])
    excerpt = [
        re.sub(r"^\d+(?:\.\d+)+\.?\s+", "", line)
        for index in DUTY_PARAGRAPHS.get(manifest["id"], ())
        if (line := professional_line(manifest["paragraphs"].get(f"P{index}", "")))
    ]
    if document is not None and document.raw_text:
        stored_lines = {" ".join(line.split()) for line in document.raw_text.splitlines()}
        if all(" ".join(manifest["paragraphs"].get(f"P{index}", "").split()) in stored_lines
               for index in DUTY_PARAGRAPHS.get(manifest["id"], ()) if f"P{index}" in manifest["paragraphs"]):
            return excerpt, "По должностной инструкции"
    return excerpt, "По сохранённым выдержкам должностной инструкции"


@router.get("/public/vacancies/{vacancy_id}", response_model=PublicTrainingVacancy)
def public_training_vacancy(vacancy_id: UUID, session: SessionDep):
    vacancy = session.get(Vacancy, vacancy_id)
    profile = (
        get_approved_profile(session, vacancy.position_id, synthetic=True)
        if vacancy is not None and vacancy.status == VacancyStatus.OPEN else None
    )
    if vacancy is None or profile is None:
        raise ApiError(404, "NOT_FOUND", "Опубликованная учебная вакансия не найдена.")

    position = vacancy.position
    postings, instructions = source_manifests()
    # The legacy seed links organizer postings by their original HH title and position.
    seeded_posting = vacancy.channel == Channel.HH_RU and vacancy.title == position.title
    posting_source = postings.get(position.code, {}) if seeded_posting else {}
    posting = trusted_document(session, DocumentKind.VACANCY_POSTING, posting_source.get("sha256"))
    if posting is None and seeded_posting and position.code == "python-dev":
        posting = trusted_document(session, DocumentKind.VACANCY_POSTING, TRAINING_PYTHON_POSTING)
    sections = posting_sections(posting.raw_text if posting is not None else "")
    intro = [line for line in sections["intro"] if line not in {vacancy.title, position.title, position.employer}]
    description = "\n\n".join(intro) if intro else professional_line(posting_source.get("exact_passage", ""))
    duties = sections["duties"]
    duties_source = "Из объявления" if duties else None
    if not duties:
        duties, duties_source = instruction_duties(session, instructions.get(position.code))
    conditions = sections["conditions"]
    if position.is_municipal_service and position.service_group:
        conditions = [*conditions, position.service_group]

    return PublicTrainingVacancy(
        vacancy_id=vacancy.id,
        position_code=position.code,
        title=vacancy.title,
        employer=position.employer,
        approved_profile_version=profile.version,
        opened_at=vacancy.opened_at,
        description=description,
        duties=duties,
        duties_source=duties_source,
        requirements=[
            PublicationCriterion(text=line, mandatory=criterion.is_mandatory)
            for criterion in profile.formal_requirements
            if (line := professional_line(criterion.description))
        ],
        advertised_requirements=sections["requirements"],
        conditions=conditions,
    )
