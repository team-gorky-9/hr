"""Таблица векторов: хранение и поиск ближайшего фрагмента средствами pgvector.
Векторы здесь игрушечные (3 числа); настоящие эмбеддинги — зона модуля поиска."""
from sqlalchemy import select

from app.db import repository as repo
from app.db.enums import ChunkKind
from app.db.models import Embedding
from tests.factories import make_candidate


def add_chunk(session, candidate, index, vector, model="toy-3d"):
    text_row = repo.get_current_text(session, candidate.id)
    session.add(
        Embedding(
            candidate_id=candidate.id, candidate_text_id=text_row.id, chunk_kind=ChunkKind.EXPERIENCE,
            chunk_index=index, text=text_row.text, start_offset=0, end_offset=len(text_row.text),
            model=model, embedding=vector,
        )
    )
    session.flush()


def test_nearest_chunk_by_cosine_distance(session):
    a = make_candidate(session, "py-0300")
    b = make_candidate(session, "py-0301", text="Другой")
    add_chunk(session, a, 0, [1.0, 0.0, 0.0])
    add_chunk(session, b, 0, [0.0, 1.0, 0.0])
    # Векторы другой модели и размерности лежат рядом и не мешают: поиск фильтрует по модели.
    add_chunk(session, b, 1, [0.9, 0.1, 0.0, 0.0], model="toy-4d")

    query = [0.9, 0.2, 0.0]
    nearest = session.scalars(
        select(Embedding)
        .where(Embedding.model == "toy-3d")
        .order_by(Embedding.embedding.cosine_distance(query))
        .limit(1)
    ).one()
    assert nearest.candidate_id == a.id
