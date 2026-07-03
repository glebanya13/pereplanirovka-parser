"""Общие эвристики извлечения полей из текста решения."""
import re
from datetime import date, datetime

from ..models import Outcome

_OUTCOME_SATISFIED_RE = re.compile(
    r"(?:иск|заявлени[ея]|требовани[ея])\s+(?:полностью\s+)?удовлетвор",
    re.IGNORECASE,
)
_OUTCOME_DENIED_RE = re.compile(
    r"(?:в\s+удовлетворени[ие]\s+.{0,60}\s+отказать|отказать\s+в\s+удовлетворени)",
    re.IGNORECASE,
)

_JUDGE_RE = re.compile(
    r"(?:председательствующ\w+|судь[яи])\s*:?\s*([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})",
    re.IGNORECASE,
)
_PLAINTIFF_RE = re.compile(
    r"(?:истец|заявитель)\s*[:\-]?\s*([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ]\.[А-ЯЁ]\.?|\s+[А-ЯЁ][а-яё]+){1,2})",
    re.IGNORECASE,
)
_PLAINTIFF_BY_CLAIM_RE = re.compile(
    r"по\s+иску\s+([А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.?)",
    re.IGNORECASE,
)
_REPRESENTATIVE_RE = re.compile(
    r"представител\w+\s+истц\w*\s+([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ]\.[А-ЯЁ]\.?|\s+[А-ЯЁ][а-яё]+){1,2})",
    re.IGNORECASE,
)

_CASE_NUMBER_RE = re.compile(r"\b([0-9]+[а-яА-Я]?-[0-9]+/[0-9]{2,4})\b")


def parse_outcome(text: str) -> Outcome:
    # Сначала резолютивная часть после «РЕШИЛ:» / «ПОСТАНОВИЛ:»
    for header in ("РЕШИЛ", "ПОСТАНОВИЛ", "ОПРЕДЕЛИЛ"):
        m = re.search(rf"{header}:?\s*(.{{0,800}})", text, re.IGNORECASE | re.DOTALL)
        if m:
            part = m.group(1)
            if re.search(r"удовлетворить", part, re.IGNORECASE):
                return Outcome.SATISFIED
            if re.search(r"в\s+удовлетворени[ие].{0,80}отказать", part, re.IGNORECASE):
                return Outcome.DENIED
    if _OUTCOME_DENIED_RE.search(text):
        return Outcome.DENIED
    if _OUTCOME_SATISFIED_RE.search(text):
        return Outcome.SATISFIED
    return Outcome.PENDING


def parse_judge(text: str) -> str:
    m = _JUDGE_RE.search(text)
    return m.group(1).strip() if m else ""


def parse_plaintiff(text: str) -> str | None:
    for pattern in (_PLAINTIFF_RE, _PLAINTIFF_BY_CLAIM_RE):
        m = pattern.search(text)
        if m:
            name = m.group(1).strip()
            if len(name.split()) >= 2 or "." in name:
                return name
    return None


def parse_representative(text: str) -> str | None:
    m = _REPRESENTATIVE_RE.search(text)
    return m.group(1).strip() if m else None


def parse_date(value: str) -> date | None:
    value = value.strip()
    for fmt in ("%d.%m.%Y", "%d %B %Y г.", "%d %B %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    # fallback: DD.MM.YYYY anywhere
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", value)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def extract_case_number(text: str) -> str | None:
    m = _CASE_NUMBER_RE.search(text)
    return m.group(1) if m else None
