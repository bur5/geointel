"""Warning signs (indicators & warnings) for every country and risk type.

Each sign has a likelihood ratio (LR): how much more often it is seen before the event than
without it. Active signs multiply the odds of the base-rate probability. The LRs are GeoIntel
judgements fixed in this file (not fitted to any case) and are shown on the site; automated,
noisy signals are capped more tightly than curated "hard" signs such as embassy evacuations.

Sources of signs:
* automated - GDELT event counts, GPS interference, travel-advice changes, elections, IMF,
  military spending, GPR, satellite radar change (when credentials exist);
* journal - curated entries in ``JOURNAL`` (with date and URL) plus entries classified from
  news headlines by a language model (when an API key exists; headline text is untrusted data).
"""

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

SCHEMA = "geointel-signals-v1"

INTERSTATE = "interstate_conflict"
INTERNAL = "internal_armed_conflict"
PROTEST = "mass_protest"
POLITICAL = "political_crisis"
ECONOMIC = "economic_crisis"
HUMANITARIAN = "humanitarian_crisis"
COUP = "coup_attempt"

AUTO_CAP = (1 / 3, 3.0)  # automated signals together
HARD_CAP = (1 / 3, 500.0)  # curated hard signs together
TOTAL_CAP = (1 / 4, 500.0)
COMBO_GROUPS = {"posture", "personnel", "final", "pretext", "cyber", "logistics"}
COMBO_LR = 1.5  # three or more of these groups active at once


@dataclass(frozen=True)
class SignSpec:
    key: str
    group: str
    lr: float
    applies: tuple[str, ...]
    label_ru: str
    label_en: str
    expires_days: int = 120
    automated: bool = False


def _s(key, group, lr, applies, ru, en, days=120, auto=False) -> SignSpec:
    return SignSpec(key, group, lr, tuple(applies), ru, en, days, auto)


