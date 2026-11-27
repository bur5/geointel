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
SIGN_CAP = 10.0  # no single sign (curated entry included) moves the odds more than ×10
# The total factor is capped by the stage of preparation the signs show (model 1.4.0):
# without signs of the last stages the odds cannot rise more than ×5 (stage 0–1), ×20 with
# personnel or logistics signs (stage 2), ×100 with final signs (stage 3). ×100 stays below
# what open forecasters implied in mid-February 2022 (×200–450): the rest must come from
# markets and official assessments, not from our signs alone.
STAGE_CAPS = {0: 5.0, 1: 5.0, 2: 20.0, 3: 100.0}
TOTAL_FLOOR = 1 / 4
HARD_CAP = (1 / 3, STAGE_CAPS[3])  # kept for the published "caps" block
TOTAL_CAP = (TOTAL_FLOOR, STAGE_CAPS[3])
COMBO_GROUPS = {"posture", "personnel", "final", "pretext", "cyber", "logistics"}
COMBO_LR = 1.0  # removed in 1.4.0: multiplying signs already rewards several groups


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
        1.0,  # observation only until a with/without test shows value (1.4.0)
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
    *(
        _s(
            key,
            "politics",
            1.0,  # part of the political crisis definition: shown, not a multiplier (1.7.0)
            (POLITICAL, PROTEST),
            ru,
            en,
            60,
        )
        for key, ru, en in (
            (
                "leader_exit",
                "Глава государства или правительства ушёл досрочно",
                "Head of state or government left office early",
            ),
            ("snap_election", "Назначены досрочные выборы", "Early national election called"),
            (
                "impeachment",
                "Импичмент одобрен хотя бы одной палатой",
                "Impeachment passed at least one chamber",
            ),
            (
                "emergency_rule",
                "Чрезвычайное или военное положение по политическим причинам",
                "State of emergency or martial law for political reasons",
            ),
        )
    ),
    _s(
        "war_risk_listed",
        "final",
        1.0,  # observation only until a with/without test shows value (1.9.3)
        WAR,
        "Морские страховщики внесли страну в зоны военного риска (JWC)",
        "Marine insurers list the country as a war-risk area (JWC)",
        auto=True,
    ),
    _s(
        "airspace_warning",
        "final",
        1.0,  # observation only until a with/without test shows value (1.7.0)
        WAR,
        "EASA: бюллетень о зоне конфликта для воздушного пространства",
        "EASA conflict zone bulletin for the airspace",
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
        1.0,  # observation only until a with/without test shows value (1.4.0)
        (INTERSTATE,),
        "Радарный спутник: резкий рост металла на объекте (с учётом сезона, эксперимент)",
        "Radar satellite: sharp rise in metal at a site (season-adjusted, experimental)",
        auto=True,
    ),
    _s(
        "internet_outage",
        "politics",
        1.4,
        (COUP, POLITICAL, PROTEST, INTERNAL),
        "Крупное отключение интернета в стране",
        "Major internet outage in the country",
        auto=True,
    ),
    _s(
        "fires_anomaly",
        "events",
        1.2,
        (INTERNAL, INTERSTATE),
        "Резкий рост пожаров со спутника в зоне конфликта",
        "Sharp rise in satellite-detected fires in a conflict country",
        auto=True,
    ),
    _s(
        "military_air",
        "posture",
        1.0,  # observation only until a with/without test shows value (1.4.0)
        (INTERSTATE,),
        "Больше военных самолётов в соседнем воздушном пространстве",
        "More military aircraft in nearby airspace",
        auto=True,
    ),
    _s(
        "media_mobilization",
        "personnel",
        1.3,
        WAR,
        "Русскоязычные СМИ: всплеск темы мобилизации и сборов",
        "Russian-language media: surge in mobilisation and call-up coverage",
        auto=True,
    ),
    _s(
        "media_martial_law",
        "pretext",
        1.4,
        WAR,
        "Русскоязычные СМИ: всплеск темы военного положения",
        "Russian-language media: surge in martial-law coverage",
        auto=True,
    ),
    # Keyword counts in public Telegram channels (sources/keywords.py): weak, automated, in
    # their own group so they never trigger the combination bonus of real preparation signs.
    _s(
        "kw_military",
        "media",
        1.2,
        WAR,
        "Telegram: всплеск сообщений о войсках, мобилизации, госпиталях",
        "Telegram: surge in posts on troops, mobilisation, field hospitals",
        auto=True,
    ),
    _s(
        "kw_emergency",
        "media",
        1.25,
        WAR,
        "Telegram: всплеск сообщений об эвакуации, военном положении, закрытии границ",
        "Telegram: surge in posts on evacuations, martial law, border closures",
        auto=True,
    ),
    _s(
        "kw_coup",
        "media",
        1.3,
        (COUP, POLITICAL),
        "Telegram: всплеск сообщений о перевороте или мятеже",
        "Telegram: surge in posts on a coup or mutiny",
        auto=True,
    ),
    _s(
        "kw_unrest",
        "media",
        1.25,
        (PROTEST, POLITICAL),
        "Telegram: всплеск сообщений о протестах и забастовках",
        "Telegram: surge in posts on protests and strikes",
        auto=True,
    ),
    _s(
        "kw_hybrid",
        "media",
        1.1,
        (INTERSTATE,),
        "Telegram: всплеск сообщений о диверсиях, кибератаках, нарушениях границ",
        "Telegram: surge in posts on sabotage, cyberattacks, border violations",
        auto=True,
    ),
    _s(
        "currency_crash",
        "economy",
        1.6,
        (ECONOMIC, PROTEST, POLITICAL),
        "Национальная валюта подешевела на 15%+ за месяц",
        "National currency lost 15%+ in a month",
        auto=True,
    ),
    _s(
        "food_price_spike",
        "economy",
        1.4,
        (PROTEST, POLITICAL, HUMANITARIAN),
        "Резкий рост цен на продовольствие (ВПП ООН)",
        "Sharp rise in food prices (WFP)",
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
    "media": ("Сообщения в Telegram (ключевые слова)", "Telegram posts (keywords)"),
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
    + [
        _e(
            "2025-12",
            c,
            "posture",
            "В Беларуси размещён российский ракетный комплекс «Орешник» (подтверждено в Кремле).",
            "Russia's Oreshnik missile system is deployed in Belarus (confirmed by the Kremlin).",
            "Atlantic Council",
            "https://www.atlanticcouncil.org/blogs/ukrainealert/belarus-hosts-nuclear-capable-russian-missiles-despite-talk-of-us-thaw/",
            "RUS",
            "belarus_front",
            0.3,  # a standing deployment, not a build-up
        )
        for c in ("POL", "LTU", "LVA")
    ]
    + [
        _e(
            "2026-03-13",
            c,
            "rhetoric",
            "Лукашенко пригрозил применить «Орешник», если Украина, Польша, Литва или Латвия "
            "будут «вмешиваться».",
            "Lukashenko threatened to use the Oreshnik if Ukraine, Poland, Lithuania or Latvia "
            "'interfere'.",
            "Kyiv Post (citing BelTA)",
            "https://www.kyivpost.com/amp/post/71898",
            "BLR",
            "belarus_front",
        )
        for c in ("POL", "LTU", "LVA")
    ]
    + [
        _e(
            "2025-09-10",
            "POL",
            "hybrid",
            "Около 19 нарушений воздушного пространства Польши российскими дронами во время "
            "удара по Украине; несколько сбиты, Польша запросила консультации по статье 4 НАТО.",
            "About 19 violations of Polish airspace by Russian drones during a strike on "
            "Ukraine; several shot down, Poland requested NATO Article 4 consultations.",
            "NPR",
            "https://www.npr.org/2025/09/10/nx-s1-5537110/nato-shoots-down-russian-drones-over-poland",
            "RUS",
            "russia_nato",
        ),
        _e(
            "2025-09-19",
            "EST",
            "hybrid",
            "Три российских МиГ-31 12 минут находились в воздушном пространстве Эстонии у "
            "острова Вайндлоо; Эстония запросила консультации по статье 4.",
            "Three Russian MiG-31s spent 12 minutes in Estonian airspace near Vaindloo Island; "
            "Estonia requested Article 4 consultations.",
            "ERR News",
            "https://news.err.ee/1609806488/estonia-requests-nato-article-4-discussions-following-russian-airspace-violations",
            "RUS",
            "russia_nato",
        ),
        _e(
            "2025-10-27",
            "LTU",
            "hybrid",
            "После серии запусков воздушных шаров с контрабандой из Беларуси, закрывавших "
            "аэропорт Вильнюса, Литва закрыла границу с Беларусью, назвав это гибридной атакой.",
            "After repeated contraband balloons from Belarus shut Vilnius airport, Lithuania "
            "closed its border with Belarus, calling it a hybrid attack.",
            "LRT",
            "https://www.lrt.lt/en/news-in-english/19/2727131/lithuania-to-close-border-with-belarus-over-smuggling-balloon-threat-with-some-exemptions",
            "BLR",
            "belarus_front",
        ),
        _e(
            "2025-12-17",
            "EST",
            "hybrid",
            "Трое российских пограничников на судне на воздушной подушке пересекли линию "
            "контроля на реке Нарве у Васкнарвы; Эстония вызвала временного поверенного России.",
            "Three Russian border guards on a hovercraft crossed the control line on the Narva "
            "River at Vasknarva; Estonia summoned Russia's chargé d'affaires.",
            "Euronews",
            "https://www.euronews.com/2025/12/18/russian-border-guards-briefly-cross-into-estonian-territory-foreign-ministry-says",
            "RUS",
            "russia_nato",
        ),
        _e(
            "2025-12-31",
            "FIN",
            "hybrid",
            "Повреждён кабель Хельсинки–Таллин; Финляндия задержала судно Fitburg, шедшее из "
            "России. Причастность государства не доказана.",
            "The Helsinki–Tallinn cable was damaged; Finland seized the Fitburg, sailing from "
            "Russia. State involvement is not proven.",
            "Polskie Radio",
            "https://www.polskieradio.pl/395/7785/artykul/3628595,finland-seizes-cargo-ship-over-damage-to-undersea-cable-linking-helsinki-and-tallinn",
            None,
            "russia_nato",
            0.5,
        ),
        _e(
            "2026-11-15",
            "EST",
            "hybrid",
            "Эстония сообщила о предотвращённом поджоге завода дронов Threod по заказу ГРУ и "
            "закрывает все автомобильные пункты пропуска на границе с Россией с 1 декабря.",
            "Estonia said it foiled a GRU-ordered arson attack on the drone maker Threod and is "
            "closing all road crossings with Russia from 1 December.",
            "Euronews",
            "https://www.euronews.com/2026/11/16/estonia-to-close-russia-border-after-sabotage-bid-on-drone-maker-foreign-minister-says",
            "RUS",
            "russia_nato",
        ),
        _e(
            "2026-03-06",
            "LTU",
            "intel_warning",
            "Разведки Литвы: бригады России у границ НАТО разворачиваются в дивизии; при "
            "снятии санкций Россия может быть готова к широкому конфликту с НАТО через ~6 лет.",
            "Lithuanian intelligence: Russian brigades near NATO borders are being expanded into "
            "divisions; with sanctions lifted Russia could be ready for a wide conflict with NATO "
            "in about 6 years.",
            "State Security Department of Lithuania",
            "https://www.vsd.lt/en/reports/introduction/",
            "RUS",
            "russia_nato",
            0.5,
        ),
        _e(
            "2026-01-26",
            "LVA",
            "intel_warning",
            "Бюро защиты Сатверсме Латвии: прямой военной угрозы сейчас нет, но признаки "
            "указывают на долгосрочные планы России.",
            "Latvia's SAB: no direct military threat now, but signs point to long-term Russian "
            "plans.",
            "Constitution Protection Bureau of Latvia",
            "https://www.sab.gov.lv/files/uploads/2026/01/SABs-annual-report_2025_ENG.pdf",
            "RUS",
            "russia_nato",
            0.5,
        ),
        _e(
            "2026-02-17",
            "SWE",
            "intel_warning",
            "Военная разведка Швеции: Россия — главная военная угроза Швеции и НАТО, готова "
            "больше рисковать вблизи Швеции.",
            "Swedish military intelligence: Russia is the main military threat to Sweden and "
            "NATO and is willing to take greater risks near Sweden.",
            "MUST (reported by Ukrainska Pravda)",
            "https://www.pravda.com.ua/eng/news/2026/02/18/8021541",
            "RUS",
            "russia_nato",
            0.5,
        ),
        _e(
            "2026-10-05",
            "DEU",
            "intel_warning",
            "Глава BND: Германия под угрозой втягивания в силовой конфликт с Россией; возможны "
            "военные действия низкой интенсивности в Прибалтике.",
            "BND chief: Germany risks being drawn into a violent conflict with Russia; "
            "low-intensity military activity in the Baltic states is possible.",
            "CP24 (Reuters)",
            "https://www.cp24.com/news/world/2026/10/05/germany-at-risk-of-violent-conflict-with-russia-intelligence-chief-says/",
            "RUS",
            "russia_nato",
            0.5,
        ),
        _e(
            "2026-05-15",
            "MDA",
            "legal",
            "Указ Путина об упрощённом российском гражданстве для жителей Приднестровья.",
            "Putin's decree on fast-track Russian citizenship for Transnistria residents.",
            "Kyiv Post",
            "https://www.kyivpost.com/topic/transnistria",
            "RUS",
            "moldova_transnistria",
            0.5,
        ),
        _e(
            "2026-08-18",
            "GRC",
            "hybrid",
            "25 нарушений воздушного пространства Греции и учебный воздушный бой над Эгейским "
            "морем после объявления Турцией двух «морских парков».",
            "25 violations of Greek airspace and a mock dogfight over the Aegean after Turkey "
            "announced two 'marine parks'.",
            "Proto Thema",
            "https://en.protothema.gr/2026/08/18/turkey-provokes-greece-25-violations-of-greek-airspace-and-mock-dogfight-over-the-aegean/",
            "TUR",
            "turkey_greece",
            0.5,
        ),
        _e(
            "2026-08-30",
            "NER",
            "elite_split",
            "Мятеж на базе 101 в Ниамее подавлен при участии российских сил; власти назвали "
            "его попыткой переворота.",
            "A mutiny at Base 101 in Niamey was put down with Russian help; the authorities "
            "called it a coup attempt.",
            "Al Jazeera",
            "https://www.aljazeera.com/amp/news/2026/8/30/nigers-military-led-government-says-it-contained-mutiny-what-next",
            None,
            "sahel_coups",
        ),
        _e(
            "2026-01",
            "BFA",
            "elite_split",
            "Власти Буркина-Фасо заявили о раскрытом заговоре; Того выдало бывшего лидера хунты "
            "Дамибу как предполагаемого организатора.",
            "Burkina Faso's authorities said they foiled a plot; Togo handed over former junta "
            "leader Damiba as its alleged mastermind.",
            "Modern Ghana",
            "https://www.modernghana.com/news/1531704/the-guard-versus-the-trenches-what-the-niamey.amp",
            None,
            "sahel_coups",
        ),
        _e(
            "2026-08-24",
            "SAU",
            "hybrid",
            "Хуситы, объявившие 20 июля морскую блокаду Саудовской Аравии, атаковали "
            "саудовский танкер у Янбу; 12 августа при их атаке на судно погибли шесть человек.",
            "The Houthis, who declared a naval blockade of Saudi Arabia on 20 July, hit a Saudi "
            "tanker off Yanbu; their 12 August attack on a ship killed six.",
            "Euronews",
            "https://euronews.com/2026/08/24/houthis-claim-strike-on-saudi-tanker-in-latest-red-sea-escalation",
            None,
            None,
        ),
        _e(
            "2026-11-11",
            "ARE",
            "hybrid",
            "Танкер DOMINICA PROSPERITY поражён неизвестным снарядом в 14 морских милях от "
            "Рас-эль-Хаймы и загорелся; нападения на суда в Ормузском проливе продолжаются.",
            "The tanker DOMINICA PROSPERITY was hit by an unknown projectile 14 nautical miles "
            "off Ras al Khaimah and caught fire; attacks on ships in the Strait of Hormuz go on.",
            "United Against Nuclear Iran (shipping update)",
            "https://www.unitedagainstnucleariran.com/node/46600",
            "IRN",
            "hormuz_reopening",
        ),
        _e(
            "2026-04-08",
            "IRN",
            "deescalation",
            "После 40 дней войны США и Иран при посредничестве Пакистана согласовали "
            "двухнедельное прекращение огня; позже оно продлено.",
            "After 40 days of war the US and Iran agreed a two-week ceasefire brokered by "
            "Pakistan; it was later extended.",
            "Dawn",
            "https://www.dawn.com/news/1989782",
            None,
            "iran_strikes",
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
        # Machine-classified news entries (curated=False) are automated evidence even when
        # the sign itself is a curated kind: a model reading headlines is not a human check.
        automated = spec.automated or sign.get("curated") is False
        if automated:
            lr **= auto_power
        lr = min(max(lr, 1 / SIGN_CAP), SIGN_CAP)
        if sign["key"] not in best or abs(math.log(lr)) > abs(math.log(best[sign["key"]]["lr"])):
            best[sign["key"]] = {"lr": lr, "auto": automated, "group": spec.group}
    # Signs of one group often report the same event (news, Telegram and GDELT counts), so
    # within a group only the strongest raising and the strongest lowering sign count.
    per_group: dict[tuple[str, bool, bool], float] = {}
    for item in best.values():
        key = (item["group"], item["auto"], item["lr"] >= 1)
        current = per_group.get(key, 1.0)
        if abs(math.log(item["lr"])) > abs(math.log(current)):
            per_group[key] = item["lr"]
    auto = math.prod(lr for (_, is_auto, _), lr in per_group.items() if is_auto)
    hard = math.prod(lr for (_, is_auto, _), lr in per_group.items() if not is_auto)
    auto = min(max(auto, AUTO_CAP[0]), auto_cap or AUTO_CAP[1])
    groups = {v["group"] for v in best.values() if v["lr"] > 1} & COMBO_GROUPS
    stage = sign_stage(groups)
    cap = STAGE_CAPS[stage]
    factor = min(max(auto * hard, TOTAL_FLOOR), cap)
    return {
        "factor": round(factor, 3),
        "signs": sorted(best),
        "groups": sorted(groups),
        "combo": False,
        "stage": stage,
        "cap": cap,
    }


def sign_stage(groups: Iterable[str]) -> int:
    present = set(groups)
    if "final" in present:
        return 3
    if present & {"personnel", "logistics"}:
        return 2
    if present & {"posture", "pretext", "cyber"}:
        return 1
    return 0


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


def make_sign(key: str, status: str, value_ru: str, value_en: str, **extra) -> dict:
    return _sign(key, status, value_ru, value_en, **extra)


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
                f"{site['name_ru']}: ×{site['ratio']:.2f} к недавнему уровню"
                + (
                    f", ×{site['seasonal_ratio']:.2f} к тому же сезону год назад"
                    if site.get("seasonal_ratio")
                    else ", прошлогодних данных нет"
                ),
                f"{site['name_en']}: ×{site['ratio']:.2f} vs recent level"
                + (
                    f", ×{site['seasonal_ratio']:.2f} vs the same season last year"
                    if site.get("seasonal_ratio")
                    else ", no data for last year"
                ),
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


def country_entry(country: Mapping, signs: list[dict]) -> dict:
    """Adjusted probabilities per risk type for one country's signs."""
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
    return {
        "signs": signs,
        "adjusted": adjusted,
        "active": len(active),
        "max_factor": max((a["factor"] for a in adjusted.values()), default=1.0),
        "alert": country_alert(adjusted),
    }


# --------------------------------------------------------------------------------------
# Alert levels: how far the next month is above the usual level, and how high it is

ALERT_LEVELS = ("green", "yellow", "orange", "red")
ALERT_RISKS = (INTERSTATE, INTERNAL, COUP, PROTEST, POLITICAL)


def alert_level(p1m: float, ratio: float, final_signs: bool) -> str:
    """green: as usual; yellow: 1.5x the usual level or >=3% within a month; orange: 3x or
    >=10%; red: >=20% within a month and last-stage signs (evacuations, closures, field
    hospitals, mobilisation) are present."""
    if p1m >= 0.2 and final_signs:
        return "red"
    if ratio >= 3 or p1m >= 0.1:
        return "orange"
    if ratio >= 1.5 or p1m >= 0.03:
        return "yellow"
    return "green"


def country_alert(adjusted: Mapping[str, Mapping]) -> dict:
    best = {"level": "green", "risk": None, "p1m": None, "ratio": 1.0}
    for risk in ALERT_RISKS:
        item = adjusted.get(risk)
        month = (item or {}).get("horizons", {}).get("1m")
        if not month:
            continue
        p1m = month["p"]
        final = bool({"final", "personnel", "logistics"} & set(item.get("groups", [])))
        level = alert_level(p1m, item["factor"], final)
        if ALERT_LEVELS.index(level) > ALERT_LEVELS.index(best["level"]) or (
            level == best["level"] and best["risk"] is not None and p1m > (best["p1m"] or 0)
        ):
            best = {"level": level, "risk": risk, "p1m": p1m, "ratio": item["factor"]}
    return best


PERSISTENCE_STRENGTH = 1.0  # removed in 1.4.0: a long-burning signal is more often background
FRESH_STRENGTH = 0.5
CONFIRM_DAYS = 3  # active on at least this many of the last five days
# Automated signs built from slow official data (not daily spikes) keep their full strength.
SLOW_AUTOMATED = frozenset(
    {
        "imf_crisis",
        "high_inflation",
        "election_soon",
        "ongoing_war",
        "milex_rise",
        "gpr_high",
        "currency_crash",
        "food_price_spike",
        "hazard_alert",
        "advisory_raised",
        "advisory_departure",
    }
)


def apply_persistence(
    country: Mapping,
    entry: dict,
    persistent: set[str],
    recent: Mapping[str, int] | None = None,
) -> dict:
    """Weigh automated daily signals by how well they are confirmed.

    * active on most of the last two weeks: strength × 1.25;
    * active on at least three of the last five days, or the country also has a verified
      (non-automated) sign: full strength;
    * otherwise a fresh one-off spike: strength × 0.5 (most such spikes were noise when the
      rules were replayed on 2008–2025 archives).
    """
    recent = recent or {}
    curated = any(
        s["status"] == "active" and not (SPEC.get(s["key"]) and SPEC[s["key"]].automated)
        for s in entry["signs"]
    )
    changed = False
    for sign in entry["signs"]:
        spec = SPEC.get(sign["key"])
        if not spec or not spec.automated or sign["status"] != "active":
            continue
        if sign["key"] in SLOW_AUTOMATED:
            continue
        if sign["key"] in persistent:
            sign["strength"] = sign.get("strength", 1.0) * PERSISTENCE_STRENGTH
            sign["persistent"] = True
            changed = True
        elif recent.get(sign["key"], 0) < CONFIRM_DAYS and not curated:
            sign["strength"] = sign.get("strength", 1.0) * FRESH_STRENGTH
            sign["fresh"] = True
            changed = True
    return country_entry(country, entry["signs"]) if changed else entry


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
    extra_signs: Mapping[str, list[dict]] | None = None,
    status: Mapping[str, str] | None = None,
    generated_at: datetime | None = None,
) -> dict:
    now = generated_at or datetime.now(UTC)
    today = today or now.date()
    entries: list = [*JOURNAL, *news_entries]
    countries: dict[str, dict] = {}
    for country in snapshot.get("countries", []):
        iso3 = country["iso3"]
        signs = (
            automated_signs(
                iso3,
                country,
                today=today,
                gdelt_z=(gdelt_z or {}).get(iso3) if gdelt_z is not None else None,
                gps=(gps or {}).get(iso3) if gps is not None else None,
                advisory_history=advisory_history,
                milex=(milex or {}).get(iso3),
                hazard_alerts=(hazard_alerts or {}).get(iso3, []),
                satellite=(satellite or {}).get(iso3, []),
            )
            + journal_signs(entries, iso3, today)
            + list((extra_signs or {}).get(iso3, []))
        )
        countries[iso3] = country_entry(country, signs)
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
