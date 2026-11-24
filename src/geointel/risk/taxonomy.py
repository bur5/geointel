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
    TSUNAMI = "tsunami"
    TROPICAL_CYCLONE = "tropical_cyclone"
    FLOOD = "flood"
    VOLCANO = "volcano"
    DROUGHT = "drought"
    WILDFIRE = "wildfire"
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
    group: str = "conflict"  # conflict | natural | society


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
        group="society",
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
        group="natural",
    ),
    *(
        EventTypeSpec(
            key,
            en,
            ru,
            f"GDACS (UN/EC): a {en.lower()} event with an Orange or Red alert that lists the "
            "country among affected countries. Orange/Red alerts reflect a likely need for "
            "international humanitarian assistance (exposed population and vulnerability).",
            f"GDACS (ООН/ЕК): событие «{ru.lower()}» с оранжевым или красным уровнем тревоги, "
            "затрагивающее страну. Оранжевый и красный уровни означают вероятную потребность в "
            "международной гуманитарной помощи (с учётом населения в зоне и уязвимости).",
            modeled=True,
            group="natural",
        )
        for key, en, ru in (
            (EventType.TROPICAL_CYCLONE, "Tropical cyclone", "Тропический циклон (ураган, тайфун)"),
            (EventType.FLOOD, "Major flood", "Сильное наводнение"),
            (EventType.VOLCANO, "Dangerous volcanic eruption", "Опасное извержение вулкана"),
            (EventType.DROUGHT, "Severe drought", "Сильная засуха"),
            (EventType.WILDFIRE, "Major wildfire", "Крупный лесной пожар"),
        )
    ),
    EventTypeSpec(
        EventType.TSUNAMI,
        "Tsunami",
        "Цунами",
        "NOAA NCEI Global Historical Tsunami Database: a definite or probable tsunami "
        "(validity 3–4) whose source or effects are recorded for the country.",
        "База цунами NOAA NCEI: достоверное или вероятное цунами (достоверность 3–4), "
        "источник или последствия которого зафиксированы в стране.",
        modeled=True,
        group="natural",
    ),
    EventTypeSpec(
        EventType.MASS_PROTEST,
        "Mass protests / unrest",
        "Массовые протесты и беспорядки",
        "Not yet modeled.",
        "Пока не моделируется.",
        modeled=False,
        group="society",
    ),
    EventTypeSpec(
        EventType.POLITICAL_CRISIS,
        "Political crisis",
        "Политический кризис",
        "Not yet modeled.",
        "Пока не моделируется.",
        modeled=False,
        group="society",
    ),
    EventTypeSpec(
        EventType.ECONOMIC_CRISIS,
        "Economic crisis",
        "Экономический кризис",
        "World Bank WDI: a year in which real GDP falls by more than 3% or consumer-price "
        "inflation exceeds 40%.",
        "Всемирный банк (WDI): год, в котором реальный ВВП падает более чем на 3% или "
        "инфляция потребительских цен превышает 40%.",
        modeled=True,
        group="society",
    ),
    EventTypeSpec(
        EventType.HUMANITARIAN_CRISIS,
        "Humanitarian crisis",
        "Гуманитарный кризис",
        "UN OCHA Financial Tracking Service: a year with a UN-coordinated humanitarian "
        "response plan or flash appeal for the country alone.",
        "UN OCHA FTS: год, когда для страны действовал отдельный гуманитарный план "
        "реагирования ООН или срочный призыв (flash appeal).",
        modeled=True,
        persistent_state=True,
        group="society",
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
