from uuid import uuid4

from app.db.enums import ChunkKind
from app.search.ranking import Document, bm25, fuse, prepare, rank_branch
from app.search.service import evidence_of
from app.search.text import MAX_BYTES, exact_tokens, split_chunks


def document(code: str, text: str) -> Document:
    return Document(uuid4(), code, uuid4(), text)


def test_sections_literal_offsets_emoji_and_footer():
    text = (
        "🧩\r\nОпыт работы :\r\nРазработал API.\r\nКлючевые навыки\r\nFastAPI.\r\n"
        "Образование\r\nВысшее.\r\nОбо мне\r\nЛюблю базы данных.\r\n"
        "Сопроводительное письмо\r\nПишу тесты.\r\nОтклик на вакансию:\r\nАудитор ИБ"
    )
    chunks = split_chunks(text)
    assert [chunk.kind for chunk in chunks] == [
        ChunkKind.EXPERIENCE, ChunkKind.SKILLS, ChunkKind.EDUCATION, ChunkKind.ABOUT, ChunkKind.COVER_LETTER,
    ]
    assert [chunk.text for chunk in chunks] == [
        "Разработал API.", "FastAPI.", "Высшее.", "Люблю базы данных.", "Пишу тесты.",
    ]
    hit = bm25(prepare([document("one", text)], "FastAPI", []))[0]
    evidence = evidence_of(hit.passage)
    assert evidence.utf16_start == evidence.start_offset + 1
    encoded = text.encode("utf-16-le")
    assert encoded[evidence.utf16_start * 2:evidence.utf16_end * 2].decode("utf-16-le") == "FastAPI."
    assert text[evidence.start_offset:evidence.end_offset] == "FastAPI."


def test_no_heading_fallback_and_long_tail():
    text = "ж" * 500 + "\nНастроил аварийное восстановление PostgreSQL."
    parts = split_chunks(text)
    assert len(parts) > 2 and all(chunk.kind == ChunkKind.FULL for chunk in parts)
    assert "восстановление PostgreSQL" in parts[-1].text
    assert all(0 < len(chunk.text.encode()) <= MAX_BYTES for chunk in parts)
    assert all(chunk.text == text[chunk.start:chunk.end] for chunk in parts)
    assert parts[-1].end == len(text)


def test_required_terms_are_whole_tokens_and_can_be_in_separate_sections():
    hit = document("actual", "Опыт работы\nПрименял 44 – ФЗ.\nНавыки\nЕИС. C++. 1С. Node.js.")
    other_law = document("similar", "44-ФЗ1, 144-ФЗ. Публиковала данные в ЕИС.")
    denial = document("denial", "Не работал с ЕИС. Применял 44-ФЗ.")
    history = document("history", "Вёл путевые листы.\nИстория общения с кандидатом\n44-ФЗ ЕИС")
    prepared = prepare([hit, other_law, denial, history], "", ["44‑ФЗ", "ЕИС"])
    assert prepared.candidates == {hit.candidate_id}
    assert prepared.exact_evidence[hit.candidate_id].chunk.text == "Применял 44 – ФЗ."
    assert exact_tokens(" 25-ФЗ, 44‑ФЗ, 131—ФЗ, 1С, C++, Node.js, .NET. ") == (
        "25-фз", "44-фз", "131-фз", "1с", "c++", "node.js", ".net",
    )
    assert prepare([hit], "", ["Node.js", "C++", "1С"]).candidates == {hit.candidate_id}
    assert prepare([hit], "", ["С++"]).candidates == set()  # кириллическая С


def test_candidates_are_ranked_before_rrf_and_dense_obeys_direct_negation():
    double = document("aa", "Опыт работы\nПисал API тесты.\nНавыки\nАвтоматизация API тестов.")
    second = document("bb", "Разворачивал сетевое приложение.")
    denial = document("cc", "Обо мне\nБез опыта API.\nОпыт работы\nМонтировал оборудование.")
    allowed = prepare([double, second, denial], "API", [])
    assert denial.candidate_id not in allowed.candidates
    lexical = bm25(allowed)
    assert [hit.passage.document.code for hit in lexical] == ["aa"]
    scores = {chunk_id: 0.95 if passage.document.code == "aa" else 0.7
              for chunk_id, passage in allowed.passages.items()}
    dense = rank_branch(allowed, scores, "semantic", 0.8)
    assert [hit.passage.document.code for hit in dense] == ["aa"]
    result = fuse(lexical, dense)
    assert [(hit.kind, hit.score) for hit in result] == [("hybrid", 2 / 61)]
    assert bm25(prepare([double, second], "микробиология", [])) == []


def test_positive_sentence_wins_over_direct_negation_chunk():
    doc = document("both", "Обо мне\nНет опыта с C++.\nОпыт работы\nПозднее разработал модуль на C++.")
    allowed = prepare([doc], "C++", ["C++"])
    assert allowed.candidates == {doc.candidate_id}
    assert [p.chunk.kind for p in allowed.passages.values()] == [ChunkKind.EXPERIENCE]
    assert bm25(allowed)[0].passage.chunk.text == "Позднее разработал модуль на C++."
