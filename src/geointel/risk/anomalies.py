"""Daily report of oddities in the published numbers (reviewer's advice, round 4, section 6).

Errors at the joins between parts of the model (a sign applied to the wrong event, a group in
which every country gets the same number) are invisible in descriptions and visible only in
the live numbers. These checks look for the patterns that caught the round-4 errors.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from statistics import median

# Liberal democracies should not carry the coup risk of closed autocracies.
REGIME_KEY = "coup_attempt"


def _p(country: Mapping, risk: str, horizon: str = "1y") -> float | None:
    item = ((country.get("risks") or {}).get(risk) or {}).get("horizons") or {}
    value = (item.get(horizon) or {}).get("p")
    return float(value) if value is not None else None


def check(
    snapshot: Mapping,
    signals: Mapping,
    previous_snapshot: Mapping | None = None,
    previous_signals: Mapping | None = None,
    regimes: Mapping[str, Mapping] | None = None,
) -> list[dict]:
    """A list of findings: {"kind", "iso3" (optional), "ru", "en"}."""
    found: list[dict] = []
    countries = {c["iso3"]: c for c in snapshot.get("countries", [])}
    danger = {k: (v.get("danger") or {}) for k, v in (signals.get("countries") or {}).items()}

    # 1. Danger level jumped by 2+ steps since the previous run.
    before = {
        k: (v.get("danger") or {}).get("level")
        for k, v in ((previous_signals or {}).get("countries") or {}).items()
    }
    for iso3, d in danger.items():
        old, new = before.get(iso3), d.get("level")
        if old and new and abs(new - old) >= 2:
            found.append(
                {
                    "kind": "level_jump",
                    "iso3": iso3,
                    "ru": f"уровень опасности изменился с {old} на {new} за день",
                    "en": f"danger level changed from {old} to {new} in a day",
                }
            )

    # 2. Model and foreign-ministry median disagree by 2+ steps.
    for iso3, d in danger.items():
        model, mfa = d.get("model_level"), d.get("ministry_median")
        if model and mfa and abs(model - mfa) >= 2:
            found.append(
                {
                    "kind": "mfa_divergence",
                    "iso3": iso3,
                    "ru": f"модель {model}, медиана МИД {mfa}",
                    "en": f"model {model}, ministry median {mfa}",
                }
            )

    # 3. Several countries with exactly the same probability although their own records
    # differ (a group prior that swamps each country's history, the 1.9.2 coup bug).
    # Countries with the same record (e.g. no events in 36 years) are expected to match.
    for spec in snapshot.get("event_types", []):
        key = spec.get("key")
        groups: dict[float, list[tuple]] = {}
        for c in countries.values():
            p = _p(c, key)
            if p is None or p < 0.01:
                continue
            basis = ((c.get("risks") or {}).get(key) or {}).get("basis") or {}
            groups.setdefault(round(p, 4), []).append(
                (basis.get("event_years"), basis.get("exposure_years"))
            )
        for value, records in groups.items():
            if len(records) >= 5 and len(set(records)) >= 3:
                n = len(records)
                found.append(
                    {
                        "kind": "identical",
                        "ru": f"{key}: у {n} стран с разной историей одинаковая вероятность "
                        f"за год {value:.4f}",
                        "en": f"{key}: {n} countries with different records share the same "
                        f"1-year probability {value:.4f}",
                    }
                )

    # 4. A liberal democracy with a coup risk above the median closed autocracy.
    if regimes:
        by_regime: dict[int, list[tuple[str, float]]] = {}
        for iso3, item in regimes.items():
            p = _p(countries.get(iso3) or {}, REGIME_KEY)
            if p is not None:
                by_regime.setdefault(int(round(float(item["value"]))), []).append((iso3, p))
        autocracies = [p for _, p in by_regime.get(0, [])]
        if autocracies:
            bar = median(autocracies)
            for iso3, p in by_regime.get(3, []):
                if p > bar:
                    found.append(
                        {
                            "kind": "regime_inversion",
                            "iso3": iso3,
                            "ru": f"риск переворота {p:.1%} у либеральной демократии выше "
                            f"медианы закрытых автократий ({bar:.1%})",
                            "en": f"coup risk {p:.1%} for a liberal democracy above the median "
                            f"closed autocracy ({bar:.1%})",
                        }
                    )

    # 5. A 1-year probability doubled (and rose by 5+ points) since the previous run.
    old_countries = {c["iso3"]: c for c in (previous_snapshot or {}).get("countries", [])}
    for iso3, c in countries.items():
        prev = old_countries.get(iso3)
        if not prev:
            continue
        for key in c.get("risks") or {}:
            new, old = _p(c, key), _p(prev, key)
            if new is not None and old is not None and new >= 2 * old and new - old >= 0.05:
                found.append(
                    {
                        "kind": "probability_jump",
                        "iso3": iso3,
                        "ru": f"{key}: {old:.1%} → {new:.1%} за день",
                        "en": f"{key}: {old:.1%} → {new:.1%} in a day",
                    }
                )

    # 6. Sources that failed today.
    for source in snapshot.get("sources", []):
        if source.get("status") == "failed":
            found.append(
                {
                    "kind": "source_failed",
                    "ru": f"источник не загрузился: {source.get('name') or source.get('key')}",
                    "en": f"source failed: {source.get('name') or source.get('key')}",
                }
            )
    return found


def summary(findings: list[dict]) -> dict[str, int]:
    return dict(Counter(f["kind"] for f in findings))
