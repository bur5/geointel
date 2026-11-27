"""Empirical-Bayes base-rate model with horizon-consistent probabilities.

Each country's annual history for an event type is shrunk towards the global distribution
of country rates (Beta-Binomial empirical Bayes), with optional recency weighting.
Persistent states (armed conflicts) use a two-state Markov model, so an ongoing conflict is
assessed by the probability that it is still active at the horizon end, while a country at
peace is assessed by the probability of onset within the horizon.

This is a transparent baseline ("outside view"), not a calibrated forecast. Intervals are
90% posterior intervals of the parameters propagated through the horizon formula.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from math import exp, log
from statistics import fmean

from geointel.risk.betamath import beta_ppf
from geointel.risk.taxonomy import HORIZONS, EventType, Question

METHOD_NAME = "empirical-bayes-base-rate-v0"
LOWER_Q, UPPER_Q = 0.05, 0.95
_P_FLOOR, _P_CEIL = 1e-5, 1 - 1e-6


@dataclass(frozen=True)
class TypeHistory:
    """Observed annual occurrence of one event type for all countries."""

    event_type: EventType
    source: str
    start_year: int
    end_year: int
    years_with_event: Mapping[str, frozenset[int]]
    half_life_years: float | None = 10.0
    unresolved_labels: int = 0
    records: int = 0
    metadata: Mapping[str, object] = field(default_factory=dict)
    # Optional per-country observed years (sources with gaps). When set, countries without
    # observations are not assessed (reported as no data, never as zero).
    observed_years: Mapping[str, frozenset[int]] | None = None


@dataclass(frozen=True)
class Counts:
    successes: float
    trials: float


@dataclass(frozen=True)
class BetaPrior:
    a: float
    b: float


@dataclass(frozen=True)
class Estimate:
    mean: float
    low: float
    high: float


@dataclass(frozen=True)
class HorizonProbability:
    p: float
    low: float
    high: float


@dataclass(frozen=True)
class CountryRisk:
    iso3: str
    event_type: EventType
    question: Question
    active: bool | None
    state_as_of: int
    horizons: dict[str, HorizonProbability]
    confidence: str
    exposure_years: int
    event_years: int
    last_event_year: int | None


def _weight(year: int, end_year: int, half_life: float | None) -> float:
    if half_life is None:
        return 1.0
    return 0.5 ** ((end_year - year) / half_life)


def exposure(history: TypeHistory, first_year: int | None, iso3: str | None = None) -> list[int]:
    start = max(history.start_year, first_year or history.start_year)
    years = range(start, history.end_year + 1)
    if history.observed_years is not None:
        observed = history.observed_years.get(iso3 or "", frozenset())
        return [year for year in years if year in observed]
    return list(years)


def bernoulli_counts(history: TypeHistory, iso3: str, first_year: int | None) -> Counts:
    years = history.years_with_event.get(iso3, frozenset())
    s = t = 0.0
    for year in exposure(history, first_year, iso3):
        w = _weight(year, history.end_year, history.half_life_years)
        t += w
        s += w * (year in years)
    return Counts(s, t)


def transition_counts(
    history: TypeHistory, iso3: str, first_year: int | None
) -> tuple[Counts, Counts]:
    """Weighted (onset | peace) and (continuation | active) counts."""
    years = history.years_with_event.get(iso3, frozenset())
    span = exposure(history, first_year, iso3)
    observed = set(span)
    s01 = t01 = s11 = t11 = 0.0
    for year in span[1:]:
        if (year - 1) not in observed:
            continue  # no transition across a data gap
        w = _weight(year, history.end_year, history.half_life_years)
        now = year in years
        if (year - 1) in years:
            t11 += w
            s11 += w * now
        else:
            t01 += w
            s01 += w * now
    return Counts(s01, t01), Counts(s11, t11)


def fit_prior(
    counts: Iterable[Counts],
    fallback: BetaPrior | None = None,
    max_strength: float = 400.0,
) -> BetaPrior:
    """Method-of-moments Beta prior across countries (empirical Bayes)."""
    usable = [c for c in counts if c.trials >= 1.0]
    if not usable:
        return fallback or BetaPrior(0.5, 10.0)
    rates = [c.successes / c.trials for c in usable]
    mean = min(max(fmean(rates), 1e-4), 0.95)
    observed_var = fmean([(r - mean) ** 2 for r in rates])
    sampling_var = fmean([mean * (1 - mean) / c.trials for c in usable])
    between = max(observed_var - sampling_var, mean * (1 - mean) / 400)
    strength = mean * (1 - mean) / between - 1
    strength = min(max(strength, 2.0), max_strength)
    return BetaPrior(mean * strength, (1 - mean) * strength)


def posterior(prior: BetaPrior, counts: Counts) -> Estimate:
    a = prior.a + counts.successes
    b = prior.b + max(counts.trials - counts.successes, 0.0)
    return Estimate(a / (a + b), beta_ppf(LOWER_Q, a, b), beta_ppf(UPPER_Q, a, b))


def _clip(p: float) -> float:
    return min(max(p, _P_FLOOR), _P_CEIL)


def onset_within(annual_p: float, years: float) -> float:
    return 1.0 - (1.0 - _clip(annual_p)) ** years


def active_at_end(p01: float, p11: float, years: float) -> float:
    """Two-state continuous-time Markov chain started in the active state."""
    lam = -log(1.0 - _clip(p01))
    mu = -log(_clip(p11))
    total = lam + mu
    return lam / total + (mu / total) * exp(-total * years)


def confidence_label(one_year: HorizonProbability) -> str:
    width = one_year.high - one_year.low
    relative = width / max(one_year.p, 1e-6)
    if width <= 0.10 and relative <= 1.0:
        return "high"
    if width <= 0.25 and relative <= 3.0:
        return "medium"
    return "low"


def _horizons(function, low_args, mid_args, high_args) -> dict[str, HorizonProbability]:
    return {
        h.key: HorizonProbability(
            p=function(*mid_args, h.years),
            low=function(*low_args, h.years),
            high=function(*high_args, h.years),
        )
        for h in HORIZONS
    }


MIN_GROUP_COUNTRIES = 8
# 10-year horizon: weight of the group rate. The rest is the world rate, a crude allowance
# for a change of regime within 10 years (0.8 gave stable democracies ~4%, implausibly high).
GROUP_LONG_MIX = 0.95


# How many times a member's mean weighted history the group prior may weigh (1.10.0: 2,
# Fable round 4 #2). Chosen on the time machine's tuning period (docs/backtest-rules.md).
GROUP_PRIOR_CAP_MULT = 2.0


def group_priors(
    counts: Mapping[str, Counts], groups: Mapping[str, str], fallback: BetaPrior
) -> dict[str, BetaPrior]:
    """Empirical-Bayes prior per group of similar countries (falls back to the world prior
    when a group has fewer than ``MIN_GROUP_COUNTRIES`` members with data)."""
    members: dict[str, list[Counts]] = {}
    for iso3, c in counts.items():
        if iso3 in groups:
            members.setdefault(groups[iso3], []).append(c)
    # Within a small group the spread between countries is often not detectable against
    # sampling noise; the prior then hit the 400 cap and every member got the same number
    # (US, Thailand and Egypt all ~7.5% a year for coups). The prior may weigh at most twice
    # a member's typical weighted history, so a country's own record still counts
    # (Fable round 4, #2; 1.10.0).
    out = {}
    for g, cs in members.items():
        usable = [c for c in cs if c.trials >= 1.0]
        if len(usable) < MIN_GROUP_COUNTRIES:
            out[g] = fallback
            continue
        cap = max(2.0, GROUP_PRIOR_CAP_MULT * fmean(c.trials for c in usable))
        out[g] = fit_prior(usable, fallback, max_strength=cap)
    return out


def assess_type(
    history: TypeHistory,
    countries: Mapping[str, int | None],
    persistent: bool,
    groups: Mapping[str, str] | None = None,
) -> list[CountryRisk]:
    """Assess every country in ``countries`` (iso3 -> first independent year or None).

    ``groups`` (non-persistent types only) shrinks each country towards similar countries
    instead of the world: iso3 -> group key. Countries without a group use the world prior.
    """
    results: list[CountryRisk] = []
    if persistent:
        transitions = {
            iso3: transition_counts(history, iso3, first) for iso3, first in countries.items()
        }
        prior01 = fit_prior(t[0] for t in transitions.values())
        prior11 = fit_prior(t[1] for t in transitions.values() if t[1].trials > 0)
    else:
        simple = {iso3: bernoulli_counts(history, iso3, f) for iso3, f in countries.items()}
        prior = fit_prior(simple.values())
        by_group = group_priors(simple, groups, prior) if groups else {}

    for iso3, first in countries.items():
        years = history.years_with_event.get(iso3, frozenset())
        span = exposure(history, first, iso3)
        if not span:
            continue
        observed = [y for y in span if y in years]
        active = span[-1] in years
        if persistent:
            onset_counts, continuation_counts = transitions[iso3]
            p01 = posterior(prior01, onset_counts)
            p11 = posterior(prior11, continuation_counts)
            if active:
                question = Question.ACTIVE_AT_END
                horizons = _horizons(
                    active_at_end,
                    (p01.low, p11.low),
                    (p01.mean, p11.mean),
                    (p01.high, p11.high),
                )
            else:
                question = Question.ONSET_WITHIN
                horizons = _horizons(onset_within, (p01.low,), (p01.mean,), (p01.high,))
        else:
            group_prior = by_group.get((groups or {}).get(iso3, ""), prior)
            estimate = posterior(group_prior, simple[iso3])
            question = Question.ONSET_WITHIN
            horizons = _horizons(onset_within, (estimate.low,), (estimate.mean,), (estimate.high,))
            if group_prior is not prior and "10y" in horizons:
                world = posterior(prior, simple[iso3])
                w = GROUP_LONG_MIX
                g10, years10 = horizons["10y"], next(h.years for h in HORIZONS if h.key == "10y")
                horizons["10y"] = HorizonProbability(
                    p=w * g10.p + (1 - w) * onset_within(world.mean, years10),
                    low=w * g10.low + (1 - w) * onset_within(world.low, years10),
                    high=w * g10.high + (1 - w) * onset_within(world.high, years10),
                )
        results.append(
            CountryRisk(
                iso3=iso3,
                event_type=history.event_type,
                question=question,
                active=active if persistent else None,
                state_as_of=span[-1],
                horizons=horizons,
                confidence=confidence_label(horizons["1y"]),
                exposure_years=len(span),
                event_years=len(observed),
                last_event_year=max(years) if years else None,
            )
        )
    return results
