"""
Сборка xlsx-описи — раздел 7 ТЗ. Структура листов и колонок взята из
эталонного файла "ТЗ форма для парсинга. перепланировка.xlsx" (ссылка из
п.2 ТЗ), а не придумана по тексту — см. README.
"""
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from ..models import CaseChain, Decision, Instance, Outcome

HEADER_FILL = PatternFill(start_color="FF9E480E", end_color="FF9E480E", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFFFF")
TITLE_FONT = Font(bold=True, size=12)

# Раздел 7.4 ТЗ: цвет строки зависит от порядкового номера инстанции решения
# в цепочке (1-я — без заливки, как в эталонном файле).
INSTANCE_FILL_BY_RANK = {
    1: None,
    2: PatternFill(start_color="FFFFFF00", end_color="FFFFFF00", fill_type="solid"),
    3: PatternFill(start_color="FFF8CBAD", end_color="FFF8CBAD", fill_type="solid"),
    4: PatternFill(start_color="FFBDD7EE", end_color="FFBDD7EE", fill_type="solid"),
}


def _style_header_row(ws: Worksheet, row: int, ncols: int) -> None:
    for col in range(1, ncols + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")


def _docx_filename(d: Decision) -> str:
    case = d.case_number.replace("/", "-")
    date_str = d.decision_date.strftime("%d.%m.%Y") if d.decision_date else "б-д"
    return f"{case}_{date_str}_{d.outcome.value}.docx"


def _other_source_links(d: Decision) -> str:
    return "\n".join(url for src, url in d.source_links.items() if src != "sudrf" and url)


def _outcome_rows(chains: list[CaseChain], instance: Instance, outcome: Outcome) -> list[Decision]:
    rows = []
    for chain in chains:
        for d in chain.decisions:
            if d.instance == instance and d.outcome == outcome:
                rows.append(d)
    return rows


def _add_satisfied_or_denied_sheet(
    wb: Workbook, sheet_name: str, decisions: list[Decision], court_name: str, period: str, outcome: Outcome
) -> None:
    ws = wb.create_sheet(sheet_name)
    headers = [
        "№ дела / решения", "Дата решения", "Есть текст\nрешения", "Несущая стена",
        "суд", "ФИО судьи", "истец", "ответчик", "представитель истца ФИО",
        "заключение, экспертиза", "результат", "ссылка на источник в суде",
        "ссылка на источники двух других сайтов", "название DOCX-файла",
    ]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    title = f"{'Удовлетворенные' if outcome == Outcome.SATISFIED else 'Отказанные'} решения {court_name} за {period}"
    ws.cell(row=1, column=1, value=title).font = TITLE_FONT

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=2)
    ws.cell(row=2, column=1, value="Количество решений")
    ws.cell(row=2, column=3, value=len(decisions))

    # По ФИО судьи (раздел 7.1/7.2 ТЗ), внутри группы — по возрастанию номера решения
    grouped: dict[str, list[Decision]] = {}
    for d in decisions:
        grouped.setdefault(d.judge_full_name or "Не установлено", []).append(d)
    for judge in grouped:
        grouped[judge].sort(key=lambda d: d.case_number)

    header_row = 4
    _write_headers(ws, header_row, headers)

    row = header_row + 1
    for judge in sorted(grouped):
        for d in grouped[judge]:
            ws.cell(row=row, column=1, value=d.case_number)
            ws.cell(row=row, column=2, value=d.decision_date)
            ws.cell(row=row, column=3, value=None if d.has_full_text else "нет")
            ws.cell(row=row, column=4, value="да" if d.has_bearing_wall_mention else None)
            ws.cell(row=row, column=5, value=d.court_name)
            ws.cell(row=row, column=6, value=d.judge_full_name)
            ws.cell(row=row, column=7, value=d.plaintiff_full_name)
            ws.cell(row=row, column=8, value=d.defendant_full_name)
            ws.cell(row=row, column=9, value=d.representative_full_name)
            ws.cell(row=row, column=10, value="; ".join(d.expert_orgs) or None)
            ws.cell(row=row, column=11, value=d.outcome.value)
            ws.cell(row=row, column=12, value=d.source_links.get("sudrf"))
            ws.cell(row=row, column=13, value=_other_source_links(d))
            ws.cell(row=row, column=14, value=_docx_filename(d) if d.has_full_text else None)
            row += 1

    _autosize(ws, len(headers))


def _write_headers(ws: Worksheet, row: int, headers: list[str]) -> None:
    for col, text in enumerate(headers, start=1):
        ws.cell(row=row, column=col, value=text)
    _style_header_row(ws, row, len(headers))


def _autosize(ws: Worksheet, ncols: int, width: int = 22) -> None:
    for col in range(1, ncols + 1):
        ws.column_dimensions[get_column_letter(col)].width = width


def _add_stats_sheet(wb: Workbook, all_decisions: list[Decision]) -> None:
    ws = wb.create_sheet("Статистика по судьям и представ")

    def stats_by(key_fn) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = {}
        for d in all_decisions:
            key = key_fn(d)
            if not key:
                continue
            entry = stats.setdefault(key, {"satisfied": 0, "denied": 0})
            if d.outcome == Outcome.SATISFIED:
                entry["satisfied"] += 1
            elif d.outcome == Outcome.DENIED:
                entry["denied"] += 1
        return stats

    def write_block(start_row: int, title: str, stats: dict[str, dict[str, int]], name_header: str) -> int:
        ws.cell(row=start_row, column=1, value=title).font = TITLE_FONT
        header_row = start_row + 2
        _write_headers(ws, header_row, [name_header, "Удовлетворенные", "Отказанные", "Всего", "% удовлетворения"])

        ordered = sorted(stats.items(), key=lambda kv: kv[1]["satisfied"] + kv[1]["denied"], reverse=True)
        row = header_row + 1
        total_sat = total_den = 0
        for name, entry in ordered:
            total = entry["satisfied"] + entry["denied"]
            pct = entry["satisfied"] / total if total else 0
            ws.cell(row=row, column=1, value=name)
            ws.cell(row=row, column=2, value=entry["satisfied"])
            ws.cell(row=row, column=3, value=entry["denied"])
            ws.cell(row=row, column=4, value=total)
            ws.cell(row=row, column=5, value=pct)
            total_sat += entry["satisfied"]
            total_den += entry["denied"]
            row += 1
        total_all = total_sat + total_den
        ws.cell(row=row, column=1, value="Итого")
        ws.cell(row=row, column=2, value=total_sat)
        ws.cell(row=row, column=3, value=total_den)
        ws.cell(row=row, column=4, value=total_all)
        ws.cell(row=row, column=5, value=(total_sat / total_all if total_all else 0))
        return row + 2

    next_row = write_block(1, "Статистика по судьям", stats_by(lambda d: d.judge_full_name), "ФИО судьи")
    write_block(next_row, "Статистика по представителям истца", stats_by(lambda d: d.representative_full_name), "ФИО представителя истца")

    _autosize(ws, 5)


def _add_multi_instance_sheet(wb: Workbook, chains: list[CaseChain]) -> None:
    ws = wb.create_sheet("Решения с более одной инстанции")
    headers = [
        "№ дела / решения", "Дата решения", "Суд", "ФИО судьи", "Истец", "Ответчик",
        "Представитель истца ФИО", "Результат", "Ссылка на источник в суде",
        "Ссылка на источник", "DOCX-файл", "Папка архива",
    ]
    _write_headers(ws, 1, headers)

    row = 2
    for chain in chains:
        ordered = chain.sorted_by_instance()
        if len(ordered) <= 1:
            continue
        for rank, d in enumerate(ordered, start=1):
            fill = INSTANCE_FILL_BY_RANK.get(rank)
            values = [
                d.case_number, d.decision_date, d.court_name, d.judge_full_name,
                d.plaintiff_full_name, d.defendant_full_name, d.representative_full_name, d.outcome.value,
                d.source_links.get("sudrf"),
                _other_source_links(d),
                _docx_filename(d) if d.has_full_text else None,
                "multi_instance",
            ]
            for col, value in enumerate(values, start=1):
                cell = ws.cell(row=row, column=col, value=value)
                if fill:
                    cell.fill = fill
            row += 1

    _autosize(ws, len(headers))


def _add_pending_sheet(wb: Workbook, all_decisions: list[Decision]) -> None:
    ws = wb.create_sheet("На проверку")
    headers = [
        "№ дела / решения", "дата решения", "суд", "ФИО судьи", "истец", "ответчик",
        "представитель истца", "результат", "ссылка на источник в суде",
        "ссылка на источник", "название DOCX-файла",
    ]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws.cell(row=1, column=1, value="Позиции, требующие ручной проверки").font = TITLE_FONT
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
    ws.cell(
        row=2, column=1,
        value="Решения, для которых не найден полный текст ни на одном из указанных в ТЗ источников.",
    )

    header_row = 3
    _write_headers(ws, header_row, headers)

    row = header_row + 1
    for d in all_decisions:
        if d.has_full_text:
            continue
        ws.cell(row=row, column=1, value=d.case_number)
        ws.cell(row=row, column=2, value=d.decision_date)
        ws.cell(row=row, column=3, value=d.court_name)
        ws.cell(row=row, column=4, value=d.judge_full_name)
        ws.cell(row=row, column=5, value=d.plaintiff_full_name)
        ws.cell(row=row, column=6, value=d.defendant_full_name)
        ws.cell(row=row, column=7, value=d.representative_full_name)
        ws.cell(row=row, column=8, value=d.outcome.value if d.outcome != Outcome.PENDING else "Не установлен")
        ws.cell(row=row, column=9, value=d.source_links.get("sudrf"))
        ws.cell(row=row, column=10, value=_other_source_links(d))
        ws.cell(row=row, column=11, value=None)
        row += 1

    _autosize(ws, len(headers))


def _add_by_case_number_sheet(wb: Workbook, all_decisions: list[Decision], period: str) -> None:
    ws = wb.create_sheet("По номеру дела")
    headers = [
        "№ дела / решения", "Дата решения", "Раздел комплекта", "Есть текст решения", "Несущая стена",
        "Суд", "ФИО судьи", "Истец", "Ответчик", "Представитель истца ФИО",
        "Заключение, экспертиза", "Результат", "Ссылка на источник в суде",
        "Ссылка на источники", "DOCX-файл", "Папка архива",
    ]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws.cell(row=1, column=1, value="Сводная опись по номеру дела").font = TITLE_FONT
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
    ws.cell(
        row=2, column=1,
        value=f"Все решения за период {period}, отсортированные по возрастанию номера дела.",
    )

    satisfied = sum(1 for d in all_decisions if d.outcome == Outcome.SATISFIED)
    denied = sum(1 for d in all_decisions if d.outcome == Outcome.DENIED)
    case_numbers = [d.case_number for d in all_decisions]
    duplicates = len(case_numbers) - len(set(case_numbers))
    ws.cell(row=3, column=1, value="Всего включено")
    ws.cell(row=3, column=2, value=len(all_decisions))
    ws.cell(row=3, column=3, value="Удовлетворенные")
    ws.cell(row=3, column=6, value=satisfied)
    ws.cell(row=3, column=7, value="Отказанные")
    ws.cell(row=3, column=8, value=denied)
    ws.cell(row=3, column=9, value="Дублей по номеру дела")
    ws.cell(row=3, column=12, value=duplicates)
    ws.cell(row=3, column=14, value="Дата формирования")
    ws.cell(row=3, column=15, value=date.today().strftime("%d.%m.%Y"))

    header_row = 5
    _write_headers(ws, header_row, headers)

    def sort_key(d: Decision) -> tuple:
        digits = d.case_number.split("-")[-1] if "-" in d.case_number else d.case_number
        return (d.case_number,)

    row = header_row + 1
    for d in sorted(all_decisions, key=sort_key):
        section = {
            Outcome.SATISFIED: "Удовлетворенные",
            Outcome.DENIED: "Отказанные",
            Outcome.PENDING: "На проверку",
        }[d.outcome] if d.has_full_text else "На проверку"
        ws.cell(row=row, column=1, value=d.case_number)
        ws.cell(row=row, column=2, value=d.decision_date)
        ws.cell(row=row, column=3, value=section)
        ws.cell(row=row, column=4, value=None if d.has_full_text else "нет")
        ws.cell(row=row, column=5, value="да" if d.has_bearing_wall_mention else None)
        ws.cell(row=row, column=6, value=d.court_name)
        ws.cell(row=row, column=7, value=d.judge_full_name)
        ws.cell(row=row, column=8, value=d.plaintiff_full_name)
        ws.cell(row=row, column=9, value=d.defendant_full_name)
        ws.cell(row=row, column=10, value=d.representative_full_name)
        ws.cell(row=row, column=11, value="; ".join(d.expert_orgs) or None)
        ws.cell(row=row, column=12, value=d.outcome.value)
        ws.cell(row=row, column=13, value=d.source_links.get("sudrf"))
        ws.cell(row=row, column=14, value=_other_source_links(d))
        ws.cell(row=row, column=15, value=_docx_filename(d) if d.has_full_text else None)
        ws.cell(row=row, column=16, value="satisfied_decisions" if d.outcome == Outcome.SATISFIED else "denied_decisions")
        row += 1

    _autosize(ws, len(headers))


def build_district_workbook(chains: list[CaseChain], court_name: str, period: str) -> Workbook:
    """Один xlsx на район/суд — раздел 7 ТЗ (без листа "Районы", он только
    в общем файле, см. build_combined_workbook)."""
    wb = Workbook()
    wb.remove(wb.active)

    all_decisions = [d for chain in chains for d in chain.decisions]
    satisfied = [d for d in all_decisions if d.outcome == Outcome.SATISFIED]
    denied = [d for d in all_decisions if d.outcome == Outcome.DENIED]

    _add_satisfied_or_denied_sheet(wb, "Удовлетворенные", satisfied, court_name, period, Outcome.SATISFIED)
    _add_satisfied_or_denied_sheet(wb, "Отказанные", denied, court_name, period, Outcome.DENIED)
    _add_stats_sheet(wb, all_decisions)
    _add_multi_instance_sheet(wb, chains)
    _add_pending_sheet(wb, all_decisions)
    _add_by_case_number_sheet(wb, all_decisions, period)

    return wb


def _add_districts_sheet(wb: Workbook, chains_by_district: dict[str, list[CaseChain]]) -> None:
    """Раздел 7.7 ТЗ — только в общем файле: группировка по району, внутри
    района — по номеру дела по возрастанию."""
    ws = wb.create_sheet("Районы")
    headers = [
        "Район", "№ дела / решения", "Дата решения", "Суд", "ФИО судьи", "Истец",
        "Представитель истца ФИО", "Результат", "Есть текст решения", "DOCX-файл",
    ]
    _write_headers(ws, 1, headers)

    row = 2
    for district in sorted(chains_by_district):
        decisions = sorted(
            (d for chain in chains_by_district[district] for d in chain.decisions),
            key=lambda d: d.case_number,
        )
        for d in decisions:
            ws.cell(row=row, column=1, value=district)
            ws.cell(row=row, column=2, value=d.case_number)
            ws.cell(row=row, column=3, value=d.decision_date)
            ws.cell(row=row, column=4, value=d.court_name)
            ws.cell(row=row, column=5, value=d.judge_full_name)
            ws.cell(row=row, column=6, value=d.plaintiff_full_name)
            ws.cell(row=row, column=7, value=d.representative_full_name)
            ws.cell(row=row, column=8, value=d.outcome.value)
            ws.cell(row=row, column=9, value=None if d.has_full_text else "нет")
            ws.cell(row=row, column=10, value=_docx_filename(d) if d.has_full_text else None)
            row += 1

    _autosize(ws, len(headers))


def build_combined_workbook(chains_by_district: dict[str, list[CaseChain]], period: str) -> Workbook:
    """Общий xlsx по всем районам — те же 6 листов + лист "Районы" (п.7.7 ТЗ)."""
    all_chains = [c for chains in chains_by_district.values() for c in chains]
    wb = build_district_workbook(all_chains, "всем судам г. Нижнего Новгорода", period)
    _add_districts_sheet(wb, chains_by_district)
    return wb
