"""Regional scenarios added in November 2026: Moldova and Transnistria, Belarus, Serbia–Kosovo,
Venezuela–Guyana, Turkey–Greece, coups in the Sahel and a weakening of US guarantees to Europe.

Each scenario states the event precisely, gives a reference-class prior with a written basis and
lists the countries it touches. Expert priors are GeoIntel judgement and are uncalibrated.
"""

from geointel.risk.scenario_types import EU, NATO, Exposure, Scenario, Warning, _t

_PARTIES = "Стороны сценария."
_PARTIES_EN = "Parties to the scenario."

MOLDOVA = Scenario(
    key="moldova_transnistria",
    title_ru="Вооружённый конфликт в Молдове и Приднестровье",
    title_en="Armed conflict in Moldova and Transnistria",
    event_ru=(
        "Боевые столкновения с погибшими между силами Молдовы (или Украины) и российскими "
        "либо приднестровскими вооружёнными формированиями, или военная операция России на "
        "территории Молдовы."
    ),
    event_en=(
        "Deadly armed clashes between Moldovan (or Ukrainian) forces and Russian or Transnistrian "
        "armed units, or a Russian military operation on Moldovan territory."
    ),
    polarity=1,
    expert=(0.03, 0.01, 0.08),
    expert_basis_ru=(
        "Боёв не было с 1992 года. В Приднестровье, по разным оценкам, 1000–2000 российских "
        "военных, с января 2026 года отрезанных от снабжения Украиной и Молдовой; сухопутного "
        "пути из России нет. Риск растёт при прорыве России к Одессе или после прекращения огня "
        "в Украине. Оценка GeoIntel: около 3% в год."
    ),
    expert_basis_en=(
        "No fighting since 1992. Transnistria hosts an estimated 1,000–2,000 Russian troops, cut "
        "off from supplies by Ukraine and Moldova since January 2026; Russia has no land route. "
        "The risk rises if Russia breaks through towards Odesa or after a ceasefire in Ukraine. "
        "GeoIntel judgement: about 3% a year."
    ),
    side_a=_t("RUS"),
    side_b=_t("MDA"),
    market_queries=("Moldova Russia", "Transnistria"),
    market_groups=(("moldova", "transnistria"), ("russia", "war", "invade", "attack", "troops")),
    market_exclude=("election", "eu accession", "join the eu"),
    use_history=False,
    prior_includes=("ongoing_war",),
    milex=_t("RUS MDA"),
    gpr=_t("RUS"),
    war_context=_t("RUS UKR"),
    exposures=(
        Exposure("party", _t("RUS MDA"), _PARTIES, _PARTIES_EN),
        Exposure(
            "frontline",
            _t("UKR"),
            "Граница с Приднестровьем рядом с Одессой; Украина держит войска у этой границы.",
            "Borders Transnistria near Odesa; Ukraine keeps troops along that border.",
        ),
        Exposure(
            "frontline",
            _t("ROU"),
            "Граница с Молдовой, общий язык и паспорта у сотен тысяч молдаван; страна НАТО.",
            "Borders Moldova; shared language and passports held by hundreds of thousands of "
            "Moldovans; NATO member.",
        ),
        Exposure(
            "economic",
            tuple(c for c in EU if c != "ROU"),
            "Молдова — кандидат в ЕС; беженцы и энергетика.",
            "Moldova is an EU candidate; refugees and energy.",
        ),
    ),
    warnings=(
        Warning(
            "2026-05-15",
            "Kyiv Post",
            "https://www.kyivpost.com/topic/transnistria",
            1,
            "Путин подписал указ об упрощённом получении российского гражданства жителями "
            "Приднестровья; президент Молдовы Санду считает, что его могут использовать для "
            "мобилизации.",
            "Putin signed a decree on fast-track Russian citizenship for Transnistria residents; "
            "Moldovan President Sandu says it could be used for mobilisation.",
        ),
        Warning(
            "2026-04-16",
            "Kyiv Post",
            "https://www.kyivpost.com/post/74088",
            1,
            "Молдова объявила командиров российского контингента в Приднестровье персонами "
            "нон грата.",
            "Moldova declared the commanders of the Russian contingent in Transnistria persona "
            "non grata.",
        ),
    ),
)