WAR = (INTERSTATE, INTERNAL)
SIGNS: tuple[SignSpec, ...] = (
    # Physical preparation for war
    _s(
        "posture",
        "posture",
        1.6,
        WAR,
        "Войска, базы и переброски у границы",
        "Troops, bases and movements near the border",
        365,
    ),
    _s(
        "mobilization",
        "personnel",
        1.4,
        WAR,
        "Мобилизация, набор, законы о резервистах",
        "Mobilisation, recruitment, reservist laws",
        365,
    ),
    _s(
        "personnel",
        "personnel",
        1.8,
        WAR,
        "Отмена отпусков, продление службы, вывоз семей",
        "Leave cancelled, service extended, families moved",
        90,
    ),
    _s(
        "medical",
        "final",
        3.0,
        WAR,
        "Запасы крови, полевые госпитали, режим больниц",
        "Blood supplies, field hospitals, hospitals on alert",
        90,
    ),
    _s(
        "logistics",
        "logistics",
        2.0,
        WAR,
        "Топливо, боеприпасы, понтоны у границы, эшелоны",
        "Fuel, ammunition, bridging kit at the border, troop trains",
        90,
    ),
    _s(
        "masking",
        "final",
        4.0,
        WAR,
        "Снятие или смена опознавательных знаков, радиомолчание",
        "Markings removed or changed, radio silence",
        45,
    ),
    # Justification
    _s(
        "rhetoric",
        "pretext",
        1.3,
        WAR,
        "Нарратив повода: «преследование», «геноцид», угрозы",
        "Pretext narrative: 'persecution', 'genocide', threats",
        180,
    ),
    _s(
        "legal",
        "pretext",
        2.0,
        WAR,
        "Юридическая подготовка: признание, постановления",
        "Legal groundwork: recognition, parliamentary acts",
        120,
    ),
    _s(
        "staged",
        "pretext",
        2.5,
        WAR,
        "Инсценировки и ложные «провокации»",
        "Staged incidents and false 'provocations'",
        60,
    ),
    # Diplomacy, airspace, cyber, economy
    _s(
        "diplomatic",
        "final",
        4.0,
        WAR,
        "Эвакуация посольств, уничтожение документов",
        "Embassy evacuations, documents destroyed",
        60,
    ),
    _s(
        "airspace",
        "final",
        3.0,
        WAR,
        "Закрытие неба, предупреждения пилотам",
        "Airspace closures, notices to pilots",
        30,
    ),
    _s(
        "cyber",
        "cyber",
        1.5,
        WAR,
        "Разрушительные кибератаки на госсистемы",
        "Destructive cyberattacks on government systems",
        60,
    ),
    _s(
        "economic_prep",
        "economy_prep",
        1.3,
        WAR,
        "Запреты экспорта, запасы, подготовка к санкциям",
        "Export bans, stockpiling, sanction-proofing",
        180,
    ),
    _s(
        "war_economy",
        "economy_prep",
        1.15,
        (INTERSTATE,),
        "Перевод экономики на военные рельсы",
        "Economy put on a war footing",
        365,
    ),
    # Assessments and incidents
    _s(
        "intel_warning",
        "intel",
        1.3,
        WAR,
        "Публичное предупреждение разведки или правительства",
        "Public warning by an intelligence service or government",
        365,
    ),
    _s(
        "hybrid",
        "hybrid",
        1.2,
        (INTERSTATE,),
        "Диверсии, кабели, нарушения границ и неба",
        "Sabotage, cable damage, border and airspace violations",
        120,
    ),
    # Factors that lower risk
    _s(
        "deterrence",
        "deterrence",
        0.85,
        (INTERSTATE,),
        "Усиление сдерживания (войска союзников)",
        "Stronger deterrence (allied forces)",
        365,
    ),
    _s(
        "deescalation",
        "deescalation",
        0.8,
        WAR,
        "Переговоры, перемирие, отвод сил",
        "Talks, truce, pull-back of forces",
        90,
    ),
    # Society and politics
    _s(
        "unrest",
        "politics",
        1.5,
        (PROTEST, POLITICAL),
        "Массовые протесты, забастовки",
        "Mass protests and strikes",
        60,
    ),
    _s(
        "repression",
        "politics",
        1.3,
        (POLITICAL, PROTEST, COUP),
        "Репрессии, аресты оппозиции",
        "Repression, opposition arrests",
        120,
    ),
    _s(
        "elite_split",
        "politics",
        1.8,
        (COUP, POLITICAL),
        "Раскол элит, недовольство армии",
        "Elite split, discontent in the army",
        120,
    ),
    # Automated
    _s(
        "gdelt_armed",
        "events",
        1.5,
        (INTERNAL,),
        "Рост сообщений о боях и нападениях",
        "Rise in reported fighting and attacks",
        auto=True,
    ),
    _s(
        "gdelt_protest",
        "events",
        1.6,
        (PROTEST, POLITICAL),
        "Рост сообщений о протестах",
        "Rise in reported protests",
        auto=True,
    ),
    _s(
        "gdelt_repression",
        "events",
        1.3,
        (POLITICAL, PROTEST),
        "Рост сообщений о силовом давлении",
        "Rise in reported coercion and repression",
        auto=True,
    ),
    _s(
        "gdelt_external",
        "events",
        1.4,
        (INTERSTATE,),
        "Рост угроз и силовых действий между странами",
        "Rise in threats and force between states",
        auto=True,
    ),
    _s(
        "gps_jamming",
        "hybrid",
        1.3,
        (INTERSTATE,),
        "Рост глушения GPS над страной",
        "Rise in GPS interference over the country",
        auto=True,
    ),
    _s(
        "advisory_raised",
        "final",
        1.8,
        WAR,
        "Повышен уровень опасности в рекомендациях МИД",
        "Travel advice level raised",
        auto=True,
    ),
    _s(
        "advisory_departure",
        "final",
        3.0,
        WAR,
        "Эвакуация персонала посольства США",
        "US embassy staff ordered or authorised to leave",
        auto=True,
    ),
    _s(
        "election_soon",
        "politics",
        1.3,
        (PROTEST, POLITICAL),
        "Выборы в ближайшие 90 дней",
        "Election within 90 days",
        auto=True,
    ),
    _s(
        "imf_crisis",
        "economy",
        2.0,
        (ECONOMIC,),
        "МВФ прогнозирует спад или инфляцию выше 40%",
        "IMF projects a contraction or inflation above 40%",
        auto=True,
    ),
    _s(
        "high_inflation",
        "economy",
        1.2,
        (PROTEST, ECONOMIC),
        "Инфляция выше 30%",
        "Inflation above 30%",
        auto=True,
    ),
    _s(
        "milex_rise",
        "economy_prep",
        1.15,
        (INTERSTATE,),
        "Военные расходы +1 п. п. ВВП за 5 лет",
        "Military spending up 1+ pp of GDP in 5 years",
        auto=True,
    ),
    _s(
        "gpr_high",
        "intel",
        1.2,
        (INTERSTATE,),
        "Индекс геополитического риска в 1,5 раза выше нормы",
        "Geopolitical risk index 1.5× its normal level",
        auto=True,
    ),
    _s(
        "ongoing_war",
        "intel",
        1.2,
        (INTERSTATE,),
        "Идёт межгосударственная война с участием сторон",
        "An interstate war involving the parties is under way",
        auto=True,
    ),
    _s(
        "satellite_change",
        "posture",
        1.0,
        (INTERSTATE,),
        "Радарный спутник: резкий рост металла на объекте (эксперимент, в расчёт не входит)",
        "Radar satellite: sharp rise in metal at a site (experimental, not counted)",
        auto=True,
    ),
    _s(
        "hazard_alert",
        "hazard",
        1.0,
        (),
        "Идёт стихийное бедствие (оповещение GDACS)",
        "Natural disaster under way (GDACS alert)",
        auto=True,
    ),
)
SPEC = {s.key: s for s in SIGNS}
GROUP_LABELS = {
    "posture": ("Войска и техника", "Forces and equipment"),
    "personnel": ("Люди и мобилизация", "People and mobilisation"),
    "final": ("Последние признаки перед ударом", "Final signs before an attack"),
    "logistics": ("Логистика", "Logistics"),
    "pretext": ("Повод и обоснование", "Pretext and justification"),
    "cyber": ("Кибер", "Cyber"),
    "economy_prep": ("Военная экономика", "War economy"),
    "intel": ("Оценки и напряжённость", "Assessments and tension"),
    "hybrid": ("Гибридные действия", "Hybrid activity"),
    "deterrence": ("Сдерживание", "Deterrence"),
    "deescalation": ("Деэскалация", "De-escalation"),
    "politics": ("Политика и общество", "Politics and society"),
    "events": ("События в новостях (GDELT)", "Events in the news (GDELT)"),
    "economy": ("Экономика", "Economy"),
    "hazard": ("Стихийные бедствия", "Natural hazards"),
}

