"""BM25, допуск к ранжированию и RRF на уровне кандидата."""
from collections import Counter
from dataclasses import dataclass
from math import log1p
from uuid import UUID, uuid5

from app.search.text import CHUNK_VERSION, Chunk, ChunkTerms, chunk_terms, exact_tokens, query_terms, split_chunks

LEXICAL_THRESHOLD = 1e-9
RRF_K = 60


@dataclass(frozen=True, slots=True)
class Document:
    candidate_id: UUID
    code: str
    candidate_text_id: UUID
    text: str


@dataclass(slots=True)
class Passage:
    id: UUID
    document: Document
    chunk: Chunk
    terms: ChunkTerms


@dataclass(slots=True)
class Prepared:
    passages: dict[UUID, Passage]
    exact_evidence: dict[UUID, Passage]
    candidates: set[UUID]
    query_words: frozenset[str]


@dataclass(frozen=True, slots=True)
class Ranked:
    passage: Passage
    score: float
    kind: str


def passage_id(candidate_text_id: UUID, chunk: Chunk) -> UUID:
    return uuid5(candidate_text_id, f"{CHUNK_VERSION}:{chunk.kind.value}:{chunk.index}")


def prepare(documents: list[Document], query: str, required_terms: list[str]) -> Prepared:
    required = [exact_tokens(term) for term in required_terms]
    query_words = query_terms(query)
    allowed = Prepared({}, {}, set(), query_words)
    for document in documents:
        chunks = split_chunks(document.text)
        passages = [Passage(passage_id(document.candidate_text_id, chunk), document, chunk,
                            chunk_terms(chunk.text)) for chunk in chunks]
        positive = set().union(*(passage.terms.lexemes for passage in passages))
        negative = set().union(*(passage.terms.negative for passage in passages))
        # Прямое отрицание названного навыка без положительного упоминания
        # не должно пройти только за счёт плотной близости.
        if query_words & (negative - positive):
            continue
        if required:
            matches = [{i for i, term in enumerate(required) if passage.terms.has(term)}
                       for passage in passages]
            if len(set().union(*matches)) != len(required):
                continue
            best_index = max(range(len(matches)), key=lambda index: len(matches[index]))
            allowed.exact_evidence[document.candidate_id] = passages[best_index]
        allowed.candidates.add(document.candidate_id)
        for passage in passages:
            if not (query_words & (passage.terms.negative - passage.terms.lexemes.keys())):
                allowed.passages[passage.id] = passage
    return allowed


def bm25(prepared: Prepared) -> list[Ranked]:
    passages = list(prepared.passages.values())
    words = prepared.query_words
    if not passages or not words:
        return []
    df: Counter[str] = Counter()
    sizes = []
    for passage in passages:
        df.update(words & passage.terms.lexemes.keys())
        sizes.append(passage.terms.lexemes.total())
    avg_size = sum(sizes) / len(passages) or 1
    idf = {word: log1p((len(passages) - count + 0.5) / (count + 0.5))
           for word, count in df.items()}
    scores = {}
    for passage, size in zip(passages, sizes, strict=True):
        frequencies = passage.terms.lexemes
        denominator = 1.2 * (0.25 + 0.75 * size / avg_size)
        score = sum(frequencies[word] * 2.2 * idf[word] / (frequencies[word] + denominator)
                    for word in sorted(words & frequencies.keys()))
        if score >= LEXICAL_THRESHOLD:
            scores[passage.id] = score
    return rank_branch(prepared, scores, "lexical", LEXICAL_THRESHOLD)


def rank_branch(prepared: Prepared, scores: dict[UUID, float], kind: str, threshold: float) -> list[Ranked]:
    matches = [Ranked(prepared.passages[chunk_id], score, kind) for chunk_id, score in scores.items()
               if chunk_id in prepared.passages and score >= threshold]
    matches.sort(key=lambda match: (-match.score, match.passage.document.code,
                                    match.passage.chunk.start, match.passage.id))
    best: dict[UUID, Ranked] = {}
    for match in matches:
        best.setdefault(match.passage.document.candidate_id, match)
    return list(best.values())


def fuse(lexical: list[Ranked], semantic: list[Ranked]) -> list[Ranked]:
    items: dict[UUID, list[tuple[int, Ranked]]] = {}
    for branch in (lexical, semantic):
        for rank, hit in enumerate(branch, start=1):
            items.setdefault(hit.passage.document.candidate_id, []).append((rank, hit))
    results = []
    for ranks in items.values():
        _, best = min(ranks, key=lambda pair: pair[0])
        score = sum(1 / (RRF_K + rank) for rank, _ in ranks)
        results.append(Ranked(best.passage, score, "hybrid" if len(ranks) == 2 else best.kind))
    return sorted(results, key=lambda hit: (-hit.score, hit.passage.document.code))