BELARUS = Scenario(
    key="belarus_front",
    title_ru="Новый фронт с территории Беларуси",
    title_en="A new front from Belarusian territory",
    event_ru=(
        "Наземное наступление или удары вооружённых сил Беларуси либо России с территории "
        "Беларуси по Украине или стране НАТО, открывающие новое направление боевых действий "
        "(отдельные пуски ракет и дронов без наземной операции не считаются)."
    ),
    event_en=(
        "A ground offensive or strikes by Belarusian or Russian forces from Belarusian territory "
        "against Ukraine or a NATO country that open a new line of fighting (isolated missile or "
        "drone launches without a ground operation do not count)."
    ),
    polarity=1,
    expert=(0.04, 0.01, 0.1),
    expert_basis_ru=(
        "В феврале 2022 года Россия наступала на Киев с территории Беларуси. Сейчас там "
        "около 2100 российских военных и комплекс «Орешник» (с декабря 2025 года); армия "
        "Беларуси в войну не вступала. Большой группировки у границ не видно — для нового "
        "фронта нужны месяцы сосредоточения, которые заметны со спутников. Оценка GeoIntel: "
        "около 4% в год."
    ),
    expert_basis_en=(
        "In February 2022 Russia attacked towards Kyiv from Belarus. About 2,100 Russian troops "
        "and the Oreshnik system (since December 2025) are there now; Belarus's army has not "
        "joined the war. No large grouping is visible near the borders, and a new front would "
        "need months of build-up visible from satellites. GeoIntel judgement: about 4% a year."
    ),
    side_a=_t("BLR RUS"),
    side_b=_t("UKR POL LTU LVA"),
    market_queries=("Belarus war", "Belarus invade"),
    market_groups=(("belarus",), ("invade", "attack", "enter the war", "offensive", "troops")),
    market_exclude=("election", "lukashenko out", "release"),
    use_history=False,
    prior_includes=("ongoing_war",),
    milex=_t("BLR RUS"),
    gpr=_t("RUS UKR POL"),
    war_context=_t("RUS UKR"),
    exposures=(
        Exposure("party", _t("BLR RUS"), _PARTIES, _PARTIES_EN),
        Exposure(
            "frontline",
            _t("UKR"),
            "Северная граница с Беларусью длиной около 1000 км; в 2022 году отсюда шло "
            "наступление на Киев.",
            "A northern border with Belarus of about 1,000 km; the 2022 offensive on Kyiv came "
            "from here.",
        ),
        Exposure(
            "frontline",
            _t("POL LTU LVA"),
            "Граница НАТО с Беларусью; Сувалкский коридор; гибридные провокации на границе.",
            "NATO's border with Belarus; the Suwałki corridor; hybrid provocations at the border.",
        ),
        Exposure(
            "ally",
            _t("DEU USA EST FIN"),
            "Союзники по НАТО с войсками на восточном фланге.",
            "NATO allies with forces on the eastern flank.",
        ),
    ),
    warnings=(
        Warning(
            "2026-03-13",
            "Kyiv Post (citing BelTA)",
            "https://www.kyivpost.com/amp/post/71898",
            1,
            "Лукашенко пригрозил применить «Орешник», если Украина, Польша, Литва или Латвия "
            "будут «вмешиваться».",
            "Lukashenko threatened to use the Oreshnik if Ukraine, Poland, Lithuania or Latvia "
            "'interfere'.",
        ),
    ),
)

SERBIA_KOSOVO = Scenario(
    key="serbia_kosovo",
    title_ru="Вооружённое столкновение Сербии и Косово",
    title_en="Armed clash between Serbia and Kosovo",
    event_ru=(
        "Столкновение с погибшими между сербскими силами (армия, полиция или поддерживаемые "
        "Белградом вооружённые группы) и полицией Косово либо KFOR, или ввод сербской армии "
        "в Косово."
    ),
    event_en=(
        "A deadly clash between Serbian forces (army, police or Belgrade-backed armed groups) "
        "and Kosovo police or KFOR, or Serbian troops entering Kosovo."
    ),
    polarity=1,
    expert=(0.06, 0.02, 0.15),
    expert_basis_ru=(
        "После 1999 года прямых боёв армий не было; в сентябре 2023 года вооружённая сербская "
        "группа напала на полицию Косово в Баньске (погибли четыре человека), Сербия стягивала "
        "войска к границе в 2022–2023 годах. Около 4000 военных KFOR сдерживают эскалацию. "
        "Оценка GeoIntel: около 6% в год."
    ),
    expert_basis_en=(
        "There has been no army-to-army fighting since 1999; in September 2023 a Serbian armed "
        "group attacked Kosovo police at Banjska (four dead), and Serbia massed troops at the "
        "boundary in 2022–2023. About 4,000 KFOR troops restrain escalation. GeoIntel judgement: "
        "about 6% a year."
    ),
    side_a=_t("SRB"),
    side_b=_t("XKX"),
    market_queries=("Serbia Kosovo",),
    market_groups=(("serbia",), ("kosovo",), ("war", "clash", "invade", "attack", "military")),
    market_exclude=("football", "match", "election", "recognize"),
    use_history=False,
    milex=_t("SRB"),
    gpr=_t("SRB"),
    exposures=(
        Exposure("party", _t("SRB XKX"), _PARTIES, _PARTIES_EN),
        Exposure(
            "frontline",
            _t("ALB MKD MNE BIH"),
            "Соседи на Балканах: беженцы, этнические связи, риск распространения.",
            "Balkan neighbours: refugees, ethnic ties, risk of spillover.",
        ),
        Exposure(
            "ally",
            _t("ITA HUN DEU TUR USA"),
            "Крупнейшие контингенты KFOR — их военные на месте.",
            "Largest KFOR contingents, with troops on the ground.",
        ),
        Exposure(
            "economic",
            _t("RUS"),
            "Политическая поддержка Сербии; повод для информационных кампаний.",
            "Political backing for Serbia; a theme for influence campaigns.",
        ),
    ),
)

