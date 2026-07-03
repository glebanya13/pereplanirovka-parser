"""
Детекция маркеров в тексте решения — раздел 8.2 и 7.8.3/7.8.4 ТЗ.

ТЗ прямо требует: "не плоский поиск по фразе, а отбор по маркерам
переустройства, перепланировки, сохранения в переустроенном и (или)
перепланированном состоянии, переоборудованном состоянии".
"""
import re

# Маркеры для отбора дел нужной категории (используются при поиске/фильтрации
# результатов на сайтах-источниках).
CASE_TYPE_MARKERS = [
    re.compile(r"перепланировк\w*", re.IGNORECASE),
    re.compile(r"переустройств\w*", re.IGNORECASE),
    re.compile(r"переоборудован\w*", re.IGNORECASE),
    re.compile(r"сохранени\w+\s+.{0,40}\s+(?:пере)?планированн\w*\s+состояни\w*", re.IGNORECASE),
]

BEARING_WALL_RE = re.compile(r"несущ\w*\s+стен\w*", re.IGNORECASE)

# Организации, упомянутые как автор заключения/экспертизы/проекта/расчётов.
# Эвристика: ищем кавычки-«лапки» рядом (в окне N символов) с одним из ключевых
# слов. Нужно будет откалибровать на реальных текстах решений — это первый
# черновой вариант.
_EXPERT_KEYWORDS = r"(?:заключени[а-я]*|экспертиз[а-я]*|проект[а-я]*|расч[её]т[а-я]*)"
_QUOTED_ORG_RE = re.compile(r"«([^»]{2,80})»")
_EXPERT_CONTEXT_RE = re.compile(
    rf"{_EXPERT_KEYWORDS}[^.]{{0,120}}«([^»]{{2,80}})»"
    rf"|«([^»]{{2,80}})»[^.]{{0,120}}{_EXPERT_KEYWORDS}",
    re.IGNORECASE,
)


def matches_case_type(text: str) -> bool:
    return any(pattern.search(text) for pattern in CASE_TYPE_MARKERS)


def has_bearing_wall_mention(text: str) -> bool:
    return bool(BEARING_WALL_RE.search(text))


def extract_expert_orgs(text: str) -> list[str]:
    orgs: list[str] = []
    for match in _EXPERT_CONTEXT_RE.finditer(text):
        name = match.group(1) or match.group(2)
        if name and name not in orgs:
            orgs.append(name.strip())
    return orgs
