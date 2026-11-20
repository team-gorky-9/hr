"""Извлечение плоского текста из TXT, DOCX и текстовых PDF.

Логика повторяет hr/app/ingest/extract.py:
- TXT: UTF-32/UTF-16 с BOM, UTF-8-SIG, затем Windows-1251;
- DOCX: XML абзацев и таблиц без дублирования объединённых ячеек, защита от DTD/ZIP-бомбы;
- PDF: pypdf по страницам; отсутствие текстового слоя → статус unavailable (скан, нужен ручной ввод).
"""
from dataclasses import dataclass
import io
import re
from typing import Literal
import unicodedata
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_DOCX_XML = 128 * 1024 * 1024


class ExtractError(Exception):
    """Сбой или недоступность извлечения текста из исходного файла."""

    def __init__(self, code: str, message: str, *, unavailable: bool = False) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.unavailable = unavailable


@dataclass(frozen=True)
class ExtractionOutcome:
    """Результат попытки извлечения текста из загруженного источника."""

    status: Literal["ready", "unavailable", "failed"]
    extracted_text: str | None
    reason: str | None


def normalize_text(text: str) -> str:
    """Нормализовать Unicode к NFC и привести переводы строк к \\n."""
    return unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")


def decode_txt(data: bytes) -> str:
    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return data.decode("utf-32")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return data.decode("cp1251")
        except UnicodeDecodeError as exc:
            raise ExtractError("TEXT_ENCODING", "не удалось декодировать текстовый файл") from exc


def _paragraph_text(element: ET.Element) -> str:
    parts: list[str] = []
    for node in element.iter():
        if node.tag == W + "t":
            parts.append(node.text or "")
        elif node.tag == W + "tab":
            parts.append("\t")
        elif node.tag in (W + "br", W + "cr"):
            parts.append("\n")
    return "".join(parts)


def _docx_blocks(element: ET.Element):
    for child in element:
        if child.tag == W + "p":
            yield _paragraph_text(child)
        elif child.tag == W + "tbl":
            for row in child.findall(W + "tr"):
                yield "\t".join("\n".join(_docx_blocks(cell)) for cell in row.findall(W + "tc"))
        else:
            yield from _docx_blocks(child)


def docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as doc:
            names = doc.namelist()
            if "word/document.xml" not in names:
                raise ExtractError("DOCX_INVALID", "в архиве нет word/document.xml")
            parts = ["word/document.xml"] + sorted(
                n for n in names
                if re.fullmatch(r"word/(header\d+|footer\d+|footnotes|endnotes|comments)\.xml", n)
            )
            if sum(doc.getinfo(n).file_size for n in parts) > MAX_DOCX_XML:
                raise ExtractError("DOCX_TOO_LARGE", "XML документа слишком большой")
            blocks: list[str] = []
            for part in parts:
                xml = doc.read(part)
                if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                    raise ExtractError("DOCX_INVALID", "в XML есть объявления DTD/ENTITY")
                blocks.extend(_docx_blocks(ET.fromstring(xml)))
    except zipfile.BadZipFile as exc:
        raise ExtractError("DOCX_INVALID", "файл не является ZIP-архивом DOCX") from exc
    except ET.ParseError as exc:
        raise ExtractError("DOCX_INVALID", "XML документа повреждён") from exc
    return "\n".join(block for block in blocks if block.strip())


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, Exception) as exc:
        raise ExtractError("PDF_INVALID", "PDF не читается") from exc
    if not pages or any(not text.strip() for text in pages):
        raise ExtractError(
            "PDF_NEEDS_REVIEW",
            "страница без текстового слоя (скан), требуется ручной ввод текста",
            unavailable=True,
        )
    return "\n\n".join(pages)


def extract_source_text(data: bytes, extension: str) -> ExtractionOutcome:
    """Извлечь текст из загруженного файла; никогда не скрывать ошибку пустой строкой."""
    ext = extension.lower()
    try:
        if ext == ".txt":
            raw_text = decode_txt(data)
        elif ext == ".docx":
            raw_text = docx_text(data)
        elif ext == ".pdf":
            raw_text = pdf_text(data)
        elif ext in {".png", ".jpg", ".jpeg"}:
            return ExtractionOutcome(
                status="unavailable",
                extracted_text=None,
                reason="SCAN_NEEDS_REVIEW: изображение без текстового слоя, требуется ручной ввод текста",
            )
        else:
            return ExtractionOutcome(
                status="failed",
                extracted_text=None,
                reason=f"UNSUPPORTED_FORMAT: формат {ext or 'без расширения'} не поддерживается",
            )
        text = normalize_text(raw_text)
        if "\x00" in text:
            return ExtractionOutcome(
                status="failed",
                extracted_text=None,
                reason="TEXT_ENCODING: в тексте обнаружены нулевые байты",
            )
        if not text.strip():
            status = "unavailable" if ext == ".pdf" else "failed"
            return ExtractionOutcome(
                status=status,
                extracted_text=None,
                reason="EMPTY_TEXT: извлечённый текст пуст",
            )
        return ExtractionOutcome(status="ready", extracted_text=text, reason=None)
    except ExtractError as exc:
        return ExtractionOutcome(
            status="unavailable" if exc.unavailable else "failed",
            extracted_text=None,
            reason=f"{exc.code}: {exc.message}",
        )
