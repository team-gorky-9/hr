"""Загрузка профилей требований из файлового пакета stage-0b-01 (формат requirement-profile-review/0.2).

Что делает:
1. Загружает документы из манифеста sources.json в source_documents: байты берёт из папки
   архива «Кадры», сверяет SHA-256 с манифестом, текст собирает из абзацев манифеста.
2. Для каждого профиля пакета вызывает create_requirement_profile: ключи строк, происхождение,
   обязательность, способ и этап проверки (check_stage, v1.5), критерии выполнения и params 0.1
   переносятся в базу. params проверяются по формату 0.1 при создании профиля.
3. С --synthetic дополнительно загружает учебный профиль из synthetic/cases.json (is_synthetic = true).
   Версии нумеруются в своём контуре, поэтому учебный python-dev v2 не конфликтует с рабочим v2.
4. Печатает, сколько строк загружено и какие поля пакета в базу не переносятся
   (они остаются в пакете для ревью: evidence_channels, mandatory_basis…).

Всё выполняется в одной транзакции. Без --commit она откатывается: так проверяется,
что пакет укладывается в схему, без изменения базы.

    uv run python -m scripts.load_requirement_profiles <profiles.draft.json> <sources.json> "<папка Кадры>" \
        [--synthetic <synthetic/cases.json>] [--commit]
"""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import repository as repo
from app.db.enums import Channel, DocumentKind, FileFormat, SourceRole
from app.db.models import Position, RequirementProfile
from app.db.session import SessionLocal
from app.schemas.requirements import (
    CompetencyIn,
    FormalRequirementIn,
    IndicatorIn,
    ProfileSourceIn,
    SourceRefIn,
)

SUPPORTED_PACKAGE = "requirement-profile-review/0.2"
IMPORT_BATCH = "requirement-profiles"

# Поля строк пакета, которые переносятся в базу. Остальные перечисляются в отчёте как оставшиеся в пакете.
FORMAL_FIELDS = {"key", "text", "kind", "params", "is_mandatory", "verification", "check_stage", "origin",
                 "source_refs", "rationale", "acceptance"}
COMPETENCY_FIELDS = {"key", "text", "code", "rank", "target_level_min", "target_level_max", "origin",
                     "source_refs", "rationale", "indicators"}
INDICATOR_FIELDS = {"key", "text", "is_mandatory", "verification", "check_stage", "origin", "source_refs",
                    "rationale", "acceptance", "excluded_from_scoring", "sort_order"}

DOCUMENT_KIND = {
    "job_description": DocumentKind.JOB_DESCRIPTION,
    "competency_matrix": DocumentKind.COMPETENCY_MATRIX,
    "vacancy_posting": DocumentKind.VACANCY_POSTING,
}


def paragraph_order(paragraph_id: str) -> int:
    """«P12» → 12, «L3» → 3: абзацы манифеста идут по номеру, а не по алфавиту."""
    return int(paragraph_id[1:])


def load_sources(session: Session, manifest: dict[str, Any], kadry_root: Path) -> dict[str, Any]:
    """Документы манифеста → source_documents. Возвращает {source_id: документ}."""
    documents = {}
    for item in manifest["documents"]:
        path = kadry_root / item["path"]
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != item["sha256"]:
            raise SystemExit(f"{item['id']}: SHA-256 файла {digest} не совпадает с манифестом {item['sha256']}")
        paragraphs = item["paragraphs"]
        raw_text = "\n".join(paragraphs[p] for p in sorted(paragraphs, key=paragraph_order))
        suffix = path.suffix.lower()
        document, _ = repo.add_source_document(
            session,
            kind=DOCUMENT_KIND.get(item["kind"], DocumentKind.OTHER),
            # Вакансия выгружена с hh.ru; ДИ и матрица — внутренние документы администрации и АЦГ.
            channel=Channel.HH_RU if item["kind"] == "vacancy_posting" else Channel.INTERNAL,
            file_format=FileFormat.DOCX if suffix == ".docx" else FileFormat.TXT,
            original_path=item["path"],
            raw_text=raw_text,
            content=content,
            import_batch=IMPORT_BATCH,
        )
        documents[item["id"]] = document
    return documents


def refs(row: dict[str, Any], documents: dict[str, Any]) -> list[SourceRefIn]:
    return [
        SourceRefIn(source_document_id=documents[ref["source_id"]].id, address=ref["address"], quote=ref["quote"])
        for ref in row["source_refs"]
    ]


def row_source(row: dict[str, Any], documents: dict[str, Any]) -> dict[str, Any]:
    """Общие поля строки. rationale пакета → note базы (для строк команды это обязательное обоснование)."""
    return {"key": row["key"], "origin": row["origin"], "source_refs": refs(row, documents),
            "note": row.get("rationale")}


def unloaded(row: dict[str, Any], loaded: set[str], counter: Counter) -> None:
    counter.update(set(row) - loaded)


