"""
Скрапер vsrf.ru — раздел 6 ТЗ (надзорная инстанция).

Поиск: https://vsrf.ru/search/?keyword=...&date_start=...&date_finish=...
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import date

from bs4 import BeautifulSoup

from ..markers import matches_case_type
from ..models import Decision, Instance, Outcome
from .base import RateLimitedSession
from .parsers import parse_date, parse_outcome

logger = logging.getLogger(__name__)

_BASE = "https://vsrf.ru"


class VsrfScraper:
    def __init__(self):
        self.session = RateLimitedSession()

    def search_cases(
        self,
        date_from: date,
        date_to: date,
        content_query: str = "перепланировка",
    ) -> Iterator[Decision]:
        params = {
            "keyword": content_query,
            "date_start": date_from.strftime("%d.%m.%Y"),
            "date_finish": date_to.strftime("%d.%m.%Y"),
            "search_sections[]": "documents",
        }
        resp = self.session.get(f"{_BASE}/search/", params=params, verify=False)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "lxml")

        for a in soup.select("a[href*='/documents/']"):
            href = a["href"]
            if not re.search(r"/documents/(?:own|all)/\d+", href):
                continue
            title = a.get_text(strip=True)
            if not matches_case_type(title):
                continue
            full_url = href if href.startswith("http") else f"{_BASE}{href}"
            case_m = re.search(r"([0-9]+[а-яА-Я]?-[0-9]+/[0-9]{2,4})", title)
            yield Decision(
                case_number=case_m.group(1) if case_m else href.rstrip("/").split("/")[-1],
                instance=Instance.SUPREME,
                court_name="Верховный Суд РФ",
                district="",
                judge_full_name="",
                outcome=Outcome.PENDING,
                has_full_text=False,
                source_links={"vsrf": full_url},
            )

    def fetch_document(self, url: str) -> str:
        resp = self.session.get(url, verify=False)
        resp.encoding = "utf-8"
        return resp.text
