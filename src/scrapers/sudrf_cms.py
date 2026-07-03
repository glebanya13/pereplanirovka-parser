"""
Скрапер судов на CMS sudrf.ru — разделы 3.1, 4.1, 5.1 ТЗ.

Поиск дел через форму «Поиск по делам» (Playwright), карточка дела — name_op=case.
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

from ..config import CourtConfig
from ..linking import extract_referenced_case_numbers
from ..markers import extract_expert_orgs, has_bearing_wall_mention, matches_case_type
from ..models import Decision, Instance, Outcome
from .parsers import parse_date, parse_judge, parse_outcome, parse_plaintiff, parse_representative

logger = logging.getLogger(__name__)


class SudrfCmsScraper:
    def __init__(
        self,
        host: str,
        court_name: str,
        district: str,
        headless: bool = True,
        raw_dir: Path | None = None,
    ):
        self.host = host
        self.court_name = court_name
        self.district = district
        self.headless = headless
        self.raw_dir = raw_dir

    @classmethod
    def from_court(cls, court: CourtConfig, headless: bool = True, raw_dir: Path | None = None) -> SudrfCmsScraper:
        if not court.host:
            raise ValueError(f"У суда {court.name} не задан host")
        return cls(
            host=court.host,
            court_name=court.name,
            district=court.district or court.name,
            headless=headless,
            raw_dir=raw_dir,
        )

    def _base_url(self) -> str:
        return f"https://{self.host}"

    def lookup_by_case_number(
        self,
        case_number: str,
        instance: Instance = Instance.FIRST,
    ) -> Decision | None:
        """Ищет дело по номеру на сайте суда, возвращает карточку + ссылку."""
        date_fmt = "%d.%m.%Y"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page()
            try:
                page.goto(f"{self._base_url()}/modules.php?name=sud_delo&srv_num=2", timeout=60000)
                if "некорректен" in page.content().lower():
                    raise RuntimeError(f"sudrf.ru ({self.host}) блокирует IP")

                page.evaluate("show_search(1,1)")
                page.wait_for_timeout(1500)
                page.fill('input[name="g1_case__CASE_NUMBERSS"]', case_number)
                page.locator('input[value="Найти"]').click()
                page.wait_for_timeout(4000)

                case_link = page.locator('a[href*="name_op=case"]').first
                if not case_link.count():
                    return None

                href = case_link.get_attribute("href") or ""
                case_url = href if href.startswith("http") else f"{self._base_url()}/{href.lstrip('./')}"
                page.goto(case_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
                text = page.inner_text("body")
                html = page.content()
            finally:
                browser.close()

        if not matches_case_type(text) and not matches_case_type(html):
            return None

        return self._build_decision(case_number, text, case_url, instance)

    def search_cases(
        self,
        date_from: date,
        date_to: date,
        instance: Instance = Instance.FIRST,
        content_query: str = "перепланировка",
    ) -> Iterator[Decision]:
        """Поиск по дате решения; фильтр по маркерам на карточках (медленно)."""
        case_refs = self._search_result_links(date_from, date_to)
        logger.info("sudrf %s: в выдаче %s дел за период", self.host, len(case_refs))

        for case_url, label in case_refs[:200]:
            try:
                text, html = self._fetch_page(case_url)
            except Exception as exc:
                logger.warning("sudrf: не удалось открыть %s: %s", case_url, exc)
                continue
            if not matches_case_type(text) and not matches_case_type(html):
                continue
            case_m = re.search(r"([0-9]+[а-яА-Я]?-[0-9]+/[0-9]{2,4})", label) or re.search(
                r"([0-9]+[а-яА-Я]?-[0-9]+/[0-9]{2,4})", text
            )
            if not case_m:
                continue
            decision = self._build_decision(case_m.group(1), text, case_url, instance)
            if decision:
                yield decision
            time.sleep(1)

    def _search_result_links(self, date_from: date, date_to: date) -> list[tuple[str, str]]:
        date_fmt = "%d.%m.%Y"
        refs: list[tuple[str, str]] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page()
            page.goto(f"{self._base_url()}/modules.php?name=sud_delo&srv_num=2", timeout=60000)
            page.evaluate("show_search(1,1)")
            page.wait_for_timeout(1500)
            page.fill('input[name="g1_case__RESULT_DATE1D"]', date_from.strftime(date_fmt))
            page.fill('input[name="g1_case__RESULT_DATE2D"]', date_to.strftime(date_fmt))
            page.locator('input[value="Найти"]').click()
            page.wait_for_timeout(5000)

            for a in page.locator('a[href*="name_op=case"]').all():
                href = a.get_attribute("href") or ""
                label = a.inner_text().strip()
                if not href or not label:
                    continue
                url = href if href.startswith("http") else f"{self._base_url()}/{href.lstrip('./')}"
                refs.append((url, label))
            browser.close()
        return refs

    def _fetch_page(self, url: str) -> tuple[str, str]:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            text = page.inner_text("body")
            html = page.content()
            browser.close()
        return text, html

    def _build_decision(
        self, case_number: str, text: str, url: str, instance: Instance
    ) -> Decision | None:
        outcome = parse_outcome(text)
        judge = parse_judge(text)
        decision_date = parse_date(text)

        text_path: str | None = None
        if text and self.raw_dir:
            text_dir = self.raw_dir / "sudrf"
            text_dir.mkdir(parents=True, exist_ok=True)
            safe = case_number.replace("/", "-")
            text_path = str(text_dir / f"{safe}.txt")
            Path(text_path).write_text(text, encoding="utf-8")

        decision = Decision(
            case_number=case_number,
            instance=instance,
            court_name=self.court_name,
            district=self.district,
            judge_full_name=judge,
            outcome=outcome,
            decision_date=decision_date,
            has_full_text=bool(text and len(text) > 500),
            text_local_path=text_path,
            plaintiff_full_name=parse_plaintiff(text),
            representative_full_name=parse_representative(text),
            has_bearing_wall_mention=has_bearing_wall_mention(text),
            expert_orgs=extract_expert_orgs(text),
            source_links={"sudrf": url},
        )
        decision._full_text = text  # type: ignore[attr-defined]
        decision._referenced_numbers = list(extract_referenced_case_numbers(text))  # type: ignore[attr-defined]
        return decision
