#!/usr/bin/env python3
"""
Проверка доступности источников. Запускать без VPN на российском интернете.

    python scripts/check_sources.py
"""
from __future__ import annotations

import sys
import urllib3

import requests

urllib3.disable_warnings()

SOURCES = [
    ("sudact.ru", "https://sudact.ru/"),
    ("vsrf.ru", "https://vsrf.ru/"),
    ("судебныерешения.рф", "https://судебныерешения.рф/"),
    ("avtozavodsky--nnov.sudrf.ru", "https://avtozavodsky--nnov.sudrf.ru/modules.php?name=sud_delo&srv_num=2"),
    ("oblsud--nnov.sudrf.ru", "https://oblsud--nnov.sudrf.ru/modules.php?name=sud_delo&srv_num=2"),
    ("1kas.sudrf.ru", "https://1kas.sudrf.ru/modules.php?name=sud_delo&srv_num=2"),
    ("nizegorodsky--nnov.sudrf.ru", "https://nizegorodsky--nnov.sudrf.ru/"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"}


def check(name: str, url: str) -> tuple[str, str]:
    try:
        r = requests.get(url, timeout=20, verify=False, headers=HEADERS)
        blocked = "некорректен" in r.text.lower()
        if blocked:
            return "BLOCKED", "IP заблокирован (нужен российский интернет без VPN)"
        if r.status_code == 200:
            return "OK", f"HTTP 200, {len(r.text)} bytes"
        return "WARN", f"HTTP {r.status_code}"
    except requests.exceptions.ConnectTimeout:
        return "TIMEOUT", "connect timeout — возможно VPN/прокси блокирует"
    except requests.exceptions.SSLError as e:
        return "SSL_ERROR", str(e)[:80]
    except requests.RequestException as e:
        return "ERROR", str(e)[:80]


def main() -> int:
    print("Проверка источников (отключите VPN перед запуском):\n")
    problems = 0
    for name, url in SOURCES:
        status, detail = check(name, url)
        icon = {"OK": "✓", "WARN": "?", "BLOCKED": "✗", "TIMEOUT": "✗", "SSL_ERROR": "✗", "ERROR": "✗"}.get(status, "?")
        print(f"  {icon} {name:30s} {status:8s}  {detail}")
        if status != "OK":
            problems += 1
    print()
    if problems:
        print(f"Проблемных источников: {problems}. См. HANDOFF.md.")
        return 1
    print("Все источники доступны.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