# Words used by intelligence services mapped to probability ranges (GeoIntel mapping, close to
# the US ICD 203 scale; "low/high risk" phrases are placed by judgement).
ESTIMATIVE = {
    "almost no chance": (0.01, 0.05),
    "highly unlikely": (0.02, 0.1),
    "very unlikely": (0.05, 0.2),
    "low": (0.03, 0.15),
    "unlikely": (0.2, 0.45),
    "roughly even": (0.45, 0.55),
    "likely": (0.55, 0.8),
    "high": (0.5, 0.8),
    "very likely": (0.8, 0.95),
    "almost certain": (0.95, 0.99),
}


@dataclass(frozen=True)
class Entry:
    date: str
    country: str  # country whose risk the sign raises
    sign: str
    summary_ru: str
    summary_en: str
    source: str
    url: str
    actor: str | None = None
    scenario: str | None = None
    strength: float = 1.0
    until: str | None = None


def _e(date_, country, sign, ru, en, source, url, actor=None, scenario=None, strength=1.0):
    return Entry(date_, country, sign, ru, en, source, url, actor, scenario, strength)


# Curated journal: only events with a date and a public source. Extend weekly.
_DDIS = "https://euronews.com/2026/09/24/denmark-says-russian-invasion-of-nato-country-highly-unlikely-but-cannot-be-ruled-out"
JOURNAL: tuple[Entry, ...] = tuple(
    [
        _e(
            "2026-09-24",
            c,
            "intel_warning",
            "Разведка Дании: низкий, но растущий риск ограниченного нападения России на "
            "граничащие с ней страны НАТО.",
            "Danish intelligence: low but growing risk of a limited Russian attack on NATO "
            "countries bordering Russia.",
            "Danish Defence Intelligence Service",
            _DDIS,
            "RUS",
            "russia_nato",
        )
        for c in ("EST", "LVA", "LTU", "POL", "FIN", "NOR")
    ]
    + [
        _e(
            "2026-08-07",
            c,
            "intel_warning",
            "Оценки разведки США: Россия может проверить единство НАТО ограниченным нападением "
            "в ближайшие годы.",
            "US intelligence: Russia could test NATO unity with a limited attack in the next "
            "few years.",
            "US intelligence (reported by CNN)",
            "https://edition.cnn.com/2026/08/07/politics/us-intelligence-russia-putin-nato-attack",
            "RUS",
            "russia_nato",
        )
        for c in ("EST", "LVA", "LTU", "POL")
    ]
    + [
        _e(
            "2026-09-14",
            "DNK",
            "hybrid",
            "Российский фрегат у Гедсера выпустил сигнальные ракеты в сторону датского "
            "военного вертолёта.",
            "A Russian frigate off Gedser fired signal flares at a Danish military helicopter.",
            "Il Foglio (citing Danish authorities)",
            "https://www.ilfoglio.it/en/world/2026/09/26/news/the-timeline-of-a-russian-war-against-nato-according-to-danish-intelligence--408794",
            "RUS",
            "russia_nato",
        ),
        _e(
            "2026-09-24",
            "POL",
            "hybrid",
            "Польша назвала пожар на станции Starlink диверсией.",
            "Poland called a fire at a Starlink station an act of sabotage.",
            "Irish Examiner",
            "https://www.irishexaminer.com/world/arid-41915434.html",
            "RUS",
            "russia_nato",
        ),
        _e(
            "2026-09-24",
            "DNK",
            "hybrid",
            "Служба безопасности Дании: Россия готовит диверсии против оборонных компаний.",
            "Danish security service: Russia is preparing sabotage against defence companies.",
            "Il Foglio (citing Danish authorities)",
            "https://www.ilfoglio.it/en/world/2026/09/26/news/the-timeline-of-a-russian-war-against-nato-according-to-danish-intelligence--408794",
            "RUS",
            "russia_nato",
        ),
        _e(
            "2026-11-13",
            "TWN",
            "posture",
            "Необъявленные учения Китая в западной части Тихого океана в начале ноября, по "
            "словам тайваньского чиновника — крупнее «Миссии справедливости 2025».",
            "Unannounced Chinese drills in the western Pacific in early November, larger than "
            "'Justice Mission 2025' according to a Taiwanese official.",
            "Reuters (via Honolulu Star-Advertiser)",
            "https://www.staradvertiser.com/2026/11/13/breaking-news/china-stages-unannounced-pacific-drills-in-intimidation-of-taiwan/",
            "CHN",
            "china_taiwan",
        ),
        _e(
            "2026-11-11",
            "UKR",
            "deescalation",
            "Переговоры в Абу-Даби: договорились об обмене пленными, без прорыва по "
            "прекращению огня.",
            "Abu Dhabi talks: prisoner exchange agreed, no ceasefire breakthrough.",
            "Jamestown Foundation",
            "https://jamestown.org/russia-ukraine-u-s-talks-in-abu-dhabi-yield-little-progress/",
            "RUS",
            "ukraine_ceasefire",
            0.5,
        ),
    ]
)


