"""Пересборка отчётов из кэша data/raw/sudreshenia (без повторного скрапинга)."""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from .config import load_region
from .linking import build_chains
from .markers import extract_expert_orgs, has_bearing_wall_mention
from .models import Decision, Instance
from .pipeline import RAW_DIR, write_reports
from .scrapers.parsers import parse_date, parse_judge, parse_outcome, parse_plaintiff, parse_representative

logger = logging.getLogger(__name__)


def rebuild_from_cache(period: str = "2020-2026") -> None:
    region = load_region()
    court_by_district = {c.district: c for c in region.first_instance_courts}
    decisions: list[Decision] = []

    cache_dir = RAW_DIR / "sudreshenia"
    if not cache_dir.exists():
        raise SystemExit(f"Нет кэша: {cache_dir}")

    for path in cache_dir.glob("*.txt"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "РЕШЕНИЕ" not in text and len(text) < 2000:
            continue
        m = re.match(r"^(.+?)_(\d+)\.txt$", path.name)
        if not m:
            continue
        case_number = m.group(1).replace("-", "/").replace(" (2-", " (2-")  # keep as stored
        # fix case number: files use 2-7161-2025 -> 2-7161/2025
        case_number = re.sub(r"^(\d+[а-яА-Я]?-\d+)-(\d{4})", r"\1/\2", m.group(1))
        case_id = m.group(2)

        # район из имени суда в тексте
        district = court_name = ""
        for c in region.first_instance_courts:
            short = c.name.split()[0]  # «Автозаводский», «Канавинский», ...
            if short.lower() in text.lower()[:3000]:
                district = c.district or ""
                court_name = c.name
                break
        if not district:
            continue

        decision_text = text[text.find("РЕШЕНИЕ") :] if "РЕШЕНИЕ" in text else text
        judge = parse_judge(text) or parse_judge(decision_text)
        judge = re.sub(r"^судь[ьяи]\s+", "", judge or "", flags=re.I).strip()

        d = Decision(
            case_number=case_number,
            instance=Instance.FIRST,
            court_name=court_name,
            district=district,
            judge_full_name=judge,
            outcome=parse_outcome(decision_text),
            decision_date=parse_date(text),
            has_full_text=True,
            text_local_path=str(path),
            plaintiff_full_name=parse_plaintiff(text),
            representative_full_name=parse_representative(text),
            has_bearing_wall_mention=has_bearing_wall_mention(decision_text),
            expert_orgs=extract_expert_orgs(decision_text),
            source_links={
                "sudreshenia": f"https://судебныерешения.рф/{case_id}",
            },
        )
        d._full_text = decision_text  # type: ignore[attr-defined]
        decisions.append(d)

    logger.info("Восстановлено из кэша: %s решений", len(decisions))
    chains = build_chains(decisions)
    by_district: dict[str, list] = defaultdict(list)
    for chain in chains:
        by_district[chain.district].append(chain)
    write_reports(dict(by_district), period)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rebuild_from_cache()
