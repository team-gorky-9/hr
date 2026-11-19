"""Чтение входного пакета и решение, что делать с каждым файлом.

Пакет бывает двух видов (контракт импорта, п. 2.1):
1. выгрузка штабного парсера: `corpus.jsonl` + `originals/` (+ `summary.json` с ошибками);
2. обычная папка с файлами `.txt` / `.docx` / `.pdf`.

Для каждого файла нужно знать: это резюме или служебный документ, на какую должность
отклик и какой у кандидата код. Источник ответа (п. 2.2):
- явная запись `entries` в `mapping.json` для этого пути — главнее всего;
- иначе словарь `folders` из `mapping.json`: имя папки → код должности. Папку можно
  переименовать, поправив только этот словарь, без изменений кода;
- если папки нет в словаре — значения по умолчанию `POSITION_CODE_BY_FOLDER` из `app/db/seed.py`
  (имена папок архива «Кадры»);
- тип документа — по имени файла. Должность по тексту резюме не угадываем.
"""
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import Channel, DocumentKind, FileFormat
from app.db.seed import POSITION_CODE_BY_FOLDER
from app.ingest.extract import ExtractError, extract_text, normalize_text

# Префиксы кодов кандидатов по должностям (контракт БД, п. 2.9 и 11.2): py-0005.
CODE_PREFIX_BY_POSITION: dict[str, str] = {
    "junior-python-dev": "jpy",
    "python-dev": "py",
    "qa-manual": "qa",
    "frontend-dev": "fe",
    "junior-ux-ui": "ux",
    "hr-consultant": "hr",
}

SUPPORTED_EXTENSIONS = {".txt", ".docx", ".pdf"}
SKIPPED_NAMES = {"mapping.json", ".DS_Store", "Thumbs.db"}

# «отклик 5.txt» (IT-вакансии) и «Резюме 12.docx» (консультант) — так названы отклики в архиве.
RESUME_NAME = re.compile(r"(?i)^(?:отклик|резюме)\s*(\d+)\.(?:txt|docx|pdf)$")
# Файл уже назван кодом кандидата: «py-9001.txt».
CODE_NAME = re.compile(r"^([a-z]+)-(\d{4})\.(?:txt|docx|pdf)$")
CANDIDATE_CODE = re.compile(r"^[a-z]+-\d{4}$")