# --------------------------------------------------------------------------------------
# Combining signs


def _as_date(value: str) -> date:
    return date.fromisoformat(value if len(value) > 7 else f"{value}-01")


def active_entries(entries: Iterable[Entry], today: date) -> list[Entry]:
    result = []
    for entry in entries:
        spec = SPEC.get(entry.sign)
        if spec is None:
            continue
        start = _as_date(entry.date)
        end = _as_date(entry.until) if entry.until else start + timedelta(days=spec.expires_days)
        if start <= today <= end:
            result.append(entry)
    return result


def combine(
    signs: Iterable[dict], risk: str, auto_power: float = 1.0, auto_cap: float | None = None
) -> dict:
    """Odds factor for one risk type from active signs (strongest entry per sign counts once).

    ``auto_power`` < 1 damps automated signals when they are pooled over many countries.
    """
    best: dict[str, dict] = {}
    for sign in signs:
        spec = SPEC.get(sign["key"])
        if spec is None or risk not in spec.applies or sign.get("status") != "active":
            continue
        lr = sign.get("lr", spec.lr) ** sign.get("strength", 1.0)
        if spec.automated:
            lr **= auto_power
        if sign["key"] not in best or abs(math.log(lr)) > abs(math.log(best[sign["key"]]["lr"])):
            best[sign["key"]] = {"lr": lr, "auto": spec.automated, "group": spec.group}
    auto = math.prod(v["lr"] for v in best.values() if v["auto"])
    hard = math.prod(v["lr"] for v in best.values() if not v["auto"])
    auto = min(max(auto, AUTO_CAP[0]), auto_cap or AUTO_CAP[1])
    groups = {v["group"] for v in best.values() if v["lr"] > 1} & COMBO_GROUPS
    combo = COMBO_LR if len(groups) >= 3 else 1.0
    hard = min(max(hard * combo, HARD_CAP[0]), HARD_CAP[1])
    factor = min(max(auto * hard, TOTAL_CAP[0]), TOTAL_CAP[1])
    return {
        "factor": round(factor, 3),
        "signs": sorted(best),
        "groups": sorted(groups),
        "combo": combo > 1,
    }


