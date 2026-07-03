from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Instance(Enum):
    FIRST = 1       # районный суд
    APPEAL = 2      # апелляция (областной суд)
    CASSATION = 3   # кассация (1kas.sudrf.ru и т.п.)
    SUPREME = 4     # Верховный Суд РФ


class Outcome(Enum):
    SATISFIED = "Удовлетворен"
    DENIED = "Отказан"
    PENDING = "На проверку"  # текст решения ещё не найден


@dataclass
class Decision:
    case_number: str
    instance: Instance
    court_name: str
    district: str
    judge_full_name: str
    outcome: Outcome
    decision_date: date | None = None
    case_number_secondary: str | None = None  # п.8.1 — если у решения два номера

    has_full_text: bool = False
    text_local_path: str | None = None

    plaintiff_full_name: str | None = None
    representative_full_name: str | None = None
    defendant_full_name: str | None = None

    has_bearing_wall_mention: bool = False
    expert_orgs: list[str] = field(default_factory=list)

    # {"sudrf": url, "sudact": url, "sudreshenia": url, "vsrf": url, "bsr": url}
    source_links: dict[str, str] = field(default_factory=dict)

    # общий id дела, связывающий Decision одного истца по всем инстанциям
    chain_id: str | None = None


@dataclass
class CaseChain:
    chain_id: str
    decisions: list[Decision] = field(default_factory=list)

    def sorted_by_instance(self) -> list[Decision]:
        return sorted(self.decisions, key=lambda d: d.instance.value)

    @property
    def district(self) -> str:
        first = self.sorted_by_instance()[0]
        return first.district

    @property
    def primary_case_number(self) -> str:
        return self.sorted_by_instance()[0].case_number
