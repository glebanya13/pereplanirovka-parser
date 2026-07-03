"""
Скрапер sudact.ru — разделы 3.3, 4.3, 5.3 ТЗ.

Поиск на /regular/doc/ отдаёт результаты через JavaScript — нужен Playwright.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date

from ..config import CourtConfig
from ..markers import matches_case_type
from ..models import Decision, Instance, Outcome
from .parsers import parse_outcome

logger = logging.getLogger(__name__)

_BASE = "https://sudact.ru/regular/doc/"
_NN_AREA_CODE = "1007"

_INSTANCE_STAGE = {
    Instance.FIRST: "10",
    Instance.APPEAL: "20",
    Instance.CASSATION: "30",
}


class SudactScraper:
    def __init__(self, headless: bool = True):
        self.headless = headless

    def search_cases(
        self,
        court: CourtConfig,
        date_from: date,
        date_to: date,
        instance: Instance = Instance.FIRST,
        content_query: str = "перепланировка",
    ) -> Iterator[Decision]:
        params = (
            f"regular-txt={content_query}"
            f"&regular-date_from={date_from.strftime('%d.%m.%Y')}"
            f"&regular-date_to={date_to.strftime('%d.%m.%Y')}"
            f"&regular-workflow_stage={_INSTANCE_STAGE.get(instance, '10')}"
            f"&regular-area={_NN_AREA_CODE}"
            f"&regular-court={court.name}"
        )
        url = f"{_BASE}?{params}"

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)

            links = page.eval_on_selector_all(
                "#searchResult a[href*='/regular/doc/']",
                "els => els.map(e => ({href: e.href, text: e.innerText.trim()}))",
            )
            browser.close()

        for item in links:
            href = item.get("href", "")
            if not href or href.rstrip("/").endswith("/regular/doc"):
                continue
            text_preview = item.get("text", "")
            if not matches_case_type(text_preview):
                continue
            case_number = text_preview.split()[0] if text_preview else href.rsplit("/", 1)[-1]
            yield Decision(
                case_number=case_number,
                instance=instance,
                court_name=court.name,
                district=court.district or court.name,
                judge_full_name="",
                outcome=Outcome.PENDING,
                has_full_text=False,
                source_links={"sudact": href},
            )
