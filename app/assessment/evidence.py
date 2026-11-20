"""Позиция цитаты считает код, а не модель (контракт assessment.md, инвариант 4; план ai-01, Р5).

Модель возвращает дословную фразу и, если фраза может повториться, кусок текста перед ней.
Код ищет её в очищенном тексте и пишет в Evidence точный срез text[start:end].

Поиск мягкий только в мелочах, которые модель часто «исправляет»: подряд идущие пробелы
и переводы строк, «ё»/«е», виды кавычек и тире. Найденный фрагмент всегда берётся из
исходного текста, поэтому text[start:end] == quote выполняется по построению.
"""
import uuid
from dataclasses import dataclass

from app.schemas.card import Evidence

_CHAR_MAP = str.maketrans({
    "ё": "е", "Ё": "Е",
    "«": '"', "»": '"', "„": '"', "“": '"', "”": '"', "‘": "'", "’": "'",
    "–": "-", "—": "-", "−": "-", "‑": "-",
    " ": " ",
})


def _normalize(text: str) -> tuple[str, list[int]]:
    """Нормализованная строка и для каждого её символа — индекс в исходной строке.
    Пробельные символы подряд схлопываются в один пробел."""
    out: list[str] = []
    index: list[int] = []
    previous_space = False
    for i, char in enumerate(text):
        char = char.translate(_CHAR_MAP)
        if char.isspace():
            if previous_space:
                continue
            char, previous_space = " ", True
        else:
            previous_space = False
        out.append(char)
        index.append(i)
    return "".join(out), index


@dataclass(frozen=True)
class ResolvedQuote:
    evidence: Evidence
    # Фраза встречается в тексте несколько раз, а контекст не помог выбрать: взято первое вхождение.
    ambiguous_location: bool = False


def resolve_quote(
    text: str,
    quote: str | None,
    *,
    candidate_text_id: uuid.UUID,
    context_before: str | None = None,
) -> ResolvedQuote | None:
    """Найти фразу модели в тексте. None — фразы в тексте нет (вывод не подтверждён)."""
    if not quote or not quote.strip():
        return None
    norm_text, index = _normalize(text)
    norm_quote = _normalize(quote.strip())[0]
    starts = []
    position = norm_text.find(norm_quote)
    while position != -1:
        starts.append(position)
        position = norm_text.find(norm_quote, position + 1)
    if not starts:
        return None

    chosen, ambiguous = starts[0], False
    if len(starts) > 1:
        matching = []
        if context_before and context_before.strip():
            norm_context = _normalize(context_before.strip())[0]
            matching = [s for s in starts if norm_text[:s].rstrip().endswith(norm_context.rstrip())]
        if len(matching) == 1:
            chosen = matching[0]
        else:
            chosen, ambiguous = (matching or starts)[0], True

    start = index[chosen]
    end = index[chosen + len(norm_quote) - 1] + 1
    exact = text[start:end]
    return ResolvedQuote(
        Evidence(candidate_text_id=candidate_text_id, quote=exact, start=start, end=end),
        ambiguous_location=ambiguous,
    )
