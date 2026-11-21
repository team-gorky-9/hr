import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ai.errors import LLMInvalidResponseError
from app.assessment.artifacts import ArtifactStore, ProcessingArtifact
from app.assessment.facts import ExtractedFacts, extract_facts


class Extractor:
    calls = []
    def __init__(self, quote):
        self.quote, self.count = quote, 0
    def model_name(self, role):
        return "controlled-test-model"
    def complete_structured(self, *args, **kwargs):
        self.count += 1
        return ExtractedFacts.model_validate({"card": {}, "assertions": [
            {"kind": "activity", "statement": "Разработка API", "quote": self.quote,
             "polarity": "asserted"}]})


def test_reuse_survives_restart_and_is_scoped(tmp_path):
    url = "sqlite:///" + str(tmp_path / "facts.db")
    engine = create_engine(url)
    ProcessingArtifact.__table__.create(engine)
    text = SimpleNamespace(id=uuid.uuid4(), text="Разрабатывал API на Python.")
    client = Extractor(text.text)
    with Session(engine) as session:
        original = extract_facts(ArtifactStore(session, "training:one"), text, client)
        session.commit()
    engine.dispose()
    with Session(create_engine(url)) as session:
        assert extract_facts(ArtifactStore(session, "training:one"), text, client) == original
        assert client.count == 1
        other = extract_facts(ArtifactStore(session, "training:two"), text, client)
        assert other["id"] != original["id"]
        assert client.count == 2
        changed = SimpleNamespace(id=uuid.uuid4(), text=text.text)
        assert extract_facts(ArtifactStore(session, "training:one"), changed, client)["id"] != original["id"]
        assert client.count == 3


def test_unfounded_fact_is_not_persisted():
    engine = create_engine("sqlite://")
    ProcessingArtifact.__table__.create(engine)
    with Session(engine) as session:
        text = SimpleNamespace(id=uuid.uuid4(), text="Изучаю Python.")
        with pytest.raises(LLMInvalidResponseError):
            extract_facts(ArtifactStore(session, "training:one"), text, Extractor("Работал пять лет"))
        assert session.query(ProcessingArtifact).count() == 0
