"""Точки входа оператора: python -m app.search --help."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter

from sqlalchemy.exc import SQLAlchemyError

from app.api.schemas import Contour
from app.db.session import SessionLocal
from app.search.encoder import MODEL_FILES, MODEL_ID, MODEL_REVISION, EncoderUnavailable, get_local_encoder
from app.search.evaluation import DEFAULT_FIXTURE, evaluate
from app.search.storage import index_document, index_targets


def _prepare_model(_: argparse.Namespace) -> None:
    from huggingface_hub import snapshot_download

    path = snapshot_download(MODEL_ID, revision=MODEL_REVISION, allow_patterns=MODEL_FILES)
    print(path)


def _index(args: argparse.Namespace) -> None:
    contour = Contour(args.contour)
    with SessionLocal() as session:
        targets = index_targets(session, contour, args.candidate_code)
    if args.candidate_code and not targets:
        raise ValueError("В выбранном контуре нет такого кандидата с текущим очищенным текстом")
    encoder = get_local_encoder()
    counts = Counter(indexed=0, unchanged=0, stale=0)
    chunks = 0
    for target in targets:
        with SessionLocal.begin() as session:
            result = index_document(session, target, contour, encoder)
        counts[result.action] += 1
        chunks += result.chunks
    print(json.dumps({"contour": contour, "model": encoder.model, "dimensions": encoder.dimensions,
                      "texts": len(targets), "chunks": chunks, **counts}, ensure_ascii=False))


def _evaluate(args: argparse.Namespace) -> None:
    start = perf_counter()
    encoder = get_local_encoder()
    result = evaluate(args.fixture, encoder, repeats=args.repeats, cold_start_ms=(perf_counter() - start) * 1000)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


def _load_demo(_: argparse.Namespace) -> None:
    from app.search.demo import load_demo

    with SessionLocal.begin() as session:
        counts = load_demo(session)
    print(json.dumps({"contour": "training", **counts}, ensure_ascii=False))


def _positive_int(value: str) -> int:
    count = int(value)
    if count < 1:
        raise argparse.ArgumentTypeError("Число повторов должно быть положительным")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Индексирование и оценка поиска кандидатов")
    commands = parser.add_subparsers(required=True)
    download = commands.add_parser("prepare-model", help="скачать закреплённую модель в локальный кэш")
    download.set_defaults(run=_prepare_model)
    index = commands.add_parser("index", help="индексировать текущие очищенные тексты в pgvector")
    index.add_argument("--contour", required=True, choices=[contour.value for contour in Contour])
    index.add_argument("--candidate-code")
    index.set_defaults(run=_index)
    demo = commands.add_parser("load-demo", help="загрузить синтетический корпус поиска в учебный контур")
    demo.set_defaults(run=_load_demo)
    benchmark = commands.add_parser("evaluate", help="сравнить методы на фиксированной синтетической разметке")
    benchmark.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    benchmark.add_argument("--output", type=Path)
    benchmark.add_argument("--repeats", type=_positive_int, default=3)
    benchmark.set_defaults(run=_evaluate)
    args = parser.parse_args()
    try:
        args.run(args)
    except (EncoderUnavailable, SQLAlchemyError, OSError, ImportError, ValueError) as exc:
        if isinstance(exc, SQLAlchemyError):
            print("Операция прервана. Проверьте PostgreSQL и миграции; повтор безопасен.", file=sys.stderr)
        elif isinstance(exc, ImportError):
            print("Установите зависимости локальной модели из requirements-search.txt.", file=sys.stderr)
        else:
            print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