def build_profile(profile: dict[str, Any], documents: dict[str, Any], skipped: Counter) -> dict[str, Any]:
    formal = []
    for row in profile["formal_requirements"]:
        unloaded(row, FORMAL_FIELDS, skipped)
        formal.append(FormalRequirementIn(
            kind=row["kind"], description=row["text"], params=row.get("params") or {},
            is_mandatory=row["is_mandatory"], verification=row["verification"], check_stage=row.get("check_stage"),
            acceptance=row.get("acceptance") or {}, **row_source(row, documents),
        ))
    competencies = []
    for group in profile["competencies"]:
        unloaded(group, COMPETENCY_FIELDS, skipped)
        indicators = []
        # Порядок индикаторов — как в пакете: sort_order пакета для строк матрицы совпадает с ним.
        for row in group["indicators"]:
            unloaded(row, INDICATOR_FIELDS, skipped)
            indicators.append(IndicatorIn(
                text=row["text"], is_mandatory=row["is_mandatory"], verification=row["verification"],
                check_stage=row.get("check_stage"), acceptance=row.get("acceptance") or {},
                excluded_from_scoring=row.get("excluded_from_scoring", False),
                **row_source(row, documents),
            ))
        competencies.append(CompetencyIn(
            code=group["code"], name=group["text"], rank=group["rank"],
            target_level_min=group["target_level_min"], target_level_max=group["target_level_max"],
            indicators=indicators, **row_source(group, documents),
        ))
    sources = [
        ProfileSourceIn(source_document_id=documents[s["source_id"]].id, role=SourceRole(s["role"]),
                        observed_revision=s.get("revision"), is_primary=s["role"] == "job_description")
        for s in profile["sources"]
    ]
    return {"formal_requirements": formal, "competencies": competencies, "sources": sources}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # консоль Windows по умолчанию не в UTF-8
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("package", type=Path, help="profiles.draft.json")
    parser.add_argument("manifest", type=Path, help="sources.json")
    parser.add_argument("kadry_root", type=Path, help="папка «Кадры» распакованного архива")
    parser.add_argument("--synthetic", type=Path, help="synthetic/cases.json: загрузить и учебный профиль")
    parser.add_argument("--created-by", default="stage-0b-01")
    parser.add_argument("--commit", action="store_true", help="сохранить; без флага транзакция откатывается")
    args = parser.parse_args()

    package = json.loads(args.package.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if package["package_schema"] != SUPPORTED_PACKAGE:
        raise SystemExit(f"формат пакета {package['package_schema']} не поддерживается, ожидается {SUPPORTED_PACKAGE}")

    profiles = list(package["profiles"])
    if args.synthetic:
        training = json.loads(args.synthetic.read_text(encoding="utf-8"))["synthetic_profile"]
        if training.get("is_synthetic") is not True:
            raise SystemExit("в synthetic/cases.json профиль не помечен is_synthetic = true")
        profiles.append(training)

    skipped: Counter = Counter()
    with SessionLocal() as session:
        documents = load_sources(session, manifest, args.kadry_root)
        print(f"документов: {len(documents)}")
        for profile in profiles:
            position_id = session.scalar(select(Position.id).where(Position.code == profile["position_code"]))
            if position_id is None:
                raise SystemExit(f"нет должности {profile['position_code']}: запустите python -m app.db.seed")
            contour = "учебный" if profile["is_synthetic"] else "рабочий"
            exists = session.scalar(select(RequirementProfile.id).where(
                RequirementProfile.position_id == position_id,
                RequirementProfile.is_synthetic == profile["is_synthetic"],
                RequirementProfile.version == profile["version"]))
            if exists is not None:
                raise SystemExit(f"{profile['position_code']} {contour} v{profile['version']} уже загружен: "
                                 "загруженную версию не переписываем, изменения — новой версией пакета")
            loaded = repo.create_requirement_profile(
                session, position_id=position_id, version=profile["version"], created_by=args.created_by,
                is_synthetic=profile["is_synthetic"],
                note=f"{package['package_schema']}, {profile['key']}",
                **build_profile(profile, documents, skipped),
            )
            indicators = [i for c in loaded.competencies for i in c.indicators]
            stages = Counter(r.check_stage.value for r in [*loaded.formal_requirements, *indicators])
            print(
                f"{profile['position_code']} {contour} v{loaded.version} ({loaded.status.value}): "
                f"условий {len(loaded.formal_requirements)}, компетенций {len(loaded.competencies)}, "
                f"индикаторов {len(indicators)}, из них не в оценке {sum(i.excluded_from_scoring for i in indicators)}; "
                f"этапы проверки: {dict(sorted(stages.items()))}"
            )
        print("поля пакета, оставшиеся только в пакете:",
              ", ".join(f"{name} ({count})" for name, count in sorted(skipped.items())) or "нет")
        if args.commit:
            session.commit()
            print("сохранено")
        else:
            session.rollback()
            print("проверка без сохранения: транзакция откатена")


if __name__ == "__main__":
    main()
