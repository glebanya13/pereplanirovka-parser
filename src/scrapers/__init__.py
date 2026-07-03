"""Скраперы источников данных."""
from .sudact import SudactScraper
from .sudreshenia import SudresheniaScraper
from .sudrf_cms import SudrfCmsScraper
from .vsrf import VsrfScraper

SudrfDistrictScraper = SudrfCmsScraper

__all__ = [
    "SudactScraper",
    "SudresheniaScraper",
    "SudrfCmsScraper",
    "SudrfDistrictScraper",
    "VsrfScraper",
]
