"""
Сборка папочного архива текстов решений — раздел 11 ТЗ.

Структура на район:
    <район>/
        Выигранные/<номер>_<дата>_Удовлетворен.docx
        Проигранные/<номер>_<дата>_Отказан.docx
        Несколько инстанций/<номер>_1Удовлетворен_2Отказан_.../<докс на каждую инстанцию>
"""
from pathlib import Path

from docx import Document

from ..models import CaseChain, Decision, Outcome

_OUTCOME_SHORT = {Outcome.SATISFIED: "Удовлетворен", Outcome.DENIED: "Отказан"}


def _docx_filename(d: Decision) -> str:
    case = d.case_number.replace("/", "-")
    date_str = d.decision_date.strftime("%d.%m.%Y") if d.decision_date else "б-д"
    return f"{case}_{date_str}_{d.outcome.value}.docx"


def _multi_instance_folder_name(chain: CaseChain) -> str:
    ordered = chain.sorted_by_instance()
    parts = [f"{rank}{_OUTCOME_SHORT.get(d.outcome, d.outcome.value)}" for rank, d in enumerate(ordered, start=1)]
    case = chain.primary_case_number.replace("/", "-")
    return f"{case}_" + "_".join(parts)


def write_decision_docx(decision: Decision, output_path: Path) -> None:
    """Пишет .docx решения: сверху столбиком ссылки на все источники этого
    решения (п.11 ТЗ), затем сам текст решения из raw-файла скрапера."""
    doc = Document()
    doc.add_heading(f"Дело № {decision.case_number}", level=1)

    for source, url in decision.source_links.items():
        if url:
            doc.add_paragraph(url)

    doc.add_paragraph("")

    if decision.text_local_path and Path(decision.text_local_path).exists():
        text = Path(decision.text_local_path).read_text(encoding="utf-8", errors="replace")
        for paragraph in text.split("\n"):
            doc.add_paragraph(paragraph)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)


def build_district_archive(chains: list[CaseChain], district_output_dir: Path) -> None:
    import shutil

    if district_output_dir.exists():
        for sub in ("Выигранные", "Проигранные", "Несколько инстанций"):
            p = district_output_dir / sub
            if p.exists():
                shutil.rmtree(p)

    won_dir = district_output_dir / "Выигранные"
    lost_dir = district_output_dir / "Проигранные"
    multi_dir = district_output_dir / "Несколько инстанций"

    for chain in chains:
        decisions_with_text = [d for d in chain.decisions if d.has_full_text]
        if not decisions_with_text:
            continue

        if len(chain.decisions) > 1:
            folder = multi_dir / _multi_instance_folder_name(chain)
            for d in decisions_with_text:
                write_decision_docx(d, folder / _docx_filename(d))
            continue

        d = decisions_with_text[0]
        if d.outcome == Outcome.SATISFIED:
            write_decision_docx(d, won_dir / _docx_filename(d))
        elif d.outcome == Outcome.DENIED:
            write_decision_docx(d, lost_dir / _docx_filename(d))
