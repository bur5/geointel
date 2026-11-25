"""Scenario layer: concrete geopolitical scenarios with probabilities pooled from independent
components, an escalation/de-escalation indicator panel and the countries each scenario touches.

Components (each shown separately on the site):

* ``history`` - recency-weighted frequency of the same dyad being at interstate war (UCDP/PRIO);
* ``expert`` - a curated reference-class prior with a written basis (GeoIntel judgement);
* ``market`` - a matching Polymarket price, converted to an annual hazard.

Components are pooled as a weighted average (a linear opinion pool, which does not let one
extreme source dominate); the indicator panel then nudges the odds by a bounded factor.
Nothing here is calibrated yet and every scenario says so.
"""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime

from geointel.risk.betamath import beta_ppf
from geointel.risk.sources import polymarket

SCHEMA = "geointel-scenarios-v1"

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


def _t(codes: str) -> tuple[str, ...]:
    return tuple(codes.split())


_BALTIC_FRONT = (
    Exposure(
        "party",
        _t("RUS"),
        "Сторона сценария: нападение исходило бы от вооружённых сил России.",
        "Party: the attack would come from Russia's armed forces.",
    ),
    Exposure(
        "party",
        _t("BLR"),
        "Союзное государство с Россией; её территорию Россия уже использовала для "
        "вторжения в Украину в 2022 году, там размещено российское ядерное оружие.",
        "Union State with Russia; Russia used its territory to invade Ukraine in 2022 and "
        "has stationed nuclear weapons there.",
    ),
    Exposure(
        "frontline",
        _t("EST"),
        "Граница с Россией (Нарва — город с русскоязычным большинством); передовые силы "
        "НАТО под командованием Великобритании.",
        "Border with Russia (Narva has a Russian-speaking majority); NATO forward forces led "
        "by the UK.",
    ),
    Exposure(
        "frontline",
        _t("LVA"),
        "Граница с Россией и Беларусью; передовые силы НАТО под командованием Канады.",
        "Border with Russia and Belarus; NATO forward forces led by Canada.",
    ),
    Exposure(
        "frontline",
        _t("LTU"),
        "Граница с Беларусью и Калининградом; Сувалкский коридор — единственная сухопутная "
        "связь Прибалтики с остальным НАТО; бригада Бундесвера.",
        "Borders Belarus and Kaliningrad; the Suwałki corridor is the Baltics' only land link "
        "to the rest of NATO; German brigade stationed there.",
    ),
    Exposure(
        "frontline",
        _t("POL"),
        "Граница с Калининградом и Беларусью, Сувалкский коридор; главный логистический узел "
        "помощи Украине; крупнейшие войска США на восточном фланге.",
        "Borders Kaliningrad and Belarus and the Suwałki corridor; main logistics hub for aid "
        "to Ukraine; largest US troop presence on the eastern flank.",
    ),
    Exposure(
        "frontline",
        _t("FIN"),
        "Самая длинная граница НАТО с Россией (около 1340 км).",
        "NATO's longest border with Russia (about 1,340 km).",
    ),
    Exposure(
        "frontline",
        _t("NOR"),
        "Граница с Россией в Арктике рядом с базами Северного флота на Кольском полуострове.",
        "Arctic border with Russia next to the Northern Fleet bases on the Kola Peninsula.",
    ),
    Exposure(
        "frontline",
        _t("ROU"),
        "Граница с Украиной, на территорию уже падали российские дроны; Чёрное море; рядом "
        "Молдова с российскими войсками в Приднестровье.",
        "Borders Ukraine and has seen Russian drone debris; Black Sea; next to Moldova with "
        "Russian troops in Transnistria.",
    ),
    Exposure(
        "ally",
        _t("DEU"),
        "Статья 5 НАТО и 42.7 ЕС; бригада в Литве; главный транзитный узел войск НАТО на восток.",
        "NATO Article 5 and EU 42.7; brigade in Lithuania; main transit hub for NATO forces "
        "moving east.",
    ),
    Exposure(
        "ally",
        _t("USA"),
        "Статья 5 НАТО; основной военный потенциал альянса; войска в Польше и Прибалтике.",
        "NATO Article 5; the alliance's main military power; troops in Poland and the Baltics.",
    ),
    Exposure(
        "ally",
        _t("GBR CAN"),
        "Статья 5 НАТО; рамочные страны передовых сил в Эстонии (Великобритания) и Латвии "
        "(Канада) — их военные будут на месте с первого дня.",
        "NATO Article 5; framework nations of forward forces in Estonia (UK) and Latvia "
        "(Canada), so their troops are there from day one.",
    ),
    Exposure(
        "ally",
        _t("SWE DNK"),
        "Статья 5 НАТО и 42.7 ЕС; контроль над Балтийским морем (Готланд, Борнхольм, проливы).",
        "NATO Article 5 and EU 42.7; control of the Baltic Sea (Gotland, Bornholm, the straits).",
    ),
    Exposure(
        "ally",
        tuple(
            c for c in NATO if c not in _t("EST LVA LTU POL FIN NOR ROU DEU USA GBR CAN SWE DNK")
        ),
        "Статья 5 НАТО: нападение на одного союзника считается нападением на всех; страна "
        "должна решить, какую помощь оказать.",
        "NATO Article 5: an attack on one ally is an attack on all; each ally decides what "
        "assistance to give.",
    ),
    Exposure(
        "ally",
        _t("AUT CYP IRL MLT"),
        "Член ЕС вне НАТО: статья 42.7 обязывает помочь всеми доступными средствами, с учётом "
        "нейтралитета.",
        "EU member outside NATO: Article 42.7 obliges aid by all means in its power, "
        "respecting neutrality.",
    ),
    Exposure(
        "economic",
        _t("MDA GEO"),
        "Соседи России вне НАТО с российскими войсками или оккупированными территориями: "
        "эскалация повысит давление и на них.",
        "Russia's non-NATO neighbours with Russian troops or occupied areas: escalation would "
        "raise pressure on them too.",
    ),
    Exposure(
        "economic",
        _t("UKR"),
        "Уже воюет с Россией; война с НАТО изменила бы поставки помощи и ход боёв.",
        "Already at war with Russia; a war with NATO would change aid flows and the fighting.",
    ),
)

