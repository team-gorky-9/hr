"""Извлечение плоского текста из TXT, DOCX и PDF.

Правила совпадают со штабным парсером архива (`tools/hr_archive_parser/parse_hr.py`),
чтобы текст из папки с файлами и текст из выгрузки парсера были одинаковыми:
- TXT: UTF-8, UTF-16/32 с BOM, иначе Windows-1251;
- DOCX: абзацы и таблицы из XML без дублирования объединённых ячеек
  (python-docx повторяет текст объединённой ячейки в каждой клетке);
- PDF: только текстовый слой; страница без текста — скан, нужен человек.
"""
import io
import re
import unicodedata
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_DOCX_XML = 128 * 1024 * 1024  # защита от «ZIP-бомбы» внутри DOCX


class ExtractError(Exception):
    """Текст извлечь нельзя. `code` — короткая причина для отчёта (например, PDF_NEEDS_REVIEW)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def normalize_text(text: str) -> str:
    """Unicode NFC и переносы строк `\\n` — так требует контракт импорта (п. 1, инвариант 4)."""
    return unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")


def decode_txt(data: bytes) -> str:
    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return data.decode("utf-32")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1251")


def _paragraph_text(element) -> str:
    parts = []
    for node in element.iter():
        if node.tag == W + "t":
            parts.append(node.text or "")
        elif node.tag == W + "tab":
            parts.append("\t")
        elif node.tag in (W + "br", W + "cr"):
            parts.append("\n")
    return "".join(parts)


def _docx_blocks(element):
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
                n for n in names if re.fullmatch(r"word/(header\d+|footer\d+|footnotes|endnotes|comments)\.xml", n)
            )
            if sum(doc.getinfo(n).file_size for n in parts) > MAX_DOCX_XML:
                raise ExtractError("DOCX_TOO_LARGE", "XML документа слишком большой")
            blocks = []
            for part in parts:
                xml = doc.read(part)
                if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                    raise ExtractError("DOCX_INVALID", "в XML есть объявления DTD/ENTITY")
                blocks.extend(_docx_blocks(ET.fromstring(xml)))
    except zipfile.BadZipFile as error:
        raise ExtractError("DOCX_INVALID", "файл не является ZIP-архивом DOCX") from error
    except ET.ParseError as error:
        raise ExtractError("DOCX_INVALID", "XML документа повреждён") from error
    return "\n".join(block for block in blocks if block.strip())


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as error:
        raise ExtractError("PDF_INVALID", "PDF не читается") from error
    if not pages or any(not text.strip() for text in pages):
        raise ExtractError("PDF_NEEDS_REVIEW", "страница без текстового слоя (скан), нужен OCR или человек")
    return "\n\n".join(pages)


def extract_text(data: bytes, extension: str) -> str:
    """Плоский текст файла по расширению (`.txt`, `.docx`, `.pdf`), уже нормализованный."""
    extension = extension.lower()
    if extension == ".txt":
        text = decode_txt(data)
    elif extension == ".docx":
        text = docx_text(data)
    elif extension == ".pdf":
        text = pdf_text(data)
    else:
        raise ExtractError("UNSUPPORTED_FORMAT", f"формат {extension or 'без расширения'} не поддерживается")
    text = normalize_text(text)
    if "\x00" in text:
        raise ExtractError("TEXT_ENCODING", "в тексте нулевые символы, кодировка определена неверно")
    if not text.strip():
        raise ExtractError("EMPTY_TEXT", "извлечённый текст пуст")
    return text
