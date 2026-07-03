"""Загрузка конфигурации регионов и судов из config/regions.yaml."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "regions.yaml"


@dataclass
class CourtConfig:
    name: str
    host: str | None = None
    district: str | None = None
    sudreshenia_id: int | None = None


@dataclass
class RegionConfig:
    city: str
    first_instance_courts: list[CourtConfig] = field(default_factory=list)
    appeal_court: CourtConfig | None = None
    cassation_court: CourtConfig | None = None
    supreme_court: CourtConfig | None = None


def _district_from_court_name(name: str) -> str:
    """«Автозаводский районный суд г. Нижнего Новгорода» → «Автозаводский район»."""
    for suffix in (
        " районный суд г. Нижнего Новгорода",
        " районный суд г. Нижний Новгород",
        " районный суд г.Нижний Новгород",
    ):
        if suffix in name:
            return name.split(suffix)[0] + " район"
    return name


def load_region(region_key: str = "nizhny_novgorod") -> RegionConfig:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    data = raw[region_key]

    courts = []
    for c in data["first_instance_courts"]:
        courts.append(
            CourtConfig(
                name=c["name"],
                host=c.get("host"),
                district=c.get("district") or _district_from_court_name(c["name"]),
                sudreshenia_id=c.get("sudreshenia_id"),
            )
        )

    appeal = data.get("appeal_court")
    cassation = data.get("cassation_court")
    supreme = data.get("supreme_court")

    return RegionConfig(
        city=data["city"],
        first_instance_courts=courts,
        appeal_court=CourtConfig(
            name=appeal["name"],
            host=appeal["host"],
            sudreshenia_id=appeal.get("sudreshenia_id"),
        )
        if appeal
        else None,
        cassation_court=CourtConfig(
            name=cassation["name"],
            host=cassation["host"],
            sudreshenia_id=cassation.get("sudreshenia_id"),
        )
        if cassation
        else None,
        supreme_court=CourtConfig(name=supreme["name"], host=supreme["host"]) if supreme else None,
    )