VENEZUELA_GUYANA = Scenario(
    key="venezuela_guyana",
    title_ru="Военные действия Венесуэлы против Гайаны (Эссекибо)",
    title_en="Venezuelan military action against Guyana (Essequibo)",
    event_ru=(
        "Вторжение, удар или захват территории Гайаны вооружёнными силами Венесуэлы, либо "
        "вооружённый захват судов или нефтяных платформ в спорных водах."
    ),
    event_en=(
        "An invasion, strike or seizure of Guyanese territory by Venezuelan forces, or an armed "
        "seizure of ships or oil platforms in disputed waters."
    ),
    polarity=1,
    expert=(0.03, 0.01, 0.1),
    expert_basis_ru=(
        "Венесуэла претендует на Эссекибо — более двух третей территории Гайаны и часть "
        "нефтяного блока Stabroek. После отстранения Мадуро в январе 2026 года и.о. президента "
        "Делси Родригес сохраняет претензию и не признаёт юрисдикцию суда, но действует "
        "дипломатически; решение Международного суда ожидается между ноябрём 2026 и "
        "январём 2027 года — это момент повышенного риска. Оценка GeoIntel: около 3% в год."
    ),
    expert_basis_en=(
        "Venezuela claims Essequibo — over two-thirds of Guyana and part of the Stabroek oil "
        "block. Since Maduro's removal in January 2026, acting President Delcy Rodríguez has "
        "kept the claim and rejects the court's jurisdiction, but by diplomatic means; the ICJ "
        "ruling is expected between November 2026 and January 2027, a moment of higher risk. "
        "GeoIntel judgement: about 3% a year."
    ),
    side_a=_t("VEN"),
    side_b=_t("GUY"),
    market_queries=("Venezuela Guyana", "Essequibo"),
    market_groups=(("venezuela", "essequibo"), ("guyana", "essequibo")),
    market_exclude=("election", "oil price"),
    use_history=False,
    milex=_t("VEN GUY"),
    gpr=_t("VEN"),
    exposures=(
        Exposure("party", _t("VEN GUY"), _PARTIES, _PARTIES_EN),
        Exposure(
            "frontline",
            _t("BRA SUR TTO"),
            "Соседи: Бразилия укрепляла границу в 2023 году; морские границы и миграция.",
            "Neighbours: Brazil reinforced its border in 2023; maritime borders and migration.",
        ),
        Exposure(
            "ally",
            _t("USA GBR"),
            "США — партнёр Гайаны по безопасности; Великобритания — бывшая метрополия, "
            "направляла военный корабль в 2023 году.",
            "The US is Guyana's security partner; the UK, the former colonial power, sent a "
            "warship in 2023.",
        ),
    ),
    warnings=(
        Warning(
            "2026-09-25",
            "The Rio Times",
            "https://riotimesonline.com/essequibo-guyana-ali-unga-venezuela-icj-ruling-2026",
            0,
            "На Генассамблее ООН Гайана призвала Венесуэлу выполнить будущее решение "
            "Международного суда; Венесуэла подтвердила свои «исторические права».",
            "At the UN General Assembly Guyana urged Venezuela to heed the coming ICJ ruling; "
            "Venezuela restated its 'historic rights'.",
        ),
    ),
)

