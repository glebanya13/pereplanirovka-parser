"""
Скрапер судебныерешения.рф — разделы 3.2, 4.2, 5.2, 7.8.1, 11 ТЗ.

Основной источник с полными (не обезличенными) ФИО. Работает через HTTP
(requests), без Playwright: поиск — POST на /extended_filter, карточка дела —
GET /{id}.
"""
from __future__ import annotations

import logging
import re
import time
import urllib3
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from ..config import CourtConfig
from ..linking import extract_referenced_case_numbers
from ..markers import extract_expert_orgs, has_bearing_wall_mention, matches_case_type
from ..models import Decision, Instance, Outcome
from .base import RateLimitedSession
from .parsers import parse_date, parse_judge, parse_outcome, parse_plaintiff, parse_representative

logger = logging.getLogger(__name__)

BASE_URL = "https://судебныерешения.рф"

_INSTANCE_TO_CASE_TYPE = {
    Instance.FIRST: "gr_first",
    Instance.APPEAL: "gr_appeal",
    Instance.CASSATION: "gr_cass",
}


class SudresheniaScraper:
    def __init__(self, min_interval_seconds: float = 2.5, raw_dir: Path | None = None):
        self.session = RateLimitedSession(min_interval_seconds=min_interval_seconds)
        self.raw_dir = raw_dir
        self._token: str | None = None

    def _get_token(self, form: str = "extendedSearch") -> str:
        path = "/extended-search" if form == "extendedSearch" else "/"
        resp = self.session.get(f"{BASE_URL}{path}", verify=False)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "lxml")
        inp = soup.find("input", {"name": f"{form}[_token]"})
        if not inp or not inp.get("value"):
            raise RuntimeError(f"Не удалось получить CSRF-токен с {BASE_URL}{path}")
        return inp["value"]

    def search_cases(
        self,
        court: CourtConfig,
        date_from: date,
        date_to: date,
        instance: Instance = Instance.FIRST,
        content_query: str = "перепланировка",
    ) -> Iterator[Decision]:
        """Ищет дела по суду и периоду, отбирает по маркерам п.8.2 ТЗ."""
        if not court.sudreshenia_id:
            logger.warning("У суда %s нет sudreshenia_id — пропуск", court.name)
            return

        case_type = _INSTANCE_TO_CASE_TYPE.get(instance)
        if not case_type:
            logger.warning("Инстанция %s не поддерживается судебныерешения.рф", instance)
            return

        token = self._get_token()
        date_fmt = "%d.%m.%Y"
        data: dict[str, str] = {
            "extendedSearch[content]": content_query,
            "extendedSearch[case_number]": "",
            "extendedSearch[person_info][0][person]": "",
            "extendedSearch[person_info][0][person_status]": "",
            "extendedSearch[judge]": "",
            "extendedSearch[uniq_id]": "",
            "extendedSearch[case_type]": case_type,
            "extendedSearch[entry_start]": "",
            "extendedSearch[entry_end]": "",
            "extendedSearch[result_start]": date_from.strftime(date_fmt),
            "extendedSearch[result_end]": date_to.strftime(date_fmt),
            "extendedSearch[_token]": token,
            f"extendedSearch[court][]": str(court.sudreshenia_id),
        }

        resp = self.session.session.post(
            f"{BASE_URL}/extended_filter",
            data=data,
            timeout=120,
            verify=False,
            allow_redirects=True,
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "lxml")

        case_ids = self._extract_case_ids(soup)
        logger.info("судебныерешения.рф: %s — найдено %s дел", court.name, len(case_ids))

        for case_id in case_ids:
            try:
                decision = self.fetch_case(case_id, court, instance)
            except Exception as exc:
                logger.warning("Ошибка загрузки дела %s: %s", case_id, exc)
                continue
            if decision and (
                matches_case_type(decision._full_text or "")
                or (content_query and matches_case_type(content_query))
            ):
                yield decision
            time.sleep(0.5)

    def search_region(
        self,
        date_from: date,
        date_to: date,
        region_id: int,
        case_stage: str = "nadzor",
        content_query: str = "перепланировка",
    ) -> Iterator[Decision]:
        """Поиск по региону (надзор/ВС РФ) без привязки к конкретному суду."""
        token = self._get_token()
        date_fmt = "%d.%m.%Y"
        data: dict[str, str] = {
            "extendedSearch[content]": content_query,
            "extendedSearch[case_number]": "",
            "extendedSearch[person_info][0][person]": "",
            "extendedSearch[person_info][0][person_status]": "",
            "extendedSearch[judge]": "",
            "extendedSearch[uniq_id]": "",
            "extendedSearch[case_type]": "",
            "extendedSearch[case_stage]": case_stage,
            "extendedSearch[entry_start]": "",
            "extendedSearch[entry_end]": "",
            "extendedSearch[result_start]": date_from.strftime(date_fmt),
            "extendedSearch[result_end]": date_to.strftime(date_fmt),
            "extendedSearch[_token]": token,
            f"extendedSearch[region][]": str(region_id),
        }
        resp = self.session.session.post(
            f"{BASE_URL}/extended_filter", data=data, timeout=120, verify=False, allow_redirects=True
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "lxml")
        case_ids = self._extract_case_ids(soup)
        logger.info("судебныерешения.рф регион %s (%s): %s дел", region_id, case_stage, len(case_ids))

        dummy_court = CourtConfig(name="", district="")
        for case_id in case_ids:
            try:
                decision = self.fetch_case(case_id, dummy_court, Instance.SUPREME)
            except Exception as exc:
                logger.warning("Ошибка загрузки дела %s: %s", case_id, exc)
                continue
            if decision and (
                matches_case_type(decision._full_text or "")
                or (content_query and matches_case_type(content_query))
            ):
                yield decision
            time.sleep(0.5)

    def _extract_case_ids(self, soup: BeautifulSoup) -> list[str]:
        ids: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.match(r"^/(\d+)(?:/extended)?/?$", href)
            if m:
                ids.append(m.group(1))
        return list(dict.fromkeys(ids))

    def _load_cached_case(self, case_id: str, court: CourtConfig, instance: Instance) -> Decision | None:
        if not self.raw_dir:
            return None
        text_dir = self.raw_dir / "sudreshenia"
        path = text_dir / f"*_{case_id}.txt"
        matches = list(text_dir.glob(f"*_{case_id}.txt"))
        if not matches:
            return None
        path = matches[0]
        text = path.read_text(encoding="utf-8", errors="replace")
        if "РЕШЕНИЕ" not in text and len(text) < 2000:
            return None
        m = re.match(r"^(.+?)_(\d+)\.txt$", path.name)
        if not m:
            return None
        case_number = re.sub(r"^(\d+[а-яА-Я]?-\d+)-(\d{4})", r"\1/\2", m.group(1))
        decision_text = text[text.find("РЕШЕНИЕ") :] if "РЕШЕНИЕ" in text else text
        judge = parse_judge(text) or parse_judge(decision_text)
        judge = re.sub(r"^судь[ьяи]\s+", "", judge or "", flags=re.I).strip()
        decision = Decision(
            case_number=case_number,
            instance=instance,
            court_name=court.name,
            district=court.district or court.name,
            judge_full_name=judge,
            outcome=parse_outcome(decision_text),
            decision_date=parse_date(text),
            has_full_text=True,
            text_local_path=str(path),
            plaintiff_full_name=parse_plaintiff(text),
            representative_full_name=parse_representative(text),
            has_bearing_wall_mention=has_bearing_wall_mention(decision_text),
            expert_orgs=extract_expert_orgs(decision_text),
            source_links={"sudreshenia": f"{BASE_URL}/{case_id}"},
        )
        decision._full_text = decision_text  # type: ignore[attr-defined]
        decision._referenced_numbers = list(extract_referenced_case_numbers(decision_text))  # type: ignore[attr-defined]
        return decision

    def fetch_case(
        self,
        case_id: str,
        court: CourtConfig,
        instance: Instance,
    ) -> Decision | None:
        cached = self._load_cached_case(case_id, court, instance)
        if cached:
            return cached

        full_text = ""
        url = f"{BASE_URL}/{case_id}"
        soup = BeautifulSoup("", "lxml")

        # HTTP
        for suffix in ("/extended", ""):
            page_url = f"{BASE_URL}/{case_id}{suffix}"
            try:
                resp = self.session.get(page_url, verify=False)
            except Exception:
                continue
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "lxml")
            for selector in ("div.decision", "#decision"):
                decision_el = soup.select_one(selector)
                if decision_el and len(decision_el.get_text(strip=True)) > 100:
                    full_text = decision_el.get_text("\n", strip=True)
                    url = page_url
                    break
            if not full_text and "РЕШЕНИЕ" in resp.text:
                body_text = soup.get_text("\n", strip=True)
                idx = body_text.find("РЕШЕНИЕ")
                if idx >= 0:
                    full_text = body_text[idx:]
                    url = page_url
            if full_text:
                break

        # Playwright fallback (текст часто грузится JS)
        if not full_text or len(full_text) < 100:
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(f"{BASE_URL}/{case_id}", wait_until="domcontentloaded", timeout=120000)
                    page.wait_for_timeout(4000)
                    body = page.inner_text("body")
                    url = f"{BASE_URL}/{case_id}"
                    if "РЕШЕНИЕ" in body:
                        full_text = body[body.find("РЕШЕНИЕ") :]
                    elif len(body) > 500:
                        full_text = body
                    browser.close()
            except Exception as exc:
                logger.debug("Playwright fallback для %s: %s", case_id, exc)

        case_number = self._meta_value(soup, "Номер дела") or ""
        if not case_number:
            m = re.search(r"дело\s*№\s*([0-9]+[а-яА-Я]?-[0-9]+/[0-9]{2,4})", full_text, re.I)
            case_number = m.group(1) if m else case_id

        court_name = self._meta_value(soup, "Суд") or court.name
        decision_date = parse_date(self._meta_value(soup, "Дата рассмотрения") or "")
        judge = parse_judge(full_text) or self._meta_value(soup, "Судья") or ""
        judge = re.sub(r"^судь[ьяи]\s+", "", judge, flags=re.I).strip()

        plaintiff = parse_plaintiff(full_text)
        representative = parse_representative(full_text)
        defendant = None
        participants = self._participants_from_table(soup)
        if not plaintiff:
            plaintiff = participants.get("ИСТЕЦ")
        if not representative:
            representative = participants.get("ПРЕДСТАВИТЕЛЬ") or participants.get("ПРЕДСТАВИТЕЛЬ ИСТЦА")
        defendant = participants.get("ОТВЕТЧИК")

        outcome = parse_outcome(full_text)

        text_path: str | None = None
        if full_text and self.raw_dir:
            text_dir = self.raw_dir / "sudreshenia"
            text_dir.mkdir(parents=True, exist_ok=True)
            safe_num = case_number.replace("/", "-")
            text_path = str(text_dir / f"{safe_num}_{case_id}.txt")
            Path(text_path).write_text(full_text, encoding="utf-8")

        has_text = bool(full_text and ("РЕШЕНИЕ" in full_text or len(full_text) > 2000))

        decision = Decision(
            case_number=case_number,
            instance=instance,
            court_name=court_name,
            district=court.district or court.name,
            judge_full_name=judge,
            outcome=outcome,
            decision_date=decision_date,
            has_full_text=has_text,
            text_local_path=text_path,
            plaintiff_full_name=plaintiff,
            representative_full_name=representative,
            defendant_full_name=defendant,
            has_bearing_wall_mention=has_bearing_wall_mention(full_text),
            expert_orgs=extract_expert_orgs(full_text),
            source_links={"sudreshenia": url},
        )
        decision._full_text = full_text  # type: ignore[attr-defined]
        decision._referenced_numbers = list(extract_referenced_case_numbers(full_text))  # type: ignore[attr-defined]
        return decision

    @staticmethod
    def _meta_value(soup: BeautifulSoup, label: str) -> str | None:
        for el in soup.find_all(string=re.compile(rf"^{re.escape(label)}", re.I)):
            parent = el.parent
            if parent:
                text = parent.get_text(" ", strip=True)
                if ":" in text:
                    return text.split(":", 1)[1].strip()
                sibling = parent.find_next(string=True)
                if sibling:
                    return sibling.strip()
        return None

    @staticmethod
    def _participants_from_table(soup: BeautifulSoup) -> dict[str, str]:
        """Парсит таблицу «Стороны по делу» на карточке дела."""
        result: dict[str, str] = {}
        for tr in soup.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            for i, cell in enumerate(cells):
                role = cell.upper().strip()
                if role in ("ИСТЕЦ", "ОТВЕТЧИК", "ПРЕДСТАВИТЕЛЬ", "ПРЕДСТАВИТЕЛЬ ИСТЦА", "ЗАЯВИТЕЛЬ"):
                    for j in range(i + 1, len(cells)):
                        name = cells[j].strip()
                        if name and name.upper() not in ("ИСТЕЦ", "ОТВЕТЧИК", "ПРОКУРОР", ""):
                            result[role] = name
                            break
        return result

    @staticmethod
    def _participant_name(soup: BeautifulSoup, status: str) -> str | None:
        for p in soup.find_all("p"):
            text = p.get_text("\n", strip=True)
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            for i, line in enumerate(lines):
                if status in line.upper() and i + 1 < len(lines):
                    candidate = lines[i + 1]
                    if re.match(r"^[А-ЯЁ][а-яё]+", candidate):
                        return candidate
        return None
