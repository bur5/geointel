"""Who else a scenario draws in, and whose economy it hits — first and second ring.

For every scenario GeoIntel lists, beyond the parties themselves:

* **involvement** — how likely a country is to take part militarily if the scenario happens,
  from defence treaties with a party, foreign bases of a party on its soil (which make it a
  target), and the curated front-line / ally roles of the scenario. A GeoIntel rule of thumb,
  not a forecast of each government's decision;
* **economic exposure, first ring** — trade with the parties (Comtrade shares of exports and
  imports) and the scenario's curated economic links (energy routes, refugees, remittances);
* **economic exposure, second ring** — countries that trade heavily with a strongly exposed
  country are exposed too, at half weight ("A is hit, and C sells 30% of its exports to A").

Each country carries a short chain of reasons so the user can see why it is on the list.
"""

from collections.abc import Iterable, Mapping

from geointel.risk.scenario_types import NATO, Scenario

# Mutual defence commitments (only stable, well-known ones).
TREATIES: dict[str, tuple[str, ...]] = {
    "NATO": tuple(NATO),
    "CSTO": ("RUS", "BLR", "KAZ", "KGZ", "TJK"),  # Armenia froze its participation in 2024
    "US-JPN": ("USA", "JPN"),
    "US-KOR": ("USA", "KOR"),
    "US-PHL": ("USA", "PHL"),
    "US-AUS": ("USA", "AUS"),
    "RUS-PRK": ("RUS", "PRK"),
    "CHN-PRK": ("CHN", "PRK"),
    "TUR-AZE": ("TUR", "AZE"),
    "SAU-PAK": ("SAU", "PAK"),
}
TREATY_NAMES = {
    "NATO": ("НАТО (статья 5)", "NATO (Article 5)"),
    "CSTO": ("ОДКБ", "CSTO"),
    "US-JPN": ("договор США–Япония", "US–Japan treaty"),
    "US-KOR": ("договор США–Южная Корея", "US–South Korea treaty"),
    "US-PHL": ("договор США–Филиппины", "US–Philippines treaty"),
    "US-AUS": ("договор АНЗЮС", "ANZUS treaty"),
    "RUS-PRK": ("договор России и КНДР 2024 года", "2024 Russia–North Korea treaty"),
    "CHN-PRK": ("договор Китая и КНДР", "China–North Korea treaty"),
    "TUR-AZE": ("Шушинская декларация Турции и Азербайджана", "Turkey–Azerbaijan Shusha accord"),
    "SAU-PAK": ("оборонный пакт Саудовской Аравии и Пакистана", "Saudi–Pakistan defence pact"),
}
# Countries hosting significant forces of a power, by region: they become targets when that
# power fights an opponent able to reach them.
BASES: dict[str, dict[str, tuple[str, ...]]] = {
    "USA": {
        "me": tuple("BHR QAT KWT ARE SAU IRQ JOR DJI TUR".split()),
        "eu": tuple("DEU ITA GBR ESP POL ROU LTU TUR".split()),
        "asia": ("JPN", "KOR"),
    },
    "RUS": {"eu": ("BLR", "ARM", "TJK", "KGZ", "MDA")},
}
OPPONENT_REGION = {
    "IRN": "me",
    "IRQ": "me",
    "YEM": "me",
    "RUS": "eu",
    "BLR": "eu",
    "USA": "eu",
    "CHN": "asia",
    "PRK": "asia",
}
ROLE_WEIGHT = {"frontline": 0.2, "ally": 0.15}
TREATY_WEIGHT = 0.5
FRONT_TREATY_WEIGHT = 0.35  # allied to a likely victim (e.g. NATO's Article 5)
BASE_WEIGHT = 0.3
# Powers whose own economy is not disrupted by fighting far from home: trade with them is not
# counted as exposure (a US strike on Iran does not hit Mexico through US trade).
FIGHTS_ABROAD = {"USA"}
ECON_ROLE = {"economic": 0.3, "frontline": 0.2, "ally": 0.1}
SECOND_RING = 0.5


def _combine(weights: Iterable[float]) -> float:
    p = 1.0
    for w in weights:
        p *= 1 - w
    return 1 - p


def _shares(trade: Mapping | None, key: str) -> dict[str, float]:
    return {s["iso3"]: s["share"] for s in (trade or {}).get(key, [])}


def parties(scenario: Scenario) -> set[str]:
    found = {c for e in scenario.exposures if e.role == "party" for c in e.countries}
    return found or set(scenario.side_a) | set(scenario.side_b)


def roles(scenario: Scenario) -> dict[str, tuple[str, str, str]]:
    out: dict[str, tuple[str, str, str]] = {}
    for e in scenario.exposures:
        for code in e.countries:
            out.setdefault(code, (e.role, e.reason_ru, e.reason_en))
    return out