class Problem(Exception):
    """Файл нельзя импортировать без человека. `code` попадает в отчёт."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


# --- Вход --------------------------------------------------------------------

@dataclass
class InputFile:
    """Один файл пакета. Если текст достать не удалось, заполнен `extract_error`."""
    source_path: str               # путь в пакете, NFC, через «/»
    content: bytes | None          # байты оригинала (по ним считается SHA-256)
    text: str | None               # извлечённый и нормализованный текст
    extract_error: Problem | None = None

    @property
    def extension(self) -> str:
        return Path(self.source_path).suffix.lower()

    @property
    def sha256(self) -> str | None:
        return hashlib.sha256(self.content).hexdigest() if self.content is not None else None


def _nfc(path: str) -> str:
    return unicodedata.normalize("NFC", path.replace("\\", "/"))


def read_package(root: Path) -> list[InputFile]:
    """Прочитать пакет в любом из двух режимов. Порядок файлов — по пути, чтобы прогон был воспроизводим."""
    if (root / "corpus.jsonl").is_file():
        files = _read_parser_export(root)
    else:
        files = _read_folder(root)
    return sorted(files, key=lambda f: f.source_path)


def _read_parser_export(root: Path) -> list[InputFile]:
    files = []
    with (root / "corpus.jsonl").open(encoding="utf-8") as corpus:
        for line_number, line in enumerate(corpus, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            source_path = _nfc(record["source_path"])
            original = root / record["original_file"]
            if not original.is_file():
                files.append(InputFile(source_path, None, None,
                                       Problem("ORIGINAL_MISSING", f"нет файла оригинала (строка {line_number})")))
                continue
            content = original.read_bytes()
            item = InputFile(source_path, content, normalize_text(record["text"]))
            if record.get("sha256") and record["sha256"] != item.sha256:
                item.text = None
                item.extract_error = Problem("CORPUS_MISMATCH", "SHA-256 оригинала не совпадает с corpus.jsonl")
            files.append(item)

    # Документы, которые парсер не смог разобрать, тоже должны попасть в отчёт импорта.
    summary = root / "summary.json"
    if summary.is_file():
        for error in json.loads(summary.read_text(encoding="utf-8")).get("errors", []):
            source_path = _nfc(error["path"])
            original = root / "originals" / source_path
            content = original.read_bytes() if original.is_file() else None
            code = str(error.get("error", "PARSE_ERROR")).split(":", 1)[0] or "PARSE_ERROR"
            files.append(InputFile(source_path, content, None, Problem(code, "парсер не извлёк текст")))
    return files


def _read_folder(root: Path) -> list[InputFile]:
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name in SKIPPED_NAMES or path.name.startswith("."):
            continue
        relative = path.relative_to(root)
        if "__MACOSX" in relative.parts:
            continue
        source_path = _nfc(relative.as_posix())
        content = path.read_bytes()
        try:
            files.append(InputFile(source_path, content, extract_text(content, path.suffix)))
        except ExtractError as error:
            files.append(InputFile(source_path, content, None, Problem(error.code, str(error).split(": ", 1)[-1])))
    return files


# --- Сопоставление -----------------------------------------------------------

class MappingEntry(BaseModel):
    """Строка `mapping.json` (контракт импорта, п. 2.2). Незаполненные поля берутся из правил."""
    model_config = ConfigDict(extra="forbid")

    source_path: str
    document_kind: DocumentKind | None = None
    position_code: str | None = None
    candidate_code: str | None = Field(default=None, max_length=32)
    channel: Channel | None = None
    file_format: FileFormat | None = None


class Mapping(BaseModel):
    """Содержимое `mapping.json`: словарь папок и точечные записи по файлам."""
    model_config = ConfigDict(extra="forbid")
    folders: dict[str, str] = {}  # имя папки → код должности, например «Python-разработчик» → «python-dev»
    entries: list[MappingEntry] = []


def folder_key(name: str) -> str:
    """Имя папки для сравнения: NFC, без учёта регистра и лишних пробелов («Python  разработчик » = «python разработчик»)."""
    return " ".join(unicodedata.normalize("NFC", name).casefold().split())


@dataclass
class MappingConfig:
    """Загруженный `mapping.json`. Пустой — только правила и значения по умолчанию из seed."""
    entries: dict[str, MappingEntry] = field(default_factory=dict)
    folders: dict[str, str] = field(default_factory=dict)  # ключ — folder_key(имя папки)

    def position_for_folder(self, folder: str | None) -> str | None:
        if folder is None:
            return None
        key = folder_key(folder)
        if key in self.folders:
            return self.folders[key]
        return DEFAULT_POSITION_BY_FOLDER.get(key)


DEFAULT_POSITION_BY_FOLDER = {folder_key(name): code for name, code in POSITION_CODE_BY_FOLDER.items()}


def load_mapping(path: Path | None) -> MappingConfig:
    if path is None:
        return MappingConfig()
    mapping = Mapping.model_validate_json(path.read_text(encoding="utf-8"))
    return MappingConfig(
        entries={_nfc(entry.source_path): entry for entry in mapping.entries},
        folders={folder_key(name): code for name, code in mapping.folders.items()},
    )


@dataclass
class Route:
    """Что делать с файлом: тип документа, должность, код кандидата, канал и формат."""
    document_kind: DocumentKind
    channel: Channel
    file_format: FileFormat
    position_code: str | None = None
    candidate_code: str | None = None


def _resume_format(channel: Channel, extension: str) -> FileFormat:
    if channel == Channel.HH_RU and extension == ".txt":
        return FileFormat.HH_TXT
    if channel == Channel.HH_RU and extension == ".docx":
        return FileFormat.HH_DOCX
    return {".txt": FileFormat.TXT, ".docx": FileFormat.DOCX, ".pdf": FileFormat.PDF}.get(extension, FileFormat.OTHER)


def _plain_format(extension: str) -> FileFormat:
    return {".txt": FileFormat.TXT, ".docx": FileFormat.DOCX, ".pdf": FileFormat.PDF}.get(extension, FileFormat.OTHER)


def _kind_by_rules(file_name: str, folder: str | None) -> DocumentKind | None:
    """Тип документа по имени файла. None — правило не нашлось, решает человек."""
    if RESUME_NAME.match(file_name) or CODE_NAME.match(file_name):
        return DocumentKind.RESUME
    stem = Path(file_name).stem
    if stem.casefold() == "вакансия":
        return DocumentKind.VACANCY_POSTING
    if re.search(r"(?<![А-ЯЁа-яё])ДИ(?![А-ЯЁа-яё])", stem):
        return DocumentKind.JOB_DESCRIPTION
    if "матриц" in stem.casefold():
        return DocumentKind.COMPETENCY_MATRIX
    if folder is not None and folder.casefold() == "положения":
        return DocumentKind.REGULATION
    return None


def _candidate_code(file_name: str, position_code: str) -> str:
    code_match = CODE_NAME.match(file_name)
    if code_match:
        return f"{code_match.group(1)}-{code_match.group(2)}"
    number_match = RESUME_NAME.match(file_name)
    prefix = CODE_PREFIX_BY_POSITION.get(position_code)
    if number_match is None or prefix is None:
        raise Problem("MISSING_CANDIDATE_CODE", "код кандидата не задан в mapping и не выводится из имени файла")
    number = int(number_match.group(1))
    if number > 9999:
        raise Problem("MISSING_CANDIDATE_CODE", "номер отклика длиннее 4 цифр, задайте код в mapping")
    return f"{prefix}-{number:04d}"


def resolve_route(item: InputFile, mapping: MappingConfig) -> Route:
    """Решить, что делать с файлом. Неоднозначность — исключение `Problem` с причиной."""
    parts = item.source_path.split("/")
    file_name = parts[-1]
    folder = parts[-2] if len(parts) > 1 else None
    entry = mapping.entries.get(item.source_path)

    kind = entry.document_kind if entry and entry.document_kind else _kind_by_rules(file_name, folder)
    if kind is None:
        raise Problem("UNKNOWN_DOCUMENT_KIND", "тип документа не определён правилами, укажите его в mapping")

    if kind != DocumentKind.RESUME:
        default_channel = Channel.HH_RU if kind == DocumentKind.VACANCY_POSTING else Channel.INTERNAL
        channel = entry.channel if entry and entry.channel else default_channel
        file_format = entry.file_format if entry and entry.file_format else _plain_format(item.extension)
        return Route(kind, channel, file_format)

    position_code = entry.position_code if entry and entry.position_code else mapping.position_for_folder(folder)
    if position_code is None:
        raise Problem("UNKNOWN_POSITION", "папки нет в словаре folders, добавьте её в mapping.json")
    channel = entry.channel if entry and entry.channel else Channel.HH_RU
    file_format = entry.file_format if entry and entry.file_format else _resume_format(channel, item.extension)
    code = entry.candidate_code if entry and entry.candidate_code else _candidate_code(file_name, position_code)
    if not CANDIDATE_CODE.match(code):
        raise Problem("BAD_CANDIDATE_CODE", "код кандидата должен иметь вид «префикс-0000»")
    return Route(kind, channel, file_format, position_code, code)
