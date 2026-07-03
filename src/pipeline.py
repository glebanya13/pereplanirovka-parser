"""
Полный пайплайн: судебныерешения.рф (поиск + ФИО) + sudrf.ru (официальные ссылки/тексты).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from .config import CourtConfig, RegionConfig, load_region
from .linking import build_chains, pick_best_source_for_names
from .models import CaseChain, Decision, Instance
from .report.archive_builder import build_district_archive
from .report.xlsx_builder import build_combined_workbook, build_district_workbook
from .scrapers.sudreshenia import SudresheniaScraper
from .scrapers.sudrf_cms import SudrfCmsScraper
from .scrapers.vsrf import VsrfScraper

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
_SUDRESHENIA_REGION_ID = 66


def _scrape_sudreshenia(
    court: CourtConfig,
    date_from: date,
    date_to: date,
    instance: Instance,
    raw_dir: Path,
) -> list[Decision]:
    scraper = SudresheniaScraper(raw_dir=raw_dir)
    return list(scraper.search_cases(court, date_from, date_to, instance=instance))


def _enrich_with_sudrf(decision: Decision, court: CourtConfig, raw_dir: Path) -> None:
    """Добавляет официальную ссылку sudrf.ru; текст не перезаписывает."""
    if not court.host:
        return
    if decision.has_full_text:
        decision.source_links.setdefault(
            "sudrf",
            f"https://{court.host}/modules.php?name=sud_delo&srv_num=2",
        )
        return
    try:
        sudrf = SudrfCmsScraper.from_court(court, raw_dir=raw_dir)
        official = sudrf.lookup_by_case_number(decision.case_number, decision.instance)
        if not official:
            return
        decision.source_links["sudrf"] = official.source_links.get("sudrf", "")
        if official.judge_full_name and not decision.judge_full_name:
            decision.judge_full_name = official.judge_full_name
        if official.decision_date and not decision.decision_date:
            decision.decision_date = official.decision_date
        sudrf_text = getattr(official, "_full_text", "") or ""
        if (
            official.outcome.value != "На проверку"
            and decision.outcome.value == "На проверку"
        ):
            decision.outcome = official.outcome
        # Текст с sudrf — только если там есть резолютивная часть, иначе оставляем sudreshenia
        if "РЕШЕНИЕ" in sudrf_text and len(sudrf_text) > 500:
            if not decision.has_full_text or len(getattr(decision, "_full_text", "") or "") < len(sudrf_text):
                decision.has_full_text = True
                decision.text_local_path = official.text_local_path
                decision._full_text = sudrf_text  # type: ignore[attr-defined]
    except Exception as exc:
        logger.debug("sudrf enrich %s: %s", decision.case_number, exc)


def _merge_decisions(decisions: list[Decision]) -> list[Decision]:
    by_key: dict[tuple[str, Instance], Decision] = {}
    for d in decisions:
        key = (d.case_number, d.instance)
        if key not in by_key:
            by_key[key] = d
            continue
        ex = by_key[key]
        ex.source_links.update(d.source_links)
        for attr in ("plaintiff_full_name", "representative_full_name", "defendant_full_name", "judge_full_name"):
            if not getattr(ex, attr) and getattr(d, attr):
                setattr(ex, attr, getattr(d, attr))
        if d.has_full_text and (not ex.has_full_text or len(getattr(ex, "_full_text", "") or "") < len(getattr(d, "_full_text", "") or "")):
            ex.has_full_text = d.has_full_text
            ex.text_local_path = d.text_local_path
            ex._full_text = getattr(d, "_full_text", "")  # type: ignore[attr-defined]
            ex.outcome = d.outcome if d.outcome.value != "На проверку" else ex.outcome
        refs = getattr(d, "_referenced_numbers", []) or []
        ex_refs = getattr(ex, "_referenced_numbers", []) or []
        ex._referenced_numbers = list(set(ex_refs + refs))  # type: ignore[attr-defined]
    return list(by_key.values())


def _apply_full_names(decisions: list[Decision], enabled: bool) -> None:
    if not enabled:
        return
    by_case: dict[tuple[str, Instance], dict[str, tuple[str | None, str | None]]] = defaultdict(dict)
    for d in decisions:
        key = (d.case_number, d.instance)
        for src in d.source_links:
            by_case[key][src] = (d.plaintiff_full_name, d.representative_full_name)
    for d in decisions:
        key = (d.case_number, d.instance)
        if key not in by_case:
            continue
        _src, plaintiff, rep = pick_best_source_for_names(by_case[key])
        if plaintiff:
            d.plaintiff_full_name = plaintiff
        if rep:
            d.representative_full_name = rep


def scrape_all(
    date_from: date,
    date_to: date,
    district: str | None = None,
    use_full_names: bool = True,
    max_workers: int = 2,
) -> tuple[list[Decision], dict[str, list[CaseChain]]]:
    region = load_region()
    all_decisions: list[Decision] = []

    courts = region.first_instance_courts
    if district:
        courts = [c for c in courts if c.district == district or district in (c.name or "")]
        if not courts:
            raise ValueError(f"Район не найден: {district}")

    logger.info("1-я инстанция: %s судов", len(courts))

    def process_court(court: CourtConfig) -> list[Decision]:
        found = _scrape_sudreshenia(court, date_from, date_to, Instance.FIRST, RAW_DIR)
        for d in found:
            _enrich_with_sudrf(d, court, RAW_DIR)
        return found

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(process_court, c): c for c in courts if c.sudreshenia_id}
        for fut in as_completed(futures):
            court = futures[fut]
            try:
                found = fut.result()
                logger.info("  %s: %s дел", court.district, len(found))
                all_decisions.extend(found)
            except Exception as exc:
                logger.error("  %s: %s", court.name, exc)

    logger.info("2–4-я инстанции: областной суд, кассация, надзор, vsrf")
    for label, court, inst in [
        ("апелляция", region.appeal_court, Instance.APPEAL),
        ("кассация", region.cassation_court, Instance.CASSATION),
    ]:
        if court and court.sudreshenia_id:
            try:
                found = _scrape_sudreshenia(court, date_from, date_to, inst, RAW_DIR)
                logger.info("  %s: %s дел", label, len(found))
                all_decisions.extend(found)
            except Exception as exc:
                logger.error("  %s: %s", label, exc)

    try:
        scraper = SudresheniaScraper(raw_dir=RAW_DIR)
        nadzor = list(scraper.search_region(date_from, date_to, _SUDRESHENIA_REGION_ID, "nadzor"))
        for d in nadzor:
            d.instance = Instance.SUPREME
        all_decisions.extend(nadzor)
        logger.info("  надзор: %s дел", len(nadzor))
    except Exception as exc:
        logger.error("  надзор: %s", exc)

    try:
        supreme = list(VsrfScraper().search_cases(date_from, date_to))
        all_decisions.extend(supreme)
        logger.info("  vsrf: %s ссылок", len(supreme))
    except Exception as exc:
        logger.error("  vsrf: %s", exc)

    all_decisions = _merge_decisions(all_decisions)
    _apply_full_names(all_decisions, use_full_names)
    chains = build_chains(all_decisions)

    by_district: dict[str, list[CaseChain]] = defaultdict(list)
    for chain in chains:
        by_district[chain.district or "Не определён"].append(chain)

    return all_decisions, dict(by_district)


def write_reports(by_district: dict[str, list[CaseChain]], period: str, region: RegionConfig | None = None) -> None:
    region = region or load_region()
    for district_name, chains in by_district.items():
        court_label = next(
            (c.name for c in region.first_instance_courts if c.district == district_name),
            district_name,
        )
        wb = build_district_workbook(chains, court_label, period)
        xlsx_path = OUTPUT_DIR / "xlsx" / f"{district_name}.xlsx"
        xlsx_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(xlsx_path)
        archive_dir = OUTPUT_DIR / "decisions" / district_name
        build_district_archive(chains, archive_dir)
        wb.save(archive_dir / f"{district_name}.xlsx")
        logger.info("готово: %s (%s цепочек)", district_name, len(chains))

    combined_wb = build_combined_workbook(by_district, period)
    combined_wb.save(OUTPUT_DIR / "xlsx" / "Все районы.xlsx")
    logger.info("общий xlsx: %s", OUTPUT_DIR / "xlsx" / "Все районы.xlsx")