def scenario_network(
    scenario: Scenario, countries: Mapping[str, Mapping], limit: int = 30
) -> list[dict]:
    sides = parties(scenario)
    role_of = roles(scenario)
    front = {c for c, r in role_of.items() if r[0] == "frontline"}
    defenders = (set(scenario.side_b) - {"USA"}) - (set(scenario.side_a) - set(scenario.side_b))
    result: dict[str, dict] = {}

    def entry(code: str) -> dict:
        return result.setdefault(
            code, {"iso3": code, "involve": 0.0, "econ": 0.0, "ring": 1, "ru": [], "en": []}
        )

    universe = set(countries) | set(role_of)
    for code in universe - sides:
        weights, ru, en = [], [], []
        # Mutual defence obliges allies to defend a member that is attacked, not to join a
        # member's war abroad, so treaties count for the defending side only. US treaties
        # protect allies' territory and do not oblige allies to join US operations.
        for name, members in TREATIES.items():
            if code not in members:
                continue
            if (defenders - {code}) & set(members):
                weights.append(TREATY_WEIGHT)
                ru.append(f"{TREATY_NAMES[name][0]} с атакуемой стороной")
                en.append(f"{TREATY_NAMES[name][1]} with the side under attack")
            elif (front - {code}) & set(members):
                weights.append(FRONT_TREATY_WEIGHT)
                ru.append(f"{TREATY_NAMES[name][0]} со страной на передовой")
                en.append(f"{TREATY_NAMES[name][1]} with a front-line country")
        for power, regions in BASES.items():
            if power not in sides:
                continue
            for other in sides - {power}:
                hosts = regions.get(OPPONENT_REGION.get(other, ""), ())
                if code in hosts:
                    weights.append(BASE_WEIGHT)
                    ru.append(
                        f"на территории базы {power} — возможная цель ответного удара {other}"
                    )
                    en.append(f"hosts {power} bases — a possible target for {other}")
                    break
        role = role_of.get(code)
        if role and role[0] in ROLE_WEIGHT:
            weights.append(ROLE_WEIGHT[role[0]])
            ru.append(role[1])
            en.append(role[2])
        econ, econ_ru, econ_en = 0.0, [], []
        trade = (countries.get(code) or {}).get("trade")
        exports, imports = _shares(trade, "exports_to"), _shares(trade, "imports_from")
        for side in sorted(sides - FIGHTS_ABROAD):
            share = max(exports.get(side, 0.0), imports.get(side, 0.0))
            if share >= 0.03:
                econ += share
                econ_ru.append(f"{share * 100:.0f}% торговли — со стороной конфликта {side}")
                econ_en.append(f"{share * 100:.0f}% of trade is with party {side}")
        if role and role[0] in ECON_ROLE:
            econ += ECON_ROLE[role[0]]
            if role[0] == "economic":
                econ_ru.append(role[1])
                econ_en.append(role[2])
        if not weights and econ <= 0:
            continue
        item = entry(code)
        item["involve"] = round(_combine(weights), 3)
        item["econ"] = round(min(econ, 1.0), 3)
        item["ru"] += ru + econ_ru
        item["en"] += en + econ_en

    # Second ring: heavy trade with a strongly hit country (parties count as fully hit).
    hit = {code: 1.0 for code in sides - FIGHTS_ABROAD}
    hit.update({c: v["econ"] for c, v in result.items() if v["econ"] >= 0.2})
    for code, data in countries.items():
        if code in sides:
            continue
        exports = _shares(data.get("trade"), "exports_to")
        best, via = 0.0, None
        for partner, weight in hit.items():
            if partner in sides or partner == code:
                continue
            value = SECOND_RING * weight * exports.get(partner, 0.0)
            if value > best:
                best, via = value, partner
        if via and best >= 0.03 and best > result.get(code, {}).get("econ", 0.0):
            item = entry(code)
            if item["econ"] == 0.0 and item["involve"] == 0.0:
                item["ring"] = 2
            item["econ"] = round(best, 3)
            share = exports[via] * 100
            item["ru"].append(
                f"{share:.0f}% экспорта идёт в {via}, которую сценарий сильно задевает"
            )
            item["en"].append(f"{share:.0f}% of exports go to {via}, which the scenario hits hard")
    ranked = sorted(result.values(), key=lambda v: -max(v["involve"], v["econ"]))
    out = []
    for v in ranked[:limit]:
        out.append(
            {
                "iso3": v["iso3"],
                "involve": v["involve"],
                "econ": v["econ"],
                "ring": v["ring"],
                "why_ru": v["ru"][:4],
                "why_en": v["en"][:4],
            }
        )
    return out


def apply_network(scenarios: dict, catalogue: Iterable[Scenario], links: Mapping | None) -> None:
    countries = (links or {}).get("countries", {})
    by_key = {s.key: s for s in catalogue}
    for item in scenarios.get("scenarios", []):
        scenario = by_key.get(item["key"])
        if scenario is not None:
            item["network"] = scenario_network(scenario, countries)
