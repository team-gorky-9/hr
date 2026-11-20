"""Воспроизводимое сравнение способов на предварительно размеченном учебном корпусе."""
import hashlib
import json
import os
import platform
from dataclasses import dataclass
from importlib.metadata import version
from math import ceil
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import NAMESPACE_URL, UUID, uuid5

from app.search.encoder import Encoder
from app.search.ranking import Document, Prepared, Ranked, bm25, fuse, passage_id, prepare, rank_branch
from app.search.service import evidence_of
from app.search.text import split_chunks

DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "search" / "synthetic-v1.json"
GRID = [step / 100 for step in range(70, 95, 2)]
MODES = ("lexical", "dense", "hybrid")


@dataclass(slots=True)
class Case:
    id: str
    split: str
    query: str
    required_terms: list[str]
    relevant: dict[str, list[str]]
    paraphrase: bool


def _documents(data: dict) -> list[Document]:
    namespace = uuid5(NAMESPACE_URL, data["version"])
    docs = [Document(uuid5(namespace, row["code"]), row["code"],
                     uuid5(namespace, row["code"] + ":text"), row["text"])
            for row in data["documents"]]
    if len({doc.code for doc in docs}) != len(docs):
        raise ValueError("Повтор кода кандидата в наборе")
    return docs


def _cases(data: dict, documents: list[Document]) -> list[Case]:
    cases = [Case(**row) for row in data["queries"]]
    docs = {doc.code: split_chunks(doc.text) for doc in documents}
    if len({case.id for case in cases}) != len(cases) or len({case.query for case in cases}) != len(cases):
        raise ValueError("Запросы и идентификаторы в разметке должны быть уникальными")
    if {case.split for case in cases} != {"calibration", "control"}:
        raise ValueError("Нужны отдельные калибровочная и контрольная группы")
    for case in cases:
        for code, fragments in case.relevant.items():
            if not fragments or not any(part in chunk.text for part in fragments for chunk in docs.get(code, [])):
                raise ValueError(f"{case.id}: нет проверяемой цитаты для {code}")
    return cases


def _dense(encoder: Encoder, query: str, prepared: Prepared,
           vectors: dict[UUID, list[float]]) -> dict[UUID, float]:
    if not prepared.passages:
        return {}
    import numpy as np
    ids = list(prepared.passages)
    query_vector = np.asarray(encoder.query(query), dtype=np.float32)
    corpus = np.asarray([vectors[chunk_id] for chunk_id in ids], dtype=np.float32)
    # E5 возвращает нормированные векторы, поэтому произведение равно cosine.
    values = corpus @ query_vector
    return dict(zip(ids, map(float, values), strict=True))


def _negative_false_positives(cases: list[Case], ranks: dict[str, list[Ranked]]) -> int:
    return sum(bool(ranks[case.id]) for case in cases if not case.relevant)


def calibrate(cases: list[Case], documents: list[Document], encoder: Encoder,
              vectors: dict[UUID, list[float]]) -> tuple[float, list[dict]]:
    prepared = {case.id: prepare(documents, case.query, case.required_terms) for case in cases}
    lexical = {case.id: bm25(prepared[case.id]) for case in cases}
    scores = {case.id: _dense(encoder, case.query, prepared[case.id], vectors) for case in cases}
    false_positive_bound = _negative_false_positives(cases, lexical)
    grid = []
    for threshold in GRID:
        hybrids = {case.id: fuse(lexical[case.id], rank_branch(
            prepared[case.id], scores[case.id], "semantic", threshold)) for case in cases}
        found = sum(
            hit.passage.document.code in case.relevant
            for case in cases
            for hit in hybrids[case.id][:5]
        )
        false_positives = _negative_false_positives(cases, hybrids)
        grid.append({"threshold": threshold, "relevant_at_5": found,
                     "negative_with_results": false_positives,
                     "accepted": false_positives <= false_positive_bound})
    acceptable = [row for row in grid if row["accepted"]]
    if not acceptable:
        raise ValueError("Ни один порог из сетки не прошёл калибровку")
    best = max(acceptable, key=lambda row: (row["relevant_at_5"], row["threshold"]))
    return best["threshold"], grid


def _case_result(case: Case, results: list[Ranked]) -> dict:
    returned = []
    for hit in results[:10]:
        passage = hit.passage
        evidence = evidence_of(passage)
        doc = passage.document
        assert evidence is not None
        encoded = doc.text.encode("utf-16-le")
        utf16_slice = encoded[evidence.utf16_start * 2:evidence.utf16_end * 2].decode("utf-16-le")
        returned.append({
            "code": doc.code,
            "score": hit.score,
            "kind": hit.kind,
            "relevant": doc.code in case.relevant,
            "citation_relevant": any(part in evidence.fragment for part in case.relevant.get(doc.code, [])),
            "offsets_valid": doc.text[evidence.start_offset:evidence.end_offset] == evidence.fragment == utf16_slice,
            "fragment": evidence.fragment,
        })
    returned_relevant = {row["code"] for row in returned if row["relevant"]}
    return {"id": case.id, "query": case.query, "required_terms": case.required_terms,
            "expected": list(case.relevant), "hits": returned,
            "missing": sorted(set(case.relevant) - returned_relevant),
            "paraphrase": case.paraphrase}


