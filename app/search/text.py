"""Нарезка очищенного текста и правила совпадения терминов."""
import re
import unicodedata
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from pymorphy3 import MorphAnalyzer

from app.db.enums import ChunkKind

CHUNK_VERSION = "chunk-v1"
MAX_BYTES = 440
OVERLAP_BYTES = 80
MIN_PREFERRED_BYTES = 240

HEADINGS = {
    "опыт работы": ChunkKind.EXPERIENCE,
    "ключевые навыки": ChunkKind.SKILLS,
    "навыки": ChunkKind.SKILLS,
    "образование": ChunkKind.EDUCATION,
    "обо мне": ChunkKind.ABOUT,
    "о себе": ChunkKind.ABOUT,
    "сопроводительное письмо": ChunkKind.COVER_LETTER,
}
FOOTER = re.compile(
    r"^(?:история общения с кандидатом(?:\s*:|$)|отклик на вакансию\s*:"
    r"|(?:фио\b.*?[•·]\s*)?резюме обновлено\b)", re.IGNORECASE
)
DASHES = str.maketrans({char: "-" for char in "‐‑‒–—―−"})
DASH_IN_CODE = re.compile(r"(?<=\d)\s*-\s*(?=[^\W_])")
TOKEN = re.compile(
    r"(?<![\w+#])(?:\d+(?:-[^\W_]+)+|\.?[\w]+(?:\.[\w]+)*(?:\+\+|#)?)(?![\w+#])"
)
RUSSIAN_WORD = re.compile(r"[а-я]+")
CLAUSE_BREAK = re.compile(r"[\r\n,;!?]|\.(?=\s|$)")
NEGATION = re.compile(
    r"(?<!\w)(?:не\s+работал(?:а|и)?\s+с|нет\s+опыта(?:\s+с)?"
    r"|без\s+опыта(?:\s+с)?)\s+"
)
STOPS = frozenset(
    "а без был быть в во вы для до его ее если же за и из или их к как ко ли мне мы на над "
    "не ни но о об от по под при про с со так то у уже что это я".split()
)


@dataclass(frozen=True, slots=True)
class Chunk:
    kind: ChunkKind
    index: int
    start: int
    end: int
    text: str


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е").translate(DASHES)
    return DASH_IN_CODE.sub("-", value)


def exact_tokens(value: str) -> tuple[str, ...]:
    return tuple(match.group() for match in TOKEN.finditer(normalize(value))
                 if any(char.isalnum() for char in match.group()))


@lru_cache(maxsize=1)
def _morphology() -> MorphAnalyzer:
    return MorphAnalyzer()


@lru_cache(maxsize=16384)
def _lemma(word: str) -> str:
    if RUSSIAN_WORD.fullmatch(word):
        return _morphology().parse(word)[0].normal_form.replace("ё", "е")
    return word


def _significant(words) -> list[str]:
    return [lemma for word in words if word not in STOPS and (lemma := _lemma(word)) not in STOPS]


@dataclass(slots=True)
class ChunkTerms:
    positive: tuple[tuple[str, ...], ...]
    negative: frozenset[str]
    lexemes: Counter[str]

    def has(self, term: tuple[str, ...]) -> bool:
        return any(
            clause[i:i + len(term)] == term
            for clause in self.positive
            for i in range(len(clause) - len(term) + 1)
        )


def chunk_terms(value: str) -> ChunkTerms:
    positive = []
    negative = set()
    for phrase in CLAUSE_BREAK.split(normalize(value)):
        denial = NEGATION.search(phrase)
        if denial:
            negative.update(_significant(exact_tokens(phrase[denial.end():])))
            phrase = phrase[:denial.start()]
        words = exact_tokens(phrase)
        if words:
            positive.append(words)
    return ChunkTerms(tuple(positive), frozenset(negative),
                      Counter(_significant(word for words in positive for word in words)))


def query_terms(value: str) -> frozenset[str]:
    return frozenset(_significant(exact_tokens(value)))


def _sections(value: str):
    kind = ChunkKind.FULL
    start = position = 0
    for line in value.splitlines(keepends=True):
        key = " ".join(normalize(line).split())
        if FOOTER.match(key):
            yield kind, start, position
            return
        heading = HEADINGS.get(key.rstrip(":").rstrip())
        if heading:
            yield kind, start, position
            kind = heading
            start = position + len(line)
        position += len(line)
    yield kind, start, len(value)


def _windows(value: str):
    # Индекс байт UTF-8 позволяет ограничить размер, не разрезая Unicode-символ.
    byte_offsets = [0]
    for char in value:
        byte_offsets.append(byte_offsets[-1] + len(char.encode("utf-8")))
    start = 0
    while start < len(value):
        end = bisect_right(byte_offsets, byte_offsets[start] + MAX_BYTES) - 1
        if end < len(value):
            preferred = bisect_left(byte_offsets, byte_offsets[start] + MIN_PREFERRED_BYTES)
            breaks = [match.end() + preferred
                      for match in re.finditer(r"[.!?](?=\s)|\n", value[preferred:end])]
            spaces = [match.end() + preferred for match in re.finditer(r"\s", value[preferred:end])]
            end = (breaks or spaces or [end])[-1]
        left = start
        right = end
        while left < right and value[left].isspace():
            left += 1
        while right > left and value[right - 1].isspace():
            right -= 1
        if left < right:
            yield left, right
        if end == len(value):
            break
        overlap_start = bisect_left(byte_offsets, byte_offsets[end] - OVERLAP_BYTES)
        # Перекрытие начинается на границе слова, если такая граница есть.
        start = next(
            (at for at in range(overlap_start, end)
             if at == 0 or not value[at - 1].isalnum() or not value[at].isalnum()),
            overlap_start,
        )


def split_chunks(value: str) -> tuple[Chunk, ...]:
    sections = Counter()
    chunks = []
    for kind, start, end in _sections(value):
        for left, right in _windows(value[start:end]):
            fragment = value[start + left:start + right]
            if not any(char.isalnum() for char in fragment):
                continue
            chunks.append(Chunk(kind, sections[kind], start + left, start + right, fragment))
            sections[kind] += 1
    return tuple(chunks)
