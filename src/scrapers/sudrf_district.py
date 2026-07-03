"""
Скрапер судов на CMS сети sudrf.ru — обратная совместимость.

Реализация перенесена в sudrf_cms.py.
"""
from .sudrf_cms import SudrfCmsScraper as SudrfDistrictScraper

__all__ = ["SudrfDistrictScraper"]