def _metrics(cases: list[dict], times: list[float]) -> dict:
    positives = [row for row in cases if row["expected"]]
    negatives = [row for row in cases if not row["expected"]]
    hits = [hit for row in cases for hit in row["hits"]]
    positive_citations = [hit for hit in hits if hit["relevant"]]
    return {
        "precision_at_5": sum(sum(hit["relevant"] for hit in row["hits"][:5])
                              for row in positives) / (len(positives) * 5),
        "precision_at_10": sum(sum(hit["relevant"] for hit in row["hits"])
                               for row in positives) / (len(positives) * 10),
        "returned_total_at_10": len(hits),
        "relevant_returned_at_10": len(positive_citations),
        "relevant_missed_at_10": sum(len(row["missing"]) for row in cases),
        "negative_with_results": sum(bool(row["hits"]) for row in negatives),
        "negative_total": len(negatives),
        "relevant_citations": sum(hit["citation_relevant"] for hit in positive_citations),
        "valid_offsets": sum(hit["offsets_valid"] for hit in hits),
        "warm_median_ms": median(times),
        "warm_p95_ms": sorted(times)[ceil(len(times) * 0.95) - 1],
        "timed_requests": len(times),
    }


def _measure(cases: list[Case], documents: list[Document], encoder: Encoder,
             vectors: dict[UUID, list[float]], mode: str, threshold: float, repeats: int) -> dict:
    times = []
    results = []
    for iteration in range(repeats):
        for case in cases:
            start = perf_counter()
            prepared = prepare(documents, case.query, case.required_terms)
            lexical = bm25(prepared) if mode != "dense" else []
            semantic = rank_branch(prepared, _dense(encoder, case.query, prepared, vectors),
                                   "semantic", threshold) if mode != "lexical" else []
            if mode == "hybrid":
                ranked = fuse(lexical, semantic)
            else:
                ranked = lexical or semantic
            times.append((perf_counter() - start) * 1000)
            if iteration == 0:
                results.append(_case_result(case, ranked))
    return {"metrics": _metrics(results, times), "queries": results}


def evaluate(path: Path, encoder: Encoder, *, repeats: int, cold_start_ms: float) -> dict:
    payload = path.read_bytes()
    data = json.loads(payload)
    documents = _documents(data)
    cases = _cases(data, documents)
    chunks = [(passage_id(doc.candidate_text_id, chunk), chunk.text)
              for doc in documents for chunk in split_chunks(doc.text)]
    index_start = perf_counter()
    values = encoder.passages([value for _, value in chunks])
    index_ms = (perf_counter() - index_start) * 1000
    vectors = {chunk_id: value for (chunk_id, _), value in zip(chunks, values, strict=True)}
    calibration = [case for case in cases if case.split == "calibration"]
    threshold, grid = calibrate(calibration, documents, encoder, vectors)
    control = [case for case in cases if case.split == "control"]
    methods = {mode: _measure(control, documents, encoder, vectors, mode, threshold, repeats) for mode in MODES}
    lex, hybrid = methods["lexical"], methods["hybrid"]
    added = []
    for base, mixed in zip(lex["queries"], hybrid["queries"], strict=True):
        if mixed["paraphrase"]:
            old = {hit["code"] for hit in base["hits"] if hit["relevant"]}
            added.extend((mixed["id"], hit["code"]) for hit in mixed["hits"]
                         if hit["relevant"] and hit["code"] not in old)
    base_metrics, mixed_metrics = lex["metrics"], hybrid["metrics"]
    passes_local_rule = (
        bool(added)
        and mixed_metrics["precision_at_5"] >= base_metrics["precision_at_5"]
        and mixed_metrics["precision_at_10"] >= base_metrics["precision_at_10"]
        and mixed_metrics["negative_with_results"] <= base_metrics["negative_with_results"]
    )
    return {
        "data_version": data["version"], "data_sha256": hashlib.sha256(payload).hexdigest(),
        "model": encoder.model, "dimensions": encoder.dimensions, "documents": len(documents),
        "chunks": len(chunks), "scope": "synthetic in-memory, without PostgreSQL/HTTP",
        "python": platform.python_version(), "platform": platform.platform(),
        "logical_cpus": os.cpu_count(), "omp_num_threads": os.getenv("OMP_NUM_THREADS"),
        "packages": {name: version(name) for name in ("torch", "transformers", "sentence-transformers", "numpy")},
        "cold_model_load_ms": cold_start_ms, "vectorize_ms": index_ms, "threshold": threshold,
        "calibration": {"queries": [case.id for case in calibration], "grid": grid},
        "control": methods, "hybrid_added_paraphrase_hits": added, "hybrid_meets_local_rule": passes_local_rule,
    }
