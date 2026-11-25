"""Data types shared by the scenario catalogue modules."""

from dataclasses import dataclass, field

NATO = (
    "ALB BEL BGR CAN HRV CZE DNK EST FIN FRA DEU GRC HUN ISL ITA LVA LTU LUX MNE NLD MKD NOR "
    "POL PRT ROU SVK SVN ESP SWE TUR GBR USA"
).split()
EU = (
    "AUT BEL BGR HRV CYP CZE DNK EST FIN FRA DEU GRC HUN IRL ITA LVA LTU LUX MLT NLD POL PRT "
    "ROU SVK SVN ESP SWE"
).split()

HORIZON_YEARS = {"1m": 1 / 12, "1y": 1.0, "5y": 5.0, "10y": 10.0}


@dataclass(frozen=True)
class Exposure:
    role: str  # party | frontline | ally | economic
    countries: tuple[str, ...]
    reason_ru: str
    reason_en: str


@dataclass(frozen=True)
class Warning:
    date: str
    source: str
    url: str
    direction: int  # +1 escalation, -1 de-escalation, 0 mixed
    summary_ru: str
    summary_en: str


@dataclass(frozen=True)
class Assessment:
    """A published official judgement, mapped to a probability range by its wording."""

    date: str
    source: str
    url: str
    phrase: str  # key of warning_signs.ESTIMATIVE
    years: float  # the period the judgement refers to
    quote_en: str


@dataclass(frozen=True)
class Scenario:
    key: str
    title_ru: str
    title_en: str
    event_ru: str
    event_en: str
    polarity: int  # +1: the event is an escalation; -1: the event is a de-escalation
    expert: tuple[float, float, float]  # annual hazard (mid, low, high)
    expert_basis_ru: str
    expert_basis_en: str
    side_a: tuple[str, ...] = ()
    side_b: tuple[str, ...] = ()
    market_queries: tuple[str, ...] = ()
    market_groups: tuple[tuple[str, ...], ...] = ()
    market_exclude: tuple[str, ...] = ()
    # Markets whose "Yes" is the opposite of the scenario (e.g. "ceasefire holds").
    market_inverse: tuple[tuple[str, ...], ...] = ()
    # Words that mark a closer fit to the scenario definition; such markets are preferred.
    market_prefer: tuple[str, ...] = ()
    metaculus_queries: tuple[str, ...] = ()
    assessments: tuple[Assessment, ...] = ()
    use_history: bool = True  # off where the dyad's past says nothing about this event type
    milex: tuple[str, ...] = ()
    gpr: tuple[str, ...] = ()
    war_context: tuple[str, ...] = ()  # countries whose ongoing interstate war raises risk
    exposures: tuple[Exposure, ...] = ()
    warnings: tuple[Warning, ...] = field(default_factory=tuple)
    # Which warning-sign risk type moves this scenario (see warning_signs.RISKS).
    risk: str = "interstate_conflict"
    # Country signs move this scenario only if they are evidence about its event.
    use_signs: bool = True
    # Sign keys whose evidence the expert prior already includes (not counted again).
    prior_includes: tuple[str, ...] = ()


def _t(codes: str) -> tuple[str, ...]:
    return tuple(codes.split())