CATALOGUE: tuple[Scenario, ...] = (
    Scenario(
        key="russia_nato",
        title_ru="Военное нападение России на страну НАТО",
        title_en="Russian military attack on a NATO country",
        event_ru=(
            "Вооружённые силы России (в том числе без опознавательных знаков, если правительство "
            "пострадавшей страны признаёт это нападением) наносят удар по территории государства "
            "НАТО или вторгаются на неё, с погибшими или захватом территории. Диверсии, "
            "кибератаки и нарушения воздушного пространства без жертв не считаются."
        ),
        event_en=(
            "Russian armed forces (including unmarked forces, if the victim government calls it "
            "an attack) strike or enter the territory of a NATO state, causing deaths or seizing "
            "territory. Sabotage, cyberattacks and airspace violations without casualties do "
            "not count."
        ),
        polarity=1,
        expert=(0.03, 0.01, 0.08),
        expert_basis_ru=(
            "С 1945 года не было прямого военного нападения одной ядерной державы на членов "
            "противостоящего альянса, поэтому историческая частота близка к нулю. Но сейчас "
            "идёт война рядом с границей НАТО, Россия перевела экономику на военные рельсы, а "
            "несколько разведок публично предупреждают об ограниченном нападении. Оценка "
            "GeoIntel: около 3% в год, разумный диапазон 1–8%."
        ),
        expert_basis_en=(
            "Since 1945 no nuclear power has directly attacked members of an opposing alliance, "
            "so the historical frequency is near zero. But a war is under way next to NATO's "
            "border, Russia runs a war economy, and several intelligence services publicly warn "
            "of a limited attack. GeoIntel judgement: about 3% a year, plausible range 1–8%."
        ),
        side_a=_t("RUS"),
        side_b=tuple(NATO),
        market_queries=("Russia NATO", "Russia attack NATO", "Russia invade Baltic"),
        market_groups=(
            ("russia", "russian"),
            (
                "nato",
                "estonia",
                "latvia",
                "lithuania",
                "poland",
                "finland",
                "baltic",
                "norway",
                "romania",
            ),
            ("attack", "invade", "invasion", "strike", "military clash", "war ", "troops"),
        ),
        market_exclude=("ceasefire", "peace", "join", "summit", "meet ", "visit"),
        market_prefer=("invade", "invasion"),
        metaculus_queries=("Russia NATO", "Russia attack NATO", "Russia Baltic"),
        assessments=(
            Assessment(
                "2026-09-24",
                "Danish Defence Intelligence Service",
                "https://euronews.com/2026/09/24/denmark-says-russian-invasion-of-nato-country-highly-unlikely-but-cannot-be-ruled-out",
                "low",
                1.0,
                "There is a low but growing risk that Russia will launch a limited military "
                "attack against one or several NATO countries bordering Russia",
            ),
        ),
        milex=_t("RUS POL EST LVA LTU DEU FIN"),
        gpr=_t("RUS POL DEU FIN"),
        war_context=_t("RUS UKR"),
        exposures=_BALTIC_FRONT,
        warnings=(
            Warning(
                "2026-09-24",
                "Danish Defence Intelligence Service (DDIS)",
                "https://euronews.com/2026/09/24/denmark-says-russian-invasion-of-nato-country-highly-unlikely-but-cannot-be-ruled-out",
                1,
                "Разведка Дании: низкий, но растущий риск ограниченного военного нападения "
                "России на одну или несколько граничащих с ней стран НАТО; признаков подготовки "
                "полномасштабного вторжения нет.",
                "Danish intelligence: a low but growing risk of a limited Russian military "
                "attack on one or more NATO countries bordering Russia; no signs of preparation "
                "for a full-scale invasion.",
            ),
            Warning(
                "2026-08-07",
                "US intelligence assessments (reported by CNN and WSJ)",
                "https://edition.cnn.com/2026/08/07/politics/us-intelligence-russia-putin-nato-attack",
                1,
                "Оценки разведки США: Путин может попытаться проверить единство НАТО "
                "ограниченным нападением в ближайшие годы — от кибератаки до небольшого "
                "вторжения.",
                "US intelligence assessments: Putin could try to test NATO unity with a limited "
                "attack in the next few years, from a cyberattack to a small incursion.",
            ),
            Warning(
                "2026-06",
                "Lt Gen Christian Freuding, Chief of the German Army (reported)",
                "https://kyivindependent.com/us-intel-warns-russia-could-launch-attack-on-nato-countries-by-2029-wsj-reports/",
                1,
                "Командующий сухопутными войсками Германии: у России могут появиться "
                "возможности для удара по странам НАТО в течение трёх лет.",
                "Head of the German Army: Russia may have the capability to strike NATO "
                "countries within three years.",
            ),
            Warning(
                "2024-10-15",
                "Bruno Kahl, President of the German BND",
                "https://www.euronews.com/2024/10/15/russia-could-attack-nato-by-end-of-decade-german-intelligence-chief-warns",
                1,
                "Глава BND: Россия может напасть на НАТО до конца десятилетия.",
                "BND chief: Russia could attack NATO by the end of the decade.",
            ),
        ),
    ),
    Scenario(
        key="ukraine_ceasefire",
        title_ru="Прекращение огня между Россией и Украиной",
        title_en="Russia–Ukraine ceasefire",
        event_ru=(
            "Общее прекращение огня по всей линии фронта, объявленное обеими сторонами и "
            "соблюдаемое не менее 30 дней (локальные и энергетические перемирия не считаются)."
        ),
        event_en=(
            "A general ceasefire along the whole front, announced by both sides and holding "
            "for at least 30 days (local or energy-only truces do not count)."
        ),
        polarity=-1,
        expert=(0.25, 0.1, 0.45),
        expert_basis_ru=(
            "Межгосударственные войны длительностью больше четырёх лет редко заканчиваются "
            "быстро; переговоры при посредничестве США возобновились в ноябре 2026 года, "
            "но без прорыва по прекращению огня. Оценка GeoIntel: около 25% в год."
        ),
        expert_basis_en=(
            "Interstate wars lasting over four years rarely end quickly; US-mediated talks "
            "resumed in November 2026 without a ceasefire breakthrough. GeoIntel judgement: "
            "about 25% a year."
        ),
        market_queries=("Russia Ukraine ceasefire", "Ukraine peace deal"),
        market_groups=(("ceasefire", "peace deal", "truce", "armistice"), ("russia", "ukraine")),
        market_exclude=("energy", "black sea", "easter", "christmas"),
        milex=_t("RUS UKR"),
        gpr=_t("RUS UKR"),
        war_context=_t("RUS UKR"),
        exposures=(
            Exposure("party", _t("RUS UKR"), "Стороны войны.", "Parties to the war."),
            Exposure(
                "frontline",
                _t("POL ROU SVK HUN MDA"),
                "Соседи Украины: возвращение беженцев, восстановление, транзит, снижение риска "
                "падения дронов и ракет.",
                "Ukraine's neighbours: refugee returns, reconstruction, transit, lower risk of "
                "stray drones and missiles.",
            ),
            Exposure(
                "economic",
                _t("DEU CZE"),
                "Крупнейшие в ЕС принимающие страны украинских беженцев (данные UNHCR на "
                "странице миграции).",
                "Among the largest EU hosts of Ukrainian refugees (UNHCR data on the migration "
                "page).",
            ),
            Exposure(
                "economic",
                _t("EGY TUR"),
                "Импортёры зерна через Чёрное море: цены и поставки.",
                "Grain importers via the Black Sea: prices and supply.",
            ),
            Exposure(
                "economic",
                tuple(c for c in EU if c not in _t("POL ROU SVK HUN DEU CZE")),
                "ЕС: санкции, цены на энергию, расходы на оборону и помощь Украине.",
                "EU: sanctions, energy prices, defence spending and aid to Ukraine.",
            ),
        ),
        warnings=(
            Warning(
                "2026-11-11",
                "Jamestown Foundation, Eurasia Daily Monitor",
                "https://jamestown.org/russia-ukraine-u-s-talks-in-abu-dhabi-yield-little-progress/",
                0,
                "Переговоры в Абу-Даби 10–11 ноября 2026 года после девятимесячной паузы: "
                "договорённость о крупном обмене пленными, но без прорыва по прекращению огня "
                "и территориям.",
                "Abu Dhabi talks on 10–11 November 2026 after a nine-month pause: agreement on "
                "a large prisoner exchange but no breakthrough on a ceasefire or territory.",
            ),
        ),
    ),
    Scenario(
        key="china_taiwan",
        title_ru="Блокада или вторжение Китая на Тайвань",
        title_en="Chinese blockade or invasion of Taiwan",
        event_ru=(
            "КНР вводит блокаду или «карантин», фактически останавливающий коммерческое "
            "судоходство к Тайваню, либо наносит удары или высаживает войска. Учения без "
            "остановки судоходства не считаются."
        ),
        event_en=(
            "China imposes a blockade or 'quarantine' that actually stops commercial shipping "
            "to Taiwan, or strikes or lands troops. Drills that do not stop shipping do not "
            "count."
        ),
        polarity=1,
        expert=(0.025, 0.008, 0.07),
        expert_basis_ru=(
            "Прецедента нет; учения вокруг Тайваня становятся крупнее и всё больше похожи на "
            "отработку блокады. Оценка GeoIntel: около 2,5% в год."
        ),
        expert_basis_en=(
            "No precedent; drills around Taiwan keep growing and increasingly rehearse a "
            "blockade. GeoIntel judgement: about 2.5% a year."
        ),
        side_a=_t("CHN"),
        side_b=_t("TWN USA"),
        market_queries=("China invade Taiwan", "China blockade Taiwan"),
        market_groups=(("china", "chinese"), ("taiwan",), ("invade", "invasion", "blockade")),
        milex=_t("CHN TWN JPN"),
        gpr=_t("CHN TWN JPN"),
        exposures=(
            Exposure("party", _t("CHN TWN"), "Стороны сценария.", "Parties to the scenario."),
            Exposure(
                "frontline",
                _t("JPN"),
                "Остров Йонагуни примерно в 110 км от Тайваня; базы США на Окинаве.",
                "Yonaguni island is about 110 km from Taiwan; US bases on Okinawa.",
            ),
            Exposure(
                "frontline",
                _t("PHL"),
                "Лусонский пролив и острова Батанес рядом с Тайванем; базы, доступные войскам США.",
                "Luzon Strait and the Batanes islands next to Taiwan; bases open to US forces.",
            ),
            Exposure(
                "ally",
                _t("USA"),
                "Закон об отношениях с Тайванем, 7-й флот: наиболее вероятный внешний участник.",
                "Taiwan Relations Act and the 7th Fleet: the most likely outside participant.",
            ),
            Exposure(
                "ally",
                _t("KOR AUS"),
                "Союзники США в регионе; морские пути и цепочки поставок.",
                "US allies in the region; sea lanes and supply chains.",
            ),
            Exposure(
                "economic",
                _t("DEU NLD VNM MYS SGP"),
                "Зависимость от тайваньских полупроводников и судоходства через Тайваньский "
                "пролив и Южно-Китайское море.",
                "Dependence on Taiwanese semiconductors and shipping through the Taiwan Strait "
                "and the South China Sea.",
            ),
        ),
        warnings=(
            Warning(
                "2026-11-13",
                "Reuters (via Honolulu Star-Advertiser)",
                "https://www.staradvertiser.com/2026/11/13/breaking-news/china-stages-unannounced-pacific-drills-in-intimidation-of-taiwan/",
                1,
                "Необъявленные учения Китая в западной части Тихого океана в начале ноября "
                "2026 года — по словам тайваньского чиновника, крупнее учений «Миссия "
                "справедливости 2025».",
                "Unannounced Chinese drills in the western Pacific in early November 2026, "
                "larger than 'Justice Mission 2025' according to a Taiwanese official.",
            ),
        ),
    ),
    Scenario(
        key="iran_strikes",
        title_ru="Новые прямые удары между Ираном и Израилем или США",
        title_en="New direct strikes between Iran and Israel or the US",
        event_ru=(
            "Израиль или США наносят удары по территории Ирана, либо Иран — по Израилю или "
            "базам США, после последней паузы в боевых действиях."
        ),
        event_en=(
            "Israel or the US strikes Iranian territory, or Iran strikes Israel or US bases, "
            "after the latest pause in fighting."
        ),
        polarity=1,
        expert=(0.5, 0.25, 0.8),
        expert_basis_ru=(
            "В 2024–2026 годах прямые удары повторялись несколько раз, перемирия нарушались. "
            "Оценка GeoIntel: около 50% в год, широкий диапазон."
        ),
        expert_basis_en=(
            "Direct strikes recurred several times in 2024–2026 and truces broke down. "
            "GeoIntel judgement: about 50% a year, wide range."
        ),
        side_a=_t("IRN"),
        side_b=_t("ISR USA"),
        market_queries=("Israel strike Iran", "US strike Iran", "Iran Israel"),
        market_groups=(
            ("iran",),
            ("strike", "attack", "military action", "bomb"),
            ("israel", " us ", "u.s.", "united states", "iran strike"),
        ),
        market_exclude=("nuclear deal", "regime", "leader", "khamenei", "airspace"),
        market_inverse=(("iran",), ("israel",), ("ceasefire",), ("continue", "hold")),
        milex=_t("IRN ISR SAU"),
        gpr=_t("IRN ISR SAU"),
        exposures=(
            Exposure("party", _t("IRN ISR USA"), "Стороны сценария.", "Parties to the scenario."),
            Exposure(
                "frontline",
                _t("QAT BHR KWT ARE SAU IRQ"),
                "Базы США и инфраструктура, по которым Иран наносил ответные удары.",
                "US bases and infrastructure that Iran has hit in retaliation.",
            ),
            Exposure(
                "frontline",
                _t("JOR LBN YEM"),
                "Перехват ракет над территорией, фронт с «Хезболлой», хуситы.",
                "Missile interceptions overhead, the Hezbollah front, the Houthis.",
            ),
            Exposure(
                "frontline",
                _t("OMN"),
                "Ормузский пролив: угрозы судоходству.",
                "Strait of Hormuz: threats to shipping.",
            ),
            Exposure(
                "economic",
                _t("CHN IND JPN KOR"),
                "Крупнейшие импортёры нефти из Персидского залива через Ормузский пролив.",
                "Largest importers of Gulf oil through the Strait of Hormuz.",
            ),
            Exposure(
                "economic",
                _t("EGY"),
                "Доходы Суэцкого канала падают при атаках в Красном море.",
                "Suez Canal revenue falls when shipping in the Red Sea is attacked.",
            ),
        ),
        warnings=(
            Warning(
                "2026-07-08",
                "Dawn (live coverage, Reuters/AFP)",
                "https://www.dawn.com/news/1976395/iran-has-no-plans-to-negotiate-with-us-deputy-fm-says",
                1,
                "США нанесли удары по Ирану в ответ на атаки на суда в Ормузском проливе; Тегеран "
                "ответил.",
                "The US struck Iran in response to attacks on ships in the Strait of Hormuz; "
                "Tehran retaliated.",
            ),
            Warning(
                "2026-06-08",
                "Dawn (live coverage, Reuters/AFP)",
                "https://www.dawn.com/news/1976395/iranian-petrochemical-plant-hit-in-attack-irgc-launches-missiles-toward-israeli-air-bases",
                1,
                "Новый обмен ударами между Израилем и Ираном, перемирие под угрозой.",
                "A new exchange of strikes between Israel and Iran, putting the truce at risk.",
            ),
            Warning(
                "2026-02-28",
                "Dawn (live coverage, Reuters/AFP)",
                "https://www.dawn.com/news/1976395/iran-says-fully-restoring-security-in-hormuz-depends-on-cessation-of-us-blockade-threats",
                1,
                "США и Израиль начали совместные удары по Ирану.",
                "The US and Israel launched joint strikes on Iran.",
            ),
        ),
    ),
    Scenario(
        key="india_pakistan",
        title_ru="Военные удары между Индией и Пакистаном",
        title_en="Military strikes between India and Pakistan",
        event_ru=(
            "Удары авиацией, ракетами или артиллерией через границу или линию контроля с "
            "погибшими, признанные хотя бы одной из сторон."
        ),
        event_en=(
            "Air, missile or artillery strikes across the border or the Line of Control with "
            "deaths, acknowledged by at least one side."
        ),
        polarity=1,
        expert=(0.25, 0.1, 0.5),
        expert_basis_ru=(
            "Перестрелки на линии контроля с погибшими шли почти ежегодно в 2013–2020 годах; "
            "после перемирия февраля 2021 года — затишье до кризиса с ударами в мае 2025 года. "
            "Оценка GeoIntel: около 25% в год."
        ),
        expert_basis_en=(
            "Deadly exchanges of fire across the Line of Control happened almost every year in "
            "2013–2020; after the February 2021 ceasefire it was quiet until the May 2025 strikes. "
            "GeoIntel judgement: about 25% a year."
        ),
        side_a=_t("IND"),
        side_b=_t("PAK"),
        market_queries=("India Pakistan",),
        market_groups=(
            ("india",),
            ("pakistan",),
            ("strike", "military", "war", "clash", "attack"),
        ),
        market_exclude=("cricket", "match", "ceasefire"),
        milex=_t("IND PAK"),
        gpr=_t("IND PAK"),
        exposures=(
            Exposure("party", _t("IND PAK"), "Стороны сценария.", "Parties to the scenario."),
            Exposure(
                "frontline",
                _t("CHN"),
                "Главный поставщик оружия Пакистану; спорные границы с Индией.",
                "Pakistan's main arms supplier; disputed borders with India.",
            ),
            Exposure(
                "frontline",
                _t("AFG"),
                "Граница с Пакистаном; напряжённость на ней растёт при кризисах.",
                "Borders Pakistan; tension there rises in crises.",
            ),
            Exposure(
                "economic",
                _t("BGD NPL LKA ARE SAU"),
                "Региональная торговля, авиасообщение, трудовая миграция и денежные переводы.",
                "Regional trade, air routes, labour migration and remittances.",
            ),
        ),
    ),
    Scenario(
        key="korea",
        title_ru="Вооружённое столкновение на Корейском полуострове",
        title_en="Armed clash on the Korean Peninsula",
        event_ru="Вооружённое столкновение между КНДР и Республикой Корея с погибшими.",
        event_en="An armed clash between North and South Korea with deaths.",
        polarity=1,
        expert=(0.04, 0.015, 0.1),
        expert_basis_ru=(
            "Последние столкновения с погибшими — 2010 год (корвет «Чхонан», обстрел острова "
            "Ёнпхёндо). Оценка GeoIntel: около 4% в год."
        ),
        expert_basis_en=(
            "The last deadly clashes were in 2010 (the Cheonan sinking and the shelling of "
            "Yeonpyeong). GeoIntel judgement: about 4% a year."
        ),
        side_a=_t("PRK"),
        side_b=_t("KOR USA"),
        market_queries=("North Korea South Korea", "North Korea attack"),
        market_groups=(
            ("north korea", "dprk"),
            ("south korea", "attack", "invade", "clash", "war "),
        ),
        market_exclude=("missile test", "nuclear test", "launch", "meet", "diplomatic", "talks"),
        milex=_t("PRK KOR JPN"),
        gpr=_t("KOR JPN"),
        exposures=(
            Exposure("party", _t("PRK KOR"), "Стороны сценария.", "Parties to the scenario."),
            Exposure(
                "ally",
                _t("USA"),
                "Договор о взаимной обороне; около 28,5 тыс. военных США в Южной Корее.",
                "Mutual defence treaty; about 28,500 US troops in South Korea.",
            ),
            Exposure(
                "frontline",
                _t("JPN"),
                "Ракеты КНДР пролетают над Японией; базы США.",
                "North Korean missiles overfly Japan; US bases.",
            ),
            Exposure(
                "ally",
                _t("CHN RUS"),
                "Договоры с КНДР: Китай (1961) и Россия (2024) — с пунктом о взаимной помощи.",
                "Treaties with North Korea: China (1961) and Russia (2024), with mutual "
                "assistance clauses.",
            ),
        ),
    ),
)


