"""
Оркестратор CLI: демо-режим и реальный прогон через скраперы.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

from .config import load_region
from .models import CaseChain, Decision, Instance, Outcome
from .pipeline import OUTPUT_DIR, scrape_all, write_reports

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _demo_chains() -> list[CaseChain]:
    d1 = Decision(
        case_number="2-101/2025",
        instance=Instance.FIRST,
        court_name="Автозаводский районный суд г. Нижнего Новгорода",
        district="Автозаводский район",
        judge_full_name="Иванова Мария Петровна",
        outcome=Outcome.SATISFIED,
        decision_date=date(2025, 3, 12),
        has_full_text=True,
        plaintiff_full_name="Петров Иван Сергеевич",
        representative_full_name="Сидорова Анна Викторовна",
        defendant_full_name="Администрация г. Н. Новгорода",
        has_bearing_wall_mention=False,
        expert_orgs=["ООО «Проектстрой»"],
        source_links={"sudrf": "https://avtozavodsky--nnov.sudrf.ru/example1"},
    )
    d2 = Decision(
        case_number="33-2200/2025",
        instance=Instance.APPEAL,
        court_name="Нижегородский областной суд",
        district="Автозаводский район",
        judge_full_name="Кузнецов Олег Николаевич",
        outcome=Outcome.SATISFIED,
        decision_date=date(2025, 6, 1),
        has_full_text=False,
    )
    chain_multi = CaseChain(chain_id="2-101/2025", decisions=[d1, d2])

    d3 = Decision(
        case_number="2-205/2025",
        instance=Instance.FIRST,
        court_name="Автозаводский районный суд г. Нижнего Новгорода",
        district="Автозаводский район",
        judge_full_name="Иванова Мария Петровна",
        outcome=Outcome.DENIED,
        decision_date=date(2025, 4, 2),
        has_full_text=True,
        plaintiff_full_name="Сидоров Пётр Алексеевич",
    )
    chain_single = CaseChain(chain_id="2-205/2025", decisions=[d3])
    return [chain_multi, chain_single]


def run_demo() -> None:
    chains = _demo_chains()
    write_reports({"Автозаводский район": chains}, "2024-2026")


def run_scrape(
    date_from: date,
    date_to: date,
    district: str | None = None,
    use_names_from_sudreshenia: bool = True,
    max_workers: int = 3,
) -> None:
    period = f"{date_from.year}-{date_to.year}"
    decisions, by_district = scrape_all(
        date_from=date_from,
        date_to=date_to,
        district=district,
        use_full_names=use_names_from_sudreshenia,
        max_workers=max_workers,
    )
    if not decisions:
        logger.warning("Дела не найдены")
        return
    write_reports(by_district, period)
    logger.info("Готово: %s решений, %s районов", len(decisions), len(by_district))


def main() -> None:
    parser = argparse.ArgumentParser(description="Парсер решений по делам о перепланировке")
    parser.add_argument("--demo", action="store_true", help="прогнать пайплайн на тестовых данных")
    parser.add_argument("--scrape", action="store_true", help="реальный прогон (судебныерешения.рф + vsrf)")
    parser.add_argument(
        "--district",
        type=str,
        default=None,
        help="только указанный район (1-я инстанция); 2–4-я инстанции всё равно подтягиваются",
    )
    parser.add_argument("--date-from", type=str, default="2020-01-01")
    parser.add_argument("--date-to", type=str, default="2026-12-31")
    parser.add_argument("--workers", type=int, default=3, help="параллельных потоков для районных судов (п.12 ТЗ)")
    parser.add_argument(
        "--no-full-names",
        action="store_true",
        help="не применять pick_best_source_for_names",
    )
    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.scrape:
        run_scrape(
            date_from=date.fromisoformat(args.date_from),
            date_to=date.fromisoformat(args.date_to),
            district=args.district,
            use_names_from_sudreshenia=not args.no_full_names,
            max_workers=args.workers,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