def adjust(p: float, factor: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    odds = p / (1 - p) * factor
    return odds / (1 + odds)


HORIZON_DAMPING = {"1m": 1.0, "1y": 1.0, "5y": 0.5, "10y": 0.33}


def adjusted_horizons(horizons: Mapping[str, Mapping], factor: float) -> dict:
    result = {}
    for h, v in horizons.items():
        f = factor ** HORIZON_DAMPING.get(h, 1.0)
        result[h] = {k: round(adjust(v[k], f), 4) for k in ("p", "low", "high")}
    return result


# --------------------------------------------------------------------------------------
# Automated signs from data already in the snapshot


def _sign(key: str, status: str, value_ru: str, value_en: str, **extra) -> dict:
    spec = SPEC[key]
    return {
        "key": key,
        "group": spec.group,
        "status": status,
        "lr": spec.lr,
        "value_ru": value_ru,
        "value_en": value_en,
        **extra,
    }


def _zscore_signs(iso3: str, z: Mapping[str, float | None]) -> list[dict]:
    names = {
        "armed": "gdelt_armed",
        "protest": "gdelt_protest",
        "repression": "gdelt_repression",
        "external": "gdelt_external",
    }
    signs = []
    for category, key in names.items():
        value = z.get(category)
        if value is None:
            signs.append(_sign(key, "no_data", "мало данных", "not enough data"))
            continue
        status = "active" if value >= 2.5 else "normal"
        strength = 1.5 if value >= 3.5 else 1.0
        signs.append(
            _sign(
                key,
                status,
                f"z = {value:+.1f} (7 дней к базе)",
                f"z = {value:+.1f} (7 days vs baseline)",
                strength=strength,
                source="GDELT",
            )
        )
    return signs


def automated_signs(
    iso3: str,
    country: Mapping,
    *,
    today: date,
    gdelt_z: Mapping[str, float | None] | None,
    gps: Mapping | None,
    advisory_history: Mapping[str, list] | None,
    milex: Mapping | None,
    hazard_alerts: list[dict],
    satellite: list[dict],
) -> list[dict]:
    signs: list[dict] = []
    if gdelt_z is not None:
        signs.extend(_zscore_signs(iso3, gdelt_z))
    if gps is not None:
        ratio, share = gps.get("ratio"), gps.get("share")
        if share is None:
            signs.append(_sign("gps_jamming", "no_data", "нет полётов", "no flights"))
        else:
            active = ratio is not None and ratio >= 1.5 and share >= 0.02
            signs.append(
                _sign(
                    "gps_jamming",
                    "active" if active else "normal",
                    f"{share * 100:.1f}% самолётов с плохой навигацией"
                    + (f", ×{ratio:.1f} к норме" if ratio else ""),
                    f"{share * 100:.1f}% of aircraft with poor navigation"
                    + (f", ×{ratio:.1f} vs normal" if ratio else ""),
                    source="GPSJam (ADS-B)",
                    chronic=share >= 0.05,
                )
            )
    history = (advisory_history or {}).get(iso3) or []
    if history:

        def level(h: list) -> int:
            return max(h[1] or 0, h[2] or 0)

        age = [(today - date.fromisoformat(h[0])).days for h in history]
        recent = [h for h, a in zip(history, age, strict=True) if a <= 30]
        older = [h for h, a in zip(history, age, strict=True) if 30 < a <= 120]
        raised = bool(recent and older) and max(map(level, recent)) > max(map(level, older))
        # Only a new departure order counts: some embassies have been on reduced staff for
        # years (e.g. Minsk), which says nothing about a coming change.
        departure = bool(older) and any(h[3] for h in recent) and not any(h[3] for h in older)
        signs.append(
            _sign(
                "advisory_raised",
                "active" if raised else "normal",
                "уровень повышен за 30 дней" if raised else "без изменений",
                "raised within 30 days" if raised else "unchanged",
                source="US State Dept, UK FCDO",
            )
        )
        signs.append(
            _sign(
                "advisory_departure",
                "active" if departure else "normal",
                "эвакуация персонала" if departure else "нет",
                "staff departure" if departure else "none",
                source="US State Dept",
            )
        )
    for election in country.get("elections") or []:
        days = (date.fromisoformat(election["date"][:10]) - today).days
        if 0 <= days <= 90 and election.get("precision") == "day":
            signs.append(
                _sign(
                    "election_soon",
                    "active",
                    f"{election['date'][:10]}: {election.get('name_ru') or election['name_en']}",
                    f"{election['date'][:10]}: {election['name_en']}",
                    source="Wikidata",
                )
            )
            break
    outlook = country.get("outlook") or {}
    if outlook:
        crisis = outlook.get("projects_crisis") or []
        signs.append(
            _sign(
                "imf_crisis",
                "active" if crisis else "normal",
                ", ".join(crisis) or "нет",
                ", ".join(crisis) or "none",
                source="IMF WEO",
            )
        )
        inflation = (outlook.get("inflation") or {}).get(str(today.year))
        if inflation is not None:
            signs.append(
                _sign(
                    "high_inflation",
                    "active" if inflation > 30 else "normal",
                    f"{inflation:.1f}% в {today.year}",
                    f"{inflation:.1f}% in {today.year}",
                    source="IMF WEO",
                )
            )
    if milex and milex.get("change5") is not None:
        signs.append(
            _sign(
                "milex_rise",
                "active" if milex["change5"] >= 1 else "normal",
                f"{milex['value']:.1f}% ВВП, {milex['change5']:+.1f} за 5 лет",
                f"{milex['value']:.1f}% of GDP, {milex['change5']:+.1f} in 5 years",
                source="SIPRI",
            )
        )
    gpr = country.get("gpr") or {}
    if gpr.get("ratio_12m"):
        signs.append(
            _sign(
                "gpr_high",
                "active" if gpr["ratio_12m"] >= 1.5 else "normal",
                f"×{gpr['ratio_12m']:.2f} к среднему за 5 лет",
                f"×{gpr['ratio_12m']:.2f} vs 5-year mean",
                source="Caldara & Iacoviello",
            )
        )
    for alert in hazard_alerts:
        signs.append(
            _sign(
                "hazard_alert",
                "active",
                f"{alert['name'] or alert['hazard']} ({alert['alert']}, {alert['date']})",
                f"{alert['name'] or alert['hazard']} ({alert['alert']}, {alert['date']})",
                source="GDACS",
                hazard=alert["hazard"],
            )
        )
    for site in satellite:
        signs.append(
            _sign(
                "satellite_change",
                "active" if site["active"] else "normal",
                f"{site['name_ru']}: ×{site['ratio']:.2f}",
                f"{site['name_en']}: ×{site['ratio']:.2f}",
                source="Sentinel-1 (Copernicus)",
            )
        )
    return signs


def journal_signs(entries: Iterable[Entry | dict], iso3: str, today: date) -> list[dict]:
    """Active journal entries for a country as signs (news-classified entries are weaker
    until two independent outlets report the same sign)."""
    curated = [e for e in entries if isinstance(e, Entry) and e.country == iso3]
    signs = [
        _sign(
            e.sign,
            "active",
            e.summary_ru,
            e.summary_en,
            source=e.source,
            url=e.url,
            date=e.date,
            strength=e.strength,
            actor=e.actor,
            curated=True,
        )
        for e in active_entries(curated, today)
    ]
    auto = [e for e in entries if isinstance(e, dict) and e.get("country") == iso3]
    by_sign: dict[str, list[dict]] = defaultdict(list)
    for e in auto:
        spec = SPEC.get(e.get("sign", ""))
        if spec and 0 <= (today - date.fromisoformat(e["date"])).days <= min(spec.expires_days, 30):
            by_sign[e["sign"]].append(e)
    for key, items in by_sign.items():
        domains = {i.get("domain") for i in items}
        latest = max(items, key=lambda i: i["date"])
        signs.append(
            _sign(
                key,
                "active",
                latest["summary_ru"],
                latest["summary_en"],
                source=f"news: {', '.join(sorted(d for d in domains if d))[:80]}",
                url=latest.get("url"),
                date=latest["date"],
                strength=1.0 if len(domains) >= 2 else 0.5,
                curated=False,
                reports=len(items),
            )
        )
    return signs


RISKS = (INTERSTATE, INTERNAL, PROTEST, POLITICAL, ECONOMIC, HUMANITARIAN, COUP)


def build_signals(
    snapshot: Mapping,
    *,
    today: date | None = None,
    gdelt_z: Mapping[str, Mapping[str, float | None]] | None = None,
    gps: Mapping[str, Mapping] | None = None,
    advisory_history: Mapping[str, list] | None = None,
    milex: Mapping[str, Mapping] | None = None,
    hazard_alerts: Mapping[str, list[dict]] | None = None,
    satellite: Mapping[str, list[dict]] | None = None,
    news_entries: Iterable[dict] = (),
    status: Mapping[str, str] | None = None,
    generated_at: datetime | None = None,
) -> dict:
    now = generated_at or datetime.now(UTC)
    today = today or now.date()
    entries: list = [*JOURNAL, *news_entries]
    countries: dict[str, dict] = {}
    for country in snapshot.get("countries", []):
        iso3 = country["iso3"]
        signs = automated_signs(
            iso3,
            country,
            today=today,
            gdelt_z=(gdelt_z or {}).get(iso3) if gdelt_z is not None else None,
            gps=(gps or {}).get(iso3) if gps is not None else None,
            advisory_history=advisory_history,
            milex=(milex or {}).get(iso3),
            hazard_alerts=(hazard_alerts or {}).get(iso3, []),
            satellite=(satellite or {}).get(iso3, []),
        ) + journal_signs(entries, iso3, today)
        adjusted = {}
        for risk in RISKS:
            base = (country.get("risks") or {}).get(risk)
            combined = combine(signs, risk)
            if not combined["signs"]:
                continue
            item = {**combined}
            if base and base.get("question") == "onset_within":
                item["horizons"] = adjusted_horizons(base["horizons"], combined["factor"])
            adjusted[risk] = item
        active = [s for s in signs if s["status"] == "active" and s["key"] != "hazard_alert"]
        countries[iso3] = {
            "signs": signs,
            "adjusted": adjusted,
            "active": len(active),
            "max_factor": max((a["factor"] for a in adjusted.values()), default=1.0),
        }
    return {
        "schema": SCHEMA,
        "generated_at": now.isoformat(),
        "catalogue": [
            {
                "key": s.key,
                "group": s.group,
                "lr": s.lr,
                "applies": list(s.applies),
                "label_ru": s.label_ru,
                "label_en": s.label_en,
                "automated": s.automated,
                "expires_days": s.expires_days,
            }
            for s in SIGNS
        ],
        "groups": {k: {"ru": v[0], "en": v[1]} for k, v in GROUP_LABELS.items()},
        "caps": {"auto": AUTO_CAP, "hard": HARD_CAP, "total": TOTAL_CAP, "combo": COMBO_LR},
        "status": dict(status or {}),
        "countries": countries,
    }