def _large_war() -> Scenario:
    limited = CATALOGUE[0]
    return replace(
        limited,
        key="russia_nato_war",
        title_ru="Большая война России с НАТО",
        title_en="Large-scale war between Russia and NATO",
        event_ru=(
            "Боевые действия между вооружёнными силами России и нескольких государств НАТО, "
            "идущие дольше семи дней, или военный ответ альянса по статье 5 на нападение России."
        ),
        event_en=(
            "Fighting between the armed forces of Russia and several NATO states lasting more "
            "than seven days, or an Article 5 military response to a Russian attack."
        ),
        expert=(0.007, 0.002, 0.025),
        expert_basis_ru=(
            "Ограниченное нападение может перерасти в большую войну лишь в части случаев; "
            "разведки не видят подготовки к вторжению и считают, что для региональной войны "
            "России нужны годы. Оценка GeoIntel: около 0,7% в год, диапазон 0,2–2,5%."
        ),
        expert_basis_en=(
            "Only some limited attacks would escalate into a large war; intelligence services "
            "see no preparation for an invasion and judge that Russia needs years to be ready "
            "for a regional war. GeoIntel judgement: about 0.7% a year, range 0.2–2.5%."
        ),
        market_prefer=("war", "invade"),
        use_history=False,
        assessments=(
            Assessment(
                "2026-09-24",
                "Danish Defence Intelligence Service",
                "https://euronews.com/2026/09/24/denmark-says-russian-invasion-of-nato-country-highly-unlikely-but-cannot-be-ruled-out",
                "highly unlikely",
                3.0,
                "an outright invasion was highly unlikely but possible",
            ),
        ),
    )


