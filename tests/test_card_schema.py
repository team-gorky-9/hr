"""Схема карточки и доказательств — без базы."""
import uuid

import pytest
from pydantic import ValidationError

from app.schemas.card import CandidateCard, Evidence, Experience, evidence_matches


def test_card_rejects_unknown_field():
    with pytest.raises(ValidationError):
        CandidateCard.model_validate({"skills": [], "salary": 100000})


def test_experience_period_must_be_ordered():
    with pytest.raises(ValidationError):
        Experience(start="2025-05", end="2024-05")
    with pytest.raises(ValidationError):
        Experience(start="2024-13")
    with pytest.raises(ValidationError):
        Experience(start="2024-01", end="2024-05", is_current=True)
    assert Experience(start="2024-05", end="2025-05").end == "2025-05"


def test_card_roundtrip_through_json():
    card = CandidateCard.model_validate(
        {
            "headline": "Python Backend Developer",
            "experience_years": 13.3,
            "experience": [{"position": "Backend-разработчик", "start": "2024-05", "end": "2025-05"}],
            "skills": [{"name": "FastAPI"}],
            "missing": ["сопроводительное письмо"],
        }
    )
    assert CandidateCard.model_validate(card.model_dump(mode="json")) == card


def test_evidence_bounds_must_match_quote():
    text_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        Evidence(candidate_text_id=text_id, quote="Pytest", start=0, end=3)
    text = "Писала автоматические тесты на Pytest."
    start = text.index("Pytest")
    ok = Evidence(candidate_text_id=text_id, quote="Pytest", start=start, end=start + 6)
    assert evidence_matches(text, ok)
    moved = Evidence(candidate_text_id=text_id, quote="Pytest", start=0, end=6)
    assert not evidence_matches(text, moved)
