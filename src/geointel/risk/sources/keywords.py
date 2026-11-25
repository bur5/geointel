"""Keyword classification of short texts (Telegram posts, news headlines) without a language model.

Each text is matched against phrase stems in Russian, Ukrainian and English and assigned to zero
or more categories; the countries it mentions are found from a small name dictionary. Counts per
country, category and day are compared with the country's own baseline, so a word that is always
frequent (for example "мобилизация" in Ukrainian channels during the war) only counts when its
share jumps. Texts are untrusted data and are only counted, never acted upon.

This is a weak, automated signal. With a Claude API key the same texts are also classified by a
model, which understands negation, irony and old news; keywords do not.
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping

# category -> phrase stems (matched at a word start, case-insensitive)
CATEGORIES: dict[str, tuple[str, ...]] = {
    "military": (
        # troops, equipment, mobilisation, medical preparation
        "эшелон",
        "колонн техник",
        "колонна техник",
        "переброск",
        "стягива",
        "сосредоточени",
        "мобилизац",
        "повестк",
        "военкомат",
        "резервист",
        "призыв запас",
        "военные сборы",
        "полевой госпитал",
        "полевые госпитал",
        "сдать кров",
        "запас крови",
        "донорск",
        "ешелон",
        "колона техн",
        "перекидан",
        "мобілізац",
        "повістк",
        "тцк",
        "резервіст",
        "польовий госпітал",
        "донор",
        "troop build",
        "troops massed",
        "massing troops",
        "military buildup",
        "military build-up",
        "convoy",
        "redeploy",
        "mobilization",
        "mobilisation",
        "reservist",
        "call-up",
        "field hospital",
        "blood suppl",
    ),
    "emergency": (
        # evacuations, closures, martial law: last-step signs
        "эвакуац",
        "военное положение",
        "режим кто",
        "закрыт воздушн",
        "закрытие воздушн",
        "закрытие границ",
        "закрыл границ",
        "покинуть страну",
        "покинуть территорию",
        "евакуац",
        "воєнний стан",
        "воєнного стану",
        "закриття кордон",
        "закрито повітрян",
        "evacuat",
        "martial law",
        "airspace closed",
        "closes airspace",
        "closed its airspace",
        "border closed",
        "closes border",
        "ordered departure",
        "leave the country",
    ),
    "coup": (
        "переворот",
        "мятеж",
        "путч",
        "хунт",
        "военные захватили",
        "заколот",
        "путч",
        "coup",
        "mutiny",
        "junta",
        "military takeover",
        "seized power",
    ),
    "unrest": (
        "протест",
        "митинг",
        "забастовк",
        "беспорядк",
        "разгон",
        "демонстрант",
        "стачк",
        "мітинг",
        "страйк",
        "заворушен",
        "protest",
        "demonstrator",
        "riot",
        "general strike",
        "nationwide strike",
        "unrest",
    ),
    "hybrid": (
        "диверси",
        "поджог",
        "саботаж",
        "кибератак",
        "ddos",
        "повреждение кабел",
        "дрон над",
        "нарушил воздушн",
        "нарушение воздушн",
        "кібератак",
        "диверсі",
        "підпал",
        "sabotage",
        "arson",
        "cyberattack",
        "cyber attack",
        "undersea cable",
        "drone incursion",
        "airspace violation",
        "violated airspace",
    ),
}

# Russian / Ukrainian / English name stems -> ISO3 (countries the service watches closely)
COUNTRY_NAMES: dict[str, str] = {
    "эстон": "EST",
    "естон": "EST",
    "estonia": "EST",
    "нарв": "EST",
    "латви": "LVA",
    "латві": "LVA",
    "latvia": "LVA",
    "рига": "LVA",
    "riga": "LVA",
    "литв": "LTU",
    "lithuania": "LTU",
    "вильнюс": "LTU",
    "вільнюс": "LTU",
    "vilnius": "LTU",
    "польш": "POL",
    "польщ": "POL",
    "poland": "POL",
    "polish": "POL",
    "варшав": "POL",
    "финлянд": "FIN",
    "фінлянд": "FIN",
    "finland": "FIN",
    "finnish": "FIN",
    "норвеги": "NOR",
    "норвегі": "NOR",
    "norway": "NOR",
    "швеци": "SWE",
    "швеці": "SWE",
    "sweden": "SWE",
    "swedish": "SWE",
    "дани": "DNK",
    "данi": "DNK",
    "denmark": "DNK",
    "danish": "DNK",
    "германи": "DEU",
    "німеччин": "DEU",
    "germany": "DEU",
    "german": "DEU",
    "белорус": "BLR",
    "беларус": "BLR",
    "білорус": "BLR",
    "belarus": "BLR",
    "минск": "BLR",
    "калининград": "RUS",
    "калінінград": "RUS",
    "kaliningrad": "RUS",
    "молдав": "MDA",
    "молдов": "MDA",
    "приднестров": "MDA",
    "придністров": "MDA",
    "moldova": "MDA",
    "transnistria": "MDA",
    "румын": "ROU",
    "румун": "ROU",
    "romania": "ROU",
    "грузия": "GEO",
    "грузии": "GEO",
    "грузию": "GEO",
    "грузинск": "GEO",
    "грузі": "GEO",
    "georgia": "GEO",
    "тбилис": "GEO",
    "армени": "ARM",
    "вірмен": "ARM",
    "armenia": "ARM",
    "азербайджан": "AZE",
    "azerbaijan": "AZE",
    "серби": "SRB",
    "сербі": "SRB",
    "serbia": "SRB",
    "косов": "XKX",
    "kosovo": "XKX",
    "иран": "IRN",
    "іран": "IRN",
    "iran": "IRN",
    "тегеран": "IRN",
    "израил": "ISR",
    "ізраїл": "ISR",
    "israel": "ISR",
    "ливан": "LBN",
    "ліван": "LBN",
    "lebanon": "LBN",
    "хезболл": "LBN",
    "hezbollah": "LBN",
    "ирак": "IRQ",
    "ірак": "IRQ",
    "iraq": "IRQ",
    "сири": "SYR",
    "сирі": "SYR",
    "syria": "SYR",
    "йемен": "YEM",
    "ємен": "YEM",
    "yemen": "YEM",
    "хусит": "YEM",
    "houthi": "YEM",
    "турци": "TUR",
    "туреч": "TUR",
    "turkey": "TUR",
    "türkiye": "TUR",
    "грец": "GRC",
    "греці": "GRC",
    "greece": "GRC",
    "казахстан": "KAZ",
    "kazakhstan": "KAZ",
    "украин": "UKR",
    "україн": "UKR",
    "ukrain": "UKR",
    "киев": "UKR",
    "київ": "UKR",
    "росси": "RUS",
    "росі": "RUS",
    "russia": "RUS",
    "kremlin": "RUS",
    "кремл": "RUS",
    "мали": "MLI",
    "mali": "MLI",
    "буркина": "BFA",
    "буркіна": "BFA",
    "burkina": "BFA",
    "нигер": "NER",
    "нігер": "NER",
    "niger": "NER",
    "чад": "TCD",
    "chad": "TCD",
    "венесуэл": "VEN",
    "венесуел": "VEN",
    "venezuela": "VEN",
    "гайан": "GUY",
    "guyana": "GUY",
}


def _compile(stems: Iterable[str]) -> re.Pattern:
    escaped = sorted({re.escape(s) for s in stems}, key=len, reverse=True)
    return re.compile(r"(?<![\w])(?:" + "|".join(escaped) + ")", re.IGNORECASE | re.UNICODE)


_PATTERNS = {k: _compile(v) for k, v in CATEGORIES.items()}
# Country stems may take an ending of at most four letters ("Эстонии", "Latvia's"); a few short
# names that are also ordinary words must match exactly.
_EXACT = {"мали", "mali", "чад", "chad", "рига", "riga", "нарв"}
_NAMES = re.compile(
    r"(?<![\w])("
    + "|".join(sorted((re.escape(s) for s in COUNTRY_NAMES), key=len, reverse=True))
    + r")(\w{0,4})(?![\w])",
    re.IGNORECASE | re.UNICODE,
)
_NOT_NIGER = ("nigeria", "нигери", "нігері")


def categories(text: str) -> set[str]:
    return {k for k, p in _PATTERNS.items() if p.search(text)}


def countries(text: str) -> set[str]:
    found = set()
    for match in _NAMES.finditer(text):
        stem, ending = match.group(1).lower(), match.group(2).lower()
        if stem in _EXACT and ending not in ("", "е", "а", "у", "ы", "и", "ой", "ой"):
            continue
        if stem in ("мали", "чад") and not match.group(1)[0].isupper():
            continue
        if (stem + ending).startswith(_NOT_NIGER):
            continue
        code = COUNTRY_NAMES.get(stem)
        if code:
            found.add(code)
    return found


def tally(
    texts: Iterable[Mapping], default_countries: Iterable[str] = ()
) -> dict[str, dict[str, dict[str, int]]]:
    """Counts per country and day: {"ISO3": {"YYYY-MM-DD": {"n": texts, <category>: hits}}}.

    Each text counts for the countries it names, or for ``default_countries`` if it names none.
    ``texts`` are dicts with ``date`` and ``text`` (original case kept for name matching).
    """
    out: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
    defaults = tuple(default_countries)
    for item in texts:
        day, text = str(item.get("date") or "")[:10], str(item.get("text") or "")
        if len(day) != 10 or not text:
            continue
        where = countries(text) or set(defaults)
        cats = categories(text)
        for code in where:
            cell = out[code][day]
            cell["n"] = cell.get("n", 0) + 1
            for cat in cats:
                cell[cat] = cell.get(cat, 0) + 1
    return {c: {d: dict(v) for d, v in days.items()} for c, days in out.items()}


def merge_tallies(*tallies: Mapping[str, Mapping[str, Mapping[str, int]]]) -> dict:
    merged: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
    for t in tallies:
        for code, days in t.items():
            for day, cell in days.items():
                target = merged[code][day]
                for k, v in cell.items():
                    target[k] = target.get(k, 0) + v
    return {c: {d: dict(v) for d, v in days.items()} for c, days in merged.items()}


def share_series(days: Mapping[str, Mapping[str, int]], category: str, min_n: int = 5) -> dict:
    """Daily share of texts in a category (days with too few texts are left out, not zero)."""
    return {
        d: cell.get(category, 0) / cell["n"]
        for d, cell in days.items()
        if cell.get("n", 0) >= min_n
    }