TURKEY_GREECE = Scenario(
    key="turkey_greece",
    title_ru="Вооружённое столкновение Турции и Греции",
    title_en="Armed clash between Turkey and Greece",
    event_ru=(
        "Обмен огнём, таран или удар между вооружёнными силами Турции и Греции в Эгейском или "
        "Восточном Средиземном море с погибшими или потерей корабля либо самолёта."
    ),
    event_en=(
        "An exchange of fire, ramming or strike between Turkish and Greek forces in the Aegean "
        "or Eastern Mediterranean causing deaths or the loss of a ship or aircraft."
    ),
    polarity=1,
    expert=(0.01, 0.003, 0.04),
    expert_basis_ru=(
        "Обе страны в НАТО; последние кризисы — Имиа 1996 года (гибель греческого вертолёта) и "
        "столкновение фрегатов в 2020 году без жертв. В 2026 году напряжённость снова выросла "
        "(навигационные предупреждения, морские парки, учения), но обе стороны избегают огня. "
        "Оценка GeoIntel: около 1% в год."
    ),
    expert_basis_en=(
        "Both are NATO members; the last crises were Imia in 1996 (a Greek helicopter lost) and "
        "a frigate collision in 2020 without casualties. Tension rose again in 2026 (navigation "
        "notices, marine parks, exercises), but both sides avoid shooting. GeoIntel judgement: "
        "about 1% a year."
    ),
    side_a=_t("TUR"),
    side_b=_t("GRC CYP"),
    market_queries=("Turkey Greece",),
    market_groups=(
        ("turkey", "türkiye"),
        ("greece", "greek", "cyprus"),
        ("war", "clash", "attack"),
    ),
    market_exclude=("football", "basketball", "earthquake"),
    milex=_t("TUR GRC"),
    gpr=_t("TUR GRC"),
    exposures=(
        Exposure("party", _t("TUR GRC"), _PARTIES, _PARTIES_EN),
        Exposure(
            "frontline",
            _t("CYP"),
            "Разделённый остров с турецкими войсками на севере; Греция — гарант Кипра.",
            "A divided island with Turkish troops in the north; Greece is a guarantor of Cyprus.",
        ),
        Exposure(
            "economic",
            tuple(c for c in EU if c not in ("GRC", "CYP")),
            "Члены ЕС: статья 42.7 и отношения ЕС с Турцией.",
            "EU members: Article 42.7 and EU relations with Turkey.",
        ),
        Exposure(
            "ally",
            _t("USA"),
            "Союзник обеих сторон по НАТО и главный посредник.",
            "NATO ally of both sides and the main mediator.",
        ),
    ),
)

SAHEL = (
    "MLI",
    "BFA",
    "NER",
    "TCD",
)
SAHEL_COUPS = Scenario(
    key="sahel_coups",
    title_ru="Переворот в одной из стран Сахеля",
    title_en="A coup in one of the Sahel states",
    event_ru=(
        "Успешный военный переворот (власть сменилась и удержана не меньше 7 дней) в Мали, "
        "Буркина-Фасо, Нигере или Чаде."
    ),
    event_en=(
        "A successful military coup (power changes hands and is held for at least 7 days) in "
        "Mali, Burkina Faso, Niger or Chad."
    ),
    polarity=1,
    expert=(0.25, 0.12, 0.45),
    expert_basis_ru=(
        "С 2012 года в этих четырёх странах было восемь успешных переворотов или захватов "
        "власти военными (Мали 2012, 2020, 2021; Буркина-Фасо 2014, 2022 дважды; Чад 2021; "
        "Нигер 2023), то есть около 0,6 в год. После 2023 года все попытки подавлены (в том "
        "числе в Нигере в августе 2026 года при помощи российского «Африканского корпуса»), "
        "поэтому оценка ниже частоты прошлых лет. Оценка GeoIntel: около 25% в год."
    ),
    expert_basis_en=(
        "Since 2012 these four states have seen eight successful coups or military takeovers "
        "(Mali 2012, 2020, 2021; Burkina Faso 2014 and twice in 2022; Chad 2021; Niger 2023), "
        "about 0.6 a year. Since 2023 every attempt has failed (including Niger in August 2026, "
        "with help from Russia's Africa Corps), so the estimate is below the past rate. GeoIntel "
        "judgement: about 25% a year."
    ),
    market_queries=("coup Mali", "coup Burkina Faso", "coup Niger"),
    market_groups=(("coup",), ("mali", "burkina", "niger", "chad", "sahel")),
    market_exclude=("nigeria",),
    use_history=False,
    risk="coup_attempt",
    exposures=(
        Exposure(
            "party",
            SAHEL,
            "Страны сценария: военные режимы (Мали, Буркина-Фасо, Нигер) и Чад.",
            "Scenario countries: military regimes (Mali, Burkina Faso, Niger) and Chad.",
        ),
        Exposure(
            "frontline",
            _t("BEN TGO GHA CIV SEN MRT DZA NGA"),
            "Соседи: распространение джихадистских группировок и беженцы.",
            "Neighbours: spread of jihadist groups and refugees.",
        ),
        Exposure(
            "economic",
            _t("RUS FRA"),
            "Россия охраняет режимы («Африканский корпус»); Франция ушла из региона в 2022–2023 "
            "годах.",
            "Russia protects the regimes (Africa Corps); France left the region in 2022–2023.",
        ),
    ),
    warnings=(
        Warning(
            "2026-08-30",
            "Al Jazeera",
            "https://www.aljazeera.com/amp/news/2026/8/30/nigers-military-led-government-says-it-contained-mutiny-what-next",
            1,
            "Военные власти Нигера подавили мятеж на базе 101 в Ниамее; Минобороны России "
            "подтвердило участие своих сил.",
            "Niger's military government put down a mutiny at Base 101 in Niamey; Russia's "
            "defence ministry confirmed its forces took part.",
        ),
    ),
)

