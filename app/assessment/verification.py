"""Проверки, которые не требуют модели и базы.

Здесь решается, можно ли верить выводу оценки:
- стоит ли цитата в нужном тексте на указанном месте (check_evidence);
- подтверждён ли вывод «выполнено / не выполнено» хотя бы одной годной цитатой (confirm_result);
- каков итог по обязательным формальным требованиям (formal_result);
- можно ли вообще выдавать рабочую оценку (assessment_refusal).

Функции чистые: им передают уже прочитанные тексты и статусы. Ими пользуются
контрольный набор (fixtures/assessment) и будущий сервис оценивания этапа 1.

Важно: БД v1.0 (app/db/repository.save_assessment) проверяет часть этого сама —
позицию цитаты и принадлежность текста кандидату. Версию текста, наличие
доказательства у вывода и статус профиля она сейчас не проверяет; где это делать
на этапе 1, ещё решается (hq/tasks/stage-0b-02-assessment-fixtures.md).
"""
import uuid
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.db.enums import CheckResult, RequirementStatus
from app.schemas.card import Evidence, evidence_matches


class EvidenceVerdict(StrEnum):
    """Почему цитате можно или нельзя верить. Проверки идут в этом порядке."""
    OK = "ok"
    UNKNOWN_TEXT = "unknown_text"                  # нет такого очищенного текста
    FOREIGN_TEXT = "foreign_text"                  # текст другого кандидата
    STALE_TEXT_VERSION = "stale_text_version"      # текст этого кандидата, но не та версия, по которой оценка
    QUOTE_NOT_AT_OFFSETS = "quote_not_at_offsets"  # на месте start:end в тексте другие символы


class ConfirmationIssue(StrEnum):
    """Почему вывод «выполнено / не выполнено» не подтверждён."""
    MISSING_EVIDENCE = "missing_evidence"  # цитат нет совсем
    INVALID_EVIDENCE = "invalid_evidence"  # цитаты есть, но ни одна не годится


class Refusal(StrEnum):
    """Почему рабочей оценки нет. Это не то же самое, что formal_result = unknown:
    unknown — проверка проведена, сведений не хватило; отказ — проверки не было."""
    MODEL_UNAVAILABLE = "model_unavailable"
    PROFILE_NOT_APPROVED = "profile_not_approved"


@dataclass(frozen=True)
class TextVersion:
    """Очищенный текст кандидата, как он хранится в candidate_texts."""
    id: uuid.UUID
    candidate_id: uuid.UUID
    version: int
    text: str


def check_evidence(
    evidence: Evidence,
    *,
    texts: Mapping[uuid.UUID, TextVersion],
    candidate_id: uuid.UUID,
    assessed_text_id: uuid.UUID,
) -> EvidenceVerdict:
    """Проверить одну цитату.

    assessed_text_id — версия очищенного текста, по которой построена карточка
    и проводится оценка. Цитата из другой версии того же кандидата не годится,
    даже если побуквенно совпадает: тексты версий могут разойтись в любом месте,
    и подсветка в интерфейсе откроет не тот документ.
    """
    text = texts.get(evidence.candidate_text_id)
    if text is None:
        return EvidenceVerdict.UNKNOWN_TEXT
    if text.candidate_id != candidate_id:
        return EvidenceVerdict.FOREIGN_TEXT
    if text.id != assessed_text_id:
        return EvidenceVerdict.STALE_TEXT_VERSION
    if not evidence_matches(text.text, evidence):
        return EvidenceVerdict.QUOTE_NOT_AT_OFFSETS
    return EvidenceVerdict.OK


@dataclass(frozen=True)
class Confirmation:
    """Результат проверки, после учёта доказательств."""
    claimed: CheckResult                 # что предложила модель
    effective: CheckResult               # чему верим
    issue: ConfirmationIssue | None      # почему понизили до unknown
    verdicts: tuple[EvidenceVerdict, ...]

    @property
    def confirmed(self) -> bool:
        return self.issue is None


def confirm_result(claimed: CheckResult, verdicts: Sequence[EvidenceVerdict]) -> Confirmation:
    """«Выполнено» и «не выполнено» — фактические выводы, им нужна хотя бы одна годная цитата.
    Без неё вывод неподтверждённый и считается unknown. Сам unknown цитаты не требует:
    это и есть «в тексте сведений нет»."""
    verdicts = tuple(verdicts)
    if claimed == CheckResult.UNKNOWN:
        return Confirmation(claimed, CheckResult.UNKNOWN, None, verdicts)
    if not verdicts:
        return Confirmation(claimed, CheckResult.UNKNOWN, ConfirmationIssue.MISSING_EVIDENCE, verdicts)
    if EvidenceVerdict.OK not in verdicts:
        return Confirmation(claimed, CheckResult.UNKNOWN, ConfirmationIssue.INVALID_EVIDENCE, verdicts)
    return Confirmation(claimed, claimed, None, verdicts)


def competency_issue(level: int | None, verdicts: Sequence[EvidenceVerdict]) -> ConfirmationIssue | None:
    """Есть ли у оценки компетенции опора. Если нет ни уровня, ни цитат — модель ничего
    не утверждала, проверять нечего. Иначе нужна хотя бы одна годная цитата: без неё
    уровень и свидетельство не показываются как подтверждённые."""
    if level is None and not verdicts:
        return None
    if not verdicts:
        return ConfirmationIssue.MISSING_EVIDENCE
    if EvidenceVerdict.OK not in verdicts:
        return ConfirmationIssue.INVALID_EVIDENCE
    return None


def formal_result(results: Mapping[Hashable, CheckResult], mandatory: Iterable[Hashable]) -> CheckResult:
    """Итог по обязательным формальным требованиям. Высокие оценки компетенций
    в нём не участвуют: формальное требование не компенсируется.

    Хоть одно обязательное не выполнено → not_met; хоть одно без сведений или
    не проверено → unknown; иначе met. Совпадает с правилом контракта БД (п. 2.6)
    и с repository._formal_result; совпадение проверяет tests/test_assessment_fixtures_db.py.
    """
    mandatory = list(mandatory)
    if any(results.get(key) == CheckResult.NOT_MET for key in mandatory):
        return CheckResult.NOT_MET
    if any(results.get(key, CheckResult.UNKNOWN) == CheckResult.UNKNOWN for key in mandatory):
        return CheckResult.UNKNOWN
    return CheckResult.MET


def assessment_refusal(*, profile_status: RequirementStatus, model_available: bool) -> Refusal | None:
    """Можно ли выдать рабочую оценку. Черновой и архивный профиль не дают рабочей рекомендации."""
    if profile_status != RequirementStatus.APPROVED:
        return Refusal.PROFILE_NOT_APPROVED
    if not model_available:
        return Refusal.MODEL_UNAVAILABLE
    return None


def utf16_offsets(text: str, start: int, end: int) -> tuple[int, int]:
    """Перевести границы из кодовых точек (Python) в единицы UTF-16 (JavaScript).

    В базе и в Evidence границы в кодовых точках. Браузер считает строку в UTF-16:
    символ вне BMP (эмодзи, редкие иероглифы) занимает там две единицы, и подсветка
    по сырым start/end съедет. Функция нужна для справки фронтенду и проверки набора.
    """
    def units(chunk: str) -> int:
        return len(chunk.encode("utf-16-le")) // 2

    return units(text[:start]), units(text[:end])
