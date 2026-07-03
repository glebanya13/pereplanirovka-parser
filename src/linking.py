"""
Связывание решений одного дела между инстанциями (раздел 4-6 ТЗ) и выбор
источника с полными ФИО (раздел 7.8.1, 7.8.4, 11 ТЗ).

ФИО-логика вынесена в отдельную явную функцию `pick_best_source_for_names`,
а не спрятана внутри общего пайплайна скрапинга — решение принято совместно
с исполнителем (см. README, раздел "Важное ограничение по ПДн"). Чтобы
отключить деобезличивание, достаточно не вызывать эту функцию и брать
plaintiff_full_name/representative_full_name с сайта первой инстанции как есть.
"""
import re

from .models import CaseChain, Decision, Instance

# Решения апелляции/кассации/ВС обычно ссылаются на номер дела нижестоящей
# инстанции в тексте ("по делу № 2-123/2025", "решение Автозаводского
# районного суда... от .. по делу №..."). Извлекаем такие ссылки, чтобы
# сшивать инстанции в одну цепочку.
_CASE_REF_RE = re.compile(r"(?:дел[ауе]\s*№?\s*|№\s*)([0-9]+[а-яА-Я]?-[0-9]+/[0-9]{2,4})")

_ANONYMIZED_NAME_RE = re.compile(
    r"^\s*(?:истец|ответчик|представитель|фио\d*|ф\.?\s*и\.?\s*о\.?\d*)\s*$",
    re.IGNORECASE,
)
_INITIALS_ONLY_RE = re.compile(r"^[А-ЯЁ]\.\s*[А-ЯЁ]\.\s*[А-ЯЁ][а-яё]+$")


def extract_referenced_case_numbers(decision_text: str) -> set[str]:
    return set(_CASE_REF_RE.findall(decision_text))


def build_chains(decisions: list[Decision]) -> list[CaseChain]:
    """Группирует решения в цепочки по совпадению/перекрёстным ссылкам
    номеров дел. decisions[i].chain_id должен быть выставлен заранее,
    если он уже известен из скрапинга (например, decision явно указывает
    dело первой инстанции); эта функция достраивает то, что не удалось
    связать на этапе скрапинга, через regex-поиск ссылок в тексте."""
    by_number: dict[str, Decision] = {d.case_number: d for d in decisions}
    parent: dict[str, str] = {d.case_number: d.case_number for d in decisions}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for d in decisions:
        for ref in getattr(d, "_referenced_numbers", []) or []:
            if ref in by_number:
                union(d.case_number, ref)

    # Наследуем район от первой инстанции внутри цепочки
    district_by_root: dict[str, str] = {}
    for d in decisions:
        if d.instance == Instance.FIRST and d.district:
            district_by_root[d.case_number] = d.district

    groups: dict[str, list[Decision]] = {}
    for d in decisions:
        root = find(d.case_number)
        groups.setdefault(root, []).append(d)

    chains = []
    for root, group in groups.items():
        district = district_by_root.get(root) or next(
            (d.district for d in group if d.instance == Instance.FIRST and d.district), ""
        )
        for d in group:
            d.chain_id = root
            if not d.district and district:
                d.district = district
        chains.append(CaseChain(chain_id=root, decisions=group))
    return chains


def _looks_anonymized(name: str | None) -> bool:
    if not name:
        return True
    name = name.strip()
    return bool(_ANONYMIZED_NAME_RE.match(name) or _INITIALS_ONLY_RE.match(name))


def pick_best_source_for_names(
    candidates: dict[str, tuple[str | None, str | None]],
) -> tuple[str | None, str | None, str | None]:
    """candidates: {source_name: (plaintiff_full_name, representative_full_name)}
    извлечённые из текста решения на разных источниках (sudrf/bsr/sudact/
    sudreshenia/vsrf) для одного и того же решения.

    Возвращает (source_name, plaintiff_full_name, representative_full_name)
    для источника, где имена не обезличены. Порядок приоритета соответствует
    п.11 ТЗ: сначала судебныерешения.рф, затем прочие источники."""
    priority = ["sudreshenia", "sudact", "sudrf", "vsrf"]
    ordered = sorted(candidates.keys(), key=lambda s: priority.index(s) if s in priority else len(priority))

    for source in ordered:
        plaintiff, representative = candidates[source]
        if not _looks_anonymized(plaintiff):
            return source, plaintiff, representative
    return None, None, None