US_GUARANTEE = Scenario(
    key="us_guarantee",
    title_ru="Ослабление гарантий безопасности США в Европе",
    title_en="Weakening of US security guarantees in Europe",
    event_ru=(
        "США официально объявляют о выходе из НАТО, либо президент США публично отказывается "
        "защищать союзника по статье 5, либо войска США в Европе сокращаются ниже 76 000 — "
        "минимума, установленного Конгрессом в законе об оборонном бюджете на 2026 год."
    ),
    event_en=(
        "The US formally announces withdrawal from NATO, or the US President publicly refuses "
        "to defend an ally under Article 5, or US troops in Europe fall below 76,000 — the floor "
        "set by Congress in the 2026 defence authorisation act."
    ),
    polarity=1,
    expert=(0.1, 0.04, 0.25),
    expert_basis_ru=(
        "В мае 2026 года США объявили о выводе 5000 военных из Германии и отменили размещение "
        "ракет дальнего действия; президент ставил под сомнение статью 5 после разногласий из-за "
        "войны с Ираном. Конгресс законом ограничил сокращение войск, а глава военного комитета "
        "НАТО не ждёт новых сокращений. Оценка GeoIntel: около 10% в год."
    ),
    expert_basis_en=(
        "In May 2026 the US announced the withdrawal of 5,000 troops from Germany and cancelled "
        "a long-range missile deployment; the President questioned Article 5 after disputes over "
        "the Iran war. Congress has limited troop cuts by law, and NATO's top military officer "
        "expects no further drawdowns. GeoIntel judgement: about 10% a year."
    ),
    market_queries=("US withdraw NATO", "leave NATO"),
    market_groups=(("nato",), ("withdraw", "leave", "exit", "quit")),
    market_exclude=("ukraine join", "sweden", "finland"),
    metaculus_queries=("United States NATO withdrawal",),
    use_history=False,
    use_signs=False,  # warning signs near Russia say nothing about US policy
    exposures=(
        Exposure(
            "party",
            _t("USA"),
            "Решение принимают США.",
            "The decision is the United States'.",
        ),
        Exposure(
            "frontline",
            _t("EST LVA LTU POL FIN ROU DEU"),
            "Страны восточного фланга и Германия, где стоят основные войска США.",
            "Eastern-flank states and Germany, where most US troops are based.",
        ),
        Exposure(
            "ally",
            tuple(c for c in NATO if c not in _t("USA EST LVA LTU POL FIN ROU DEU")),
            "Остальные союзники по НАТО: сдерживание держится на ядерном зонтике США.",
            "Other NATO allies: deterrence rests on the US nuclear umbrella.",
        ),
        Exposure(
            "economic",
            _t("UKR"),
            "Поставки оружия и разведданных.",
            "Supplies of weapons and intelligence.",
        ),
    ),
    warnings=(
        Warning(
            "2026-05-01",
            "EU Institute for Security Studies",
            "https://www.iss.europa.eu/node/3835",
            1,
            "Пентагон подтвердил вывод около 5000 военных из Германии; общая численность войск "
            "США в Европе остаётся выше 76 000 — минимума, заданного Конгрессом.",
            "The Pentagon confirmed the withdrawal of about 5,000 troops from Germany; total US "
            "forces in Europe remain above the 76,000 floor set by Congress.",
        ),
    ),
)

EXTRA: tuple[Scenario, ...] = (
    MOLDOVA,
    BELARUS,
    SERBIA_KOSOVO,
    VENEZUELA_GUYANA,
    TURKEY_GREECE,
    SAHEL_COUPS,
    US_GUARANTEE,
)
