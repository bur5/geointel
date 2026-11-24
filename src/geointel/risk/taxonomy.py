"""Event types and horizons for the global risk snapshot.

Every event type carries an explicit resolution criterion so that forecasts can later be
scored. Types without a model are listed with ``modeled=False`` and are reported as
unavailable, never as zero risk.
"""

from dataclasses import dataclass
from enum import StrEnum


class EventType(StrEnum):
    INTERNAL_ARMED_CONFLICT = "internal_armed_conflict"
    INTERSTATE_CONFLICT = "interstate_conflict"
    COUP_ATTEMPT = "coup_attempt"
    MAJOR_EARTHQUAKE = "major_earthquake"
    MASS_PROTEST = "mass_protest"
    POLITICAL_CRISIS = "political_crisis"
    ECONOMIC_CRISIS = "economic_crisis"
    HUMANITARIAN_CRISIS = "humanitarian_crisis"


class Question(StrEnum):
    """What a probability refers to."""

    ONSET_WITHIN = "onset_within"  # at least one qualifying event/year starts within horizon
    ACTIVE_AT_END = "active_at_end"  # an ongoing state is still active at the horizon end


@dataclass(frozen=True)
class EventTypeSpec:
    key: EventType
    label_en: str
    label_ru: str
    resolution_en: str
    resolution_ru: str
    modeled: bool
    persistent_state: bool = False


EVENT_TYPES: tuple[EventTypeSpec, ...] = (
    EventTypeSpec(
        EventType.INTERNAL_ARMED_CONFLICT,
        "Internal armed conflict",
        "Внутренний вооружённый конфликт",
        "UCDP/PRIO: an intrastate or internationalized intrastate conflict located in the "
        "country with at least 25 battle-related deaths in a calendar year.",
        "UCDP/PRIO: внутригосударственный (в т.ч. интернационализированный) конфликт на "
        "территории страны с не менее чем 25 боевыми погибшими за календарный год.",
        modeled=True,
        persistent_state=True,
    ),
    EventTypeSpec(
        EventType.INTERSTATE_CONFLICT,
        "Interstate armed conflict",
        "Межгосударственный вооружённый конфликт",
        "UCDP/PRIO: the country's government is a primary party to an interstate conflict "
        "with at least 25 battle-related deaths in a calendar year.",
        "UCDP/PRIO: правительство страны — основная сторона межгосударственного конфликта "
        "с не менее чем 25 боевыми погибшими за календарный год.",
        modeled=True,
        persistent_state=True,
    ),
    EventTypeSpec(
        EventType.COUP_ATTEMPT,
        "Coup attempt",
        "Попытка государственного переворота",
        "Powell & Thyne: an illegal and overt attempt by the military or other state elites "
        "to unseat the sitting executive (successful or failed).",
        "Powell & Thyne: незаконная открытая попытка военных или элит сместить действующую "
        "исполнительную власть (успешная или неудачная).",
        modeled=True,
    ),
    EventTypeSpec(
        EventType.MAJOR_EARTHQUAKE,
        "Major earthquake (M6.5+)",
        "Сильное землетрясение (M6,5+)",
        "USGS: an earthquake of magnitude 6.5 or greater whose USGS location label names "
        "the country. Offshore events without a country label are not attributed.",
        "USGS: землетрясение магнитудой 6,5 и выше, в описании места которого USGS указывает "
        "страну. Морские события без страны не учитываются.",
        modeled=True,
    ),
    EventTypeSpec(
        EventType.MASS_PROTEST,
        "Mass protests / unrest",
        "Массовые протесты и беспорядки",
        "Not yet modeled.",
        "Пока не моделируется.",
        modeled=False,
    ),
    EventTypeSpec(
        EventType.POLITICAL_CRISIS,
        "Political crisis",
        "Политический кризис",
        "Not yet modeled.",
        "Пока не моделируется.",
        modeled=False,
    ),
    EventTypeSpec(
        EventType.ECONOMIC_CRISIS,
        "Economic crisis",
        "Экономический кризис",
        "Not yet modeled.",
        "Пока не моделируется.",
        modeled=False,
    ),
    EventTypeSpec(
        EventType.HUMANITARIAN_CRISIS,
        "Humanitarian crisis",
        "Гуманитарный кризис",
        "Not yet modeled.",
        "Пока не моделируется.",
        modeled=False,
    ),
)

SPEC_BY_TYPE = {spec.key: spec for spec in EVENT_TYPES}


@dataclass(frozen=True)
class Horizon:
    key: str
    years: float
    label_en: str
    label_ru: str


HORIZONS: tuple[Horizon, ...] = (
    Horizon("1m", 1 / 12, "1 month", "1 месяц"),
    Horizon("1y", 1.0, "1 year", "1 год"),
    Horizon("5y", 5.0, "5 years", "5 лет"),
    Horizon("10y", 10.0, "10 years", "10 лет"),
)