CATALOGUE = (CATALOGUE[0], _large_war(), *CATALOGUE[1:])

# --------------------------------------------------------------------------------------
# Components


def _hazard_to_p(hazard: float, years: float) -> float:
    return 1 - (1 - hazard) ** years


def _p_to_hazard(p: float, years: float) -> float:
    p = min(max(p, 0.0), 0.999)
    return 1 - (1 - p) ** (1 / years)


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _expit(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def history_component(
    scenario: Scenario,
    dyads: Mapping[frozenset[str], set[int]],
    last_year: int,
    first_year: int = 1946,
    half_life: float = 15.0,
) -> dict | None:
    if not scenario.side_a or not scenario.side_b:
        return None
    years: set[int] = set()
    for a in scenario.side_a:
        for b in scenario.side_b:
            years |= dyads.get(frozenset((a, b)), set())
    weights = {y: 0.5 ** ((last_year - y) / half_life) for y in range(first_year, last_year + 1)}
    n = sum(weights.values())
    s = sum(w for y, w in weights.items() if y in years)
    a, b = 0.5 + s, 0.5 + n - s
    recent = sorted(y for y in years if y >= last_year - 30)
    return {
        "kind": "history",
        "annual": round(a / (a + b), 4),
        "low": round(beta_ppf(0.05, a, b), 4),
        "high": round(beta_ppf(0.95, a, b), 4),
        "weight": 0.35,
        "detail_ru": (
            f"Годы межгосударственного конфликта между сторонами по UCDP/PRIO с {first_year} "
            f"по {last_year} г.: "
            f"{len(years)}; за последние 30 лет: {', '.join(map(str, recent)) or 'нет'}. "
            f"Недавние годы весят больше (полупериод {half_life:.0f} лет). Вес низкий: данные "
            "отстают на год, а сценарии как раз о разрыве с прошлым."
        ),
        "detail_en": (
            f"Years of interstate conflict between the sides in UCDP/PRIO, {first_year}–"
            f"{last_year}: "
            f"{len(years)}; in the last 30 years: {', '.join(map(str, recent)) or 'none'}. "
            f"Recent years weigh more (half-life {half_life:.0f} years). Low weight: the data "
            "lag a year and a structural break is exactly what scenarios are about."
        ),
        "url": "https://ucdp.uu.se/downloads/",
    }


def expert_component(scenario: Scenario) -> dict:
    mid, low, high = scenario.expert
    return {
        "kind": "expert",
        "annual": mid,
        "low": low,
        "high": high,
        "weight": 1.0,
        "detail_ru": scenario.expert_basis_ru,
        "detail_en": scenario.expert_basis_en,
        "url": None,
    }


MIN_MARKET_DAYS = 120  # shorter windows say little about a year and are not annualised


def market_candidates(scenario: Scenario, all_markets: Iterable[dict]) -> list[dict]:
    found = []
    for m in all_markets:
        if polymarket.matches(m["question"], scenario.market_groups, scenario.market_exclude):
            found.append({**m, "inverse": False})
        elif scenario.market_inverse and polymarket.matches(m["question"], scenario.market_inverse):
            found.append({**m, "p": round(1 - m["p"], 4), "inverse": True})
    return sorted(found, key=lambda m: -m["volume"])


def _fit(scenario: Scenario | None, market: dict) -> int:
    text = market["question"].lower()
    return int(bool(scenario) and any(word in text for word in scenario.market_prefer))


def _days(market: dict, today: date) -> int:
    return (date.fromisoformat(market["end"]) - today).days


def near_term_market(scenario: Scenario, candidates: list[dict], today: date) -> dict | None:
    """The best-fitting liquid open market (shown as a signal even if it resolves soon)."""
    open_ = [m for m in candidates if m["volume"] >= 5000 and _days(m, today) > 0]
    if not open_:
        return None
    return max(open_, key=lambda m: (_fit(scenario, m), m["volume"]))


def market_component(
    candidates: list[dict], today: date, scenario: Scenario | None = None
) -> dict | None:
    usable = [
        m
        for m in candidates
        if m["volume"] >= 5000 and not m.get("inverse") and _days(m, today) >= MIN_MARKET_DAYS
    ]
    if not usable:
        return None
    best = max(usable, key=lambda m: (_fit(scenario, m), m["volume"]))
    days = _days(best, today)
    years = days / 365.25
    hazard = _p_to_hazard(best["p"], years)
    # Windows under a year still say less about a whole year: their weight shrinks a little.
    weight = (1.5 if best["volume"] >= 100_000 else 0.75) * min(1.0, days / 365)
    return {
        "kind": "market",
        "annual": round(hazard, 4),
        "low": round(min(hazard * 0.6, 0.999), 4),
        "high": round(min(hazard * 1.6, 0.999), 4),
        "weight": round(weight, 2),
        "detail_ru": (
            f"Рынок Polymarket: «{best['question']}» — {best['p'] * 100:.1f}% к {best['end']}, "
            + f"объём торгов ${best['volume']:,.0f}. ".replace(",", " ")
            + "Пересчитано в годовую вероятность. Вопрос рынка может отличаться от определения "
            "сценария."
        ),
        "detail_en": (
            f'Polymarket: "{best["question"]}" at {best["p"] * 100:.1f}% by {best["end"]}, '
            f"volume ${best['volume']:,.0f}. Converted to an annual probability. The market's "
            "question may differ from the scenario definition."
        ),
        "url": polymarket.url(best["slug"]),
        "market": best,
    }


# --------------------------------------------------------------------------------------
# Indicators


def _warning_date(value: str) -> date:
    """Warnings may carry a full date or only a month (YYYY-MM) when the day is unknown."""
    return date.fromisoformat(value if len(value) > 7 else f"{value}-01")


def watched_countries(scenario: Scenario) -> set[str]:
    core = {c for e in scenario.exposures if e.role in ("party", "frontline") for c in e.countries}
    return core | set(scenario.milex) | set(scenario.gpr)


def scenario_signs(
    scenario: Scenario,
    country_signs: Mapping[str, list[dict]],
    dyad_trend: Mapping[str, dict] | None,
    active_interstate: set[str],
) -> list[dict]:
    """Active interstate signs in the scenario's parties and front-line countries."""
    from geointel.risk.warning_signs import INTERSTATE, SPEC

    found: list[dict] = []
    for code in sorted(watched_countries(scenario)):
        for sign in country_signs.get(code, []):
            spec = SPEC.get(sign["key"])
            if sign.get("status") != "active" or spec is None or INTERSTATE not in spec.applies:
                continue
            if (
                sign.get("actor")
                and scenario.side_a
                and sign["actor"]
                not in (
                    *scenario.side_a,
                    *scenario.side_b,
                )
            ):
                continue
            found.append({**sign, "country": code})
    for pair, trend in (dyad_trend or {}).items():
        a, b = pair.split("-")
        if (
            (a in scenario.side_a or b in scenario.side_a)
            and trend["ratio"] >= 2
            and trend["recent"] >= 10
        ):
            found.append(
                {
                    "key": "gdelt_external",
                    "group": "events",
                    "status": "active",
                    "lr": SPEC["gdelt_external"].lr,
                    "value_ru": f"{a}–{b}: {trend['recent']} событий за 30 дней (норма "
                    f"{trend['expected']})",
                    "value_en": f"{a}–{b}: {trend['recent']} events in 30 days (normal "
                    f"{trend['expected']})",
                    "source": "GDELT",
                    "country": b,
                }
            )
    at_war = [c for c in scenario.war_context if c in active_interstate]
    if at_war:
        found.append(
            {
                "key": "ongoing_war",
                "group": "intel",
                "status": "active",
                "lr": SPEC["ongoing_war"].lr,
                "value_ru": "идёт межгосударственная война: " + ", ".join(at_war),
                "value_en": "interstate war under way: " + ", ".join(at_war),
                "source": "UCDP/PRIO",
                "country": at_war[0],
            }
        )
    return found


def structural_signs(
    scenario: Scenario,
    milex: Mapping[str, dict],
    gpr: Mapping[str, dict],
) -> dict[str, list[dict]]:
    """Minimal per-country signs when the full signal layer is not available."""
    from geointel.risk.warning_signs import SPEC

    result: dict[str, list[dict]] = {}
    for code in scenario.milex:
        m = milex.get(code) or {}
        if m.get("change5") is not None and m["change5"] >= 1:
            result.setdefault(code, []).append(
                {
                    "key": "milex_rise",
                    "group": "economy_prep",
                    "status": "active",
                    "lr": SPEC["milex_rise"].lr,
                    "source": "SIPRI",
                    "value_ru": f"{code} {m['value']:.1f}% ({m['change5']:+.1f})",
                    "value_en": f"{code} {m['value']:.1f}% ({m['change5']:+.1f})",
                }
            )
    for code in scenario.gpr:
        r = (gpr.get(code) or {}).get("ratio_12m")
        if r and r >= 1.5:
            result.setdefault(code, []).append(
                {
                    "key": "gpr_high",
                    "group": "intel",
                    "status": "active",
                    "lr": SPEC["gpr_high"].lr,
                    "source": "GPR",
                    "value_ru": f"{code} ×{r:.2f}",
                    "value_en": f"{code} ×{r:.2f}",
                }
            )
    return result


def near_term_indicator(near: dict | None) -> dict | None:
    if near is None:
        return None
    change = near.get("month_change")
    if near.get("inverse") and change is not None:
        change = -change
    trend = "" if change is None else f"; {change * 100:+.1f} pp / 30d"
    direction = 0 if change is None else 1 if change > 0.03 else -1 if change < -0.03 else 0
    value = (
        f"{near['p'] * 100:.1f}% → {near['end']}{trend}. "
        f"{'NOT: ' if near.get('inverse') else ''}{near['question'][:120]}"
    )
    return {
        "key": "market_trend",
        "group": "market",
        "direction": direction,
        "lr": 1.0,
        "label_ru": "Рынок прогнозов: ближайший вопрос (не входит в расчёт)",
        "label_en": "Prediction market: nearest question (not in the calculation)",
        "value_ru": value,
        "value_en": value,
        "value": value,
        "source": "Polymarket",
        "countries": [],
    }


def indicator_list(signs: list[dict], near: dict | None) -> list[dict]:
    """One row per sign key, listing the countries where it is active."""
    from geointel.risk.warning_signs import SPEC

    rows: dict[str, dict] = {}
    for sign in signs:
        spec = SPEC[sign["key"]]
        row = rows.setdefault(
            sign["key"],
            {
                "key": sign["key"],
                "group": spec.group,
                "direction": 1 if spec.lr > 1 else -1,
                "lr": round(spec.lr ** sign.get("strength", 1.0), 3),
                "label_ru": spec.label_ru,
                "label_en": spec.label_en,
                "value_ru": sign.get("value_ru", ""),
                "value_en": sign.get("value_en", ""),
                "value": sign.get("value_en", ""),
                "source": sign.get("source", ""),
                "url": sign.get("url"),
                "countries": [],
            },
        )
        lr = spec.lr ** sign.get("strength", 1.0)
        if abs(math.log(lr)) > abs(math.log(row["lr"])):
            row.update(
                lr=round(lr, 3),
                value_ru=sign.get("value_ru", ""),
                value_en=sign.get("value_en", ""),
                url=sign.get("url"),
            )
        if sign.get("country") and sign["country"] not in row["countries"]:
            row["countries"].append(sign["country"])
    result = sorted(rows.values(), key=lambda r: -abs(math.log(r["lr"])))
    market = near_term_indicator(near)
    return result + ([market] if market else [])


def scenario_factor(signs: list[dict], polarity: int) -> dict:
    from geointel.risk.warning_signs import INTERSTATE, combine

    combined = combine(signs, INTERSTATE)
    factor = combined["factor"]
    if polarity < 0:  # escalation makes a ceasefire less likely, and vice versa
        factor = min(max(1 / factor, 0.5), 2.0)
    return {**combined, "factor": round(factor, 3)}


def official_component(scenario: Scenario, today: date) -> dict | None:
    from geointel.risk.warning_signs import ESTIMATIVE

    usable = [
        a
        for a in scenario.assessments
        if a.phrase in ESTIMATIVE and (today - _warning_date(a.date)).days <= 400
    ]
    if not usable:
        return None
    latest = max(usable, key=lambda a: a.date)
    low, high = ESTIMATIVE[latest.phrase]
    mid = math.sqrt(low * high)
    to_annual = lambda p: _p_to_hazard(p, latest.years)  # noqa: E731
    return {
        "kind": "official",
        "annual": round(to_annual(mid), 4),
        "low": round(to_annual(low), 4),
        "high": round(to_annual(high), 4),
        "weight": 1.0,
        "detail_ru": (
            f"{latest.source}, {latest.date}: «{latest.quote_en}». Формулировка «{latest.phrase}» "
            f"по шкале GeoIntel = {low * 100:.0f}–{high * 100:.0f}% за {latest.years:g} г."
        ),
        "detail_en": (
            f'{latest.source}, {latest.date}: "{latest.quote_en}". The phrase '
            f'"{latest.phrase}" on the GeoIntel scale = {low * 100:.0f}–{high * 100:.0f}% '
            f"over {latest.years:g} year(s)."
        ),
        "url": latest.url,
    }


def community_component(
    scenario: Scenario, questions: list[dict], today: date
) -> tuple[dict | None, list[dict]]:
    found = [
        q
        for q in questions
        if polymarket.matches(q["question"], scenario.market_groups, scenario.market_exclude)
    ]
    usable = [q for q in found if _days(q, today) >= MIN_MARKET_DAYS and q["forecasters"] >= 20]
    if not usable:
        return None, found
    best = max(usable, key=lambda q: (_fit(scenario, q), q["forecasters"]))
    days = _days(best, today)
    hazard = _p_to_hazard(best["p"], days / 365.25)
    return (
        {
            "kind": "community",
            "annual": round(hazard, 4),
            "low": round(min(hazard * 0.6, 0.999), 4),
            "high": round(min(hazard * 1.6, 0.999), 4),
            "weight": 1.5 * min(1.0, days / 365),
            "detail_ru": (
                f"Metaculus: «{best['question']}» — {best['p'] * 100:.1f}% к {best['end']}, "
                f"{best['forecasters']} прогнозистов. Пересчитано в годовую вероятность."
            ),
            "detail_en": (
                f'Metaculus: "{best["question"]}" at {best["p"] * 100:.1f}% by {best["end"]}, '
                f"{best['forecasters']} forecasters. Converted to an annual probability."
            ),
            "url": best["url"],
        },
        found,
    )


def pool(components: list[dict], factor: float) -> dict:
    total = sum(c["weight"] for c in components)
    mean = sum(c["weight"] * c["annual"] for c in components) / total  # linear opinion pool
    annual = _expit(_logit(mean) + math.log(factor))
    low = min(c["low"] for c in components)
    high = max(c["high"] for c in components)
    low, high = min(low, annual), max(high, annual)
    spread = max(c["annual"] for c in components) / max(min(c["annual"] for c in components), 1e-4)
    confidence = "medium" if len(components) >= 3 and spread < 3 else "low"
    horizons = {
        h: {
            "p": round(_hazard_to_p(annual, y), 4),
            "low": round(_hazard_to_p(low, y), 4),
            "high": round(_hazard_to_p(high, y), 4),
        }
        for h, y in HORIZON_YEARS.items()
    }
    return {
        "annual": {"p": round(annual, 4), "low": round(low, 4), "high": round(high, 4)},
        "horizons": horizons,
        "confidence": confidence,
    }


def build_scenarios(
    *,
    dyads: Mapping[frozenset[str], set[int]] | None,
    last_conflict_year: int | None,
    active_interstate: set[str],
    markets: list[dict] | None,
    milex: Mapping[str, dict],
    gpr: Mapping[str, dict],
    generated_at: datetime | None = None,
    catalogue: tuple[Scenario, ...] = CATALOGUE,
    country_signs: Mapping[str, list[dict]] | None = None,
    dyad_trend: Mapping[str, dict] | None = None,
    community: list[dict] | None = None,
) -> dict:
    now = generated_at or datetime.now(UTC)
    today = now.date()
    result = []
    for scenario in catalogue:
        components = [expert_component(scenario)]
        if dyads is not None and last_conflict_year and scenario.use_history:
            history = history_component(scenario, dyads, last_conflict_year)
            if history:
                components.insert(0, history)
        candidates = market_candidates(scenario, markets or []) if markets is not None else []
        market = market_component(candidates, today, scenario)
        if market:
            components.append(market)
        official = official_component(scenario, today)
        if official:
            components.append(official)
        found_community: list[dict] = []
        if community is not None:
            comp, found_community = community_component(scenario, community, today)
            if comp:
                components.append(comp)
        near = near_term_market(scenario, candidates, today)
        per_country = (
            country_signs if country_signs is not None else structural_signs(scenario, milex, gpr)
        )
        signs = scenario_signs(scenario, per_country, dyad_trend, active_interstate)
        factor_info = scenario_factor(signs, scenario.polarity)
        factor = factor_info["factor"]
        pooled = pool(components, factor)
        affected: list[dict] = []
        seen: set[str] = set()
        for exposure in scenario.exposures:
            for code in exposure.countries:
                if code in seen:
                    continue
                seen.add(code)
                affected.append(
                    {
                        "iso3": code,
                        "role": exposure.role,
                        "reason_ru": exposure.reason_ru,
                        "reason_en": exposure.reason_en,
                    }
                )
        result.append(
            {
                "key": scenario.key,
                "title_ru": scenario.title_ru,
                "title_en": scenario.title_en,
                "event_ru": scenario.event_ru,
                "event_en": scenario.event_en,
                "polarity": scenario.polarity,
                **pooled,
                "indicator_factor": factor,
                "sign_groups": factor_info["groups"],
                "sign_combo": factor_info["combo"],
                "components": [{k: v for k, v in c.items() if k != "market"} for c in components],
                "indicators": indicator_list(signs, near),
                "community_candidates": found_community[:6],
                "community_status": (
                    "unavailable"
                    if community is None
                    else "matched"
                    if any(c["kind"] == "community" for c in components)
                    else "no_match"
                ),
                "warnings": [
                    {
                        "date": w.date,
                        "source": w.source,
                        "url": w.url,
                        "direction": w.direction,
                        "summary_ru": w.summary_ru,
                        "summary_en": w.summary_en,
                    }
                    for w in sorted(scenario.warnings, key=lambda w: w.date, reverse=True)
                ],
                "market_candidates": [
                    {k: m[k] for k in ("question", "p", "end", "volume", "slug", "inverse")}
                    for m in candidates[:6]
                ],
                "market_status": (
                    "unavailable" if markets is None else "matched" if market else "no_match"
                ),
                "affected": affected,
                "calibration": "uncalibrated",
            }
        )
    return {"schema": SCHEMA, "generated_at": now.isoformat(), "scenarios": result}
