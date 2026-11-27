"""How each forecast is resolved: who decides whether it came true, and the date window.

The threshold of every scenario is in its definition (``event_ru`` / ``event_en``); the
threshold of every country event type is in ``taxonomy.EVENT_TYPES``. This module adds the
missing parts: the deciding source and the window (forecast date → date + horizon).
"""

from datetime import date, timedelta

WIRES_RU = "не менее двух из Reuters, AP, AFP"
WIRES_EN = "at least two of Reuters, AP, AFP"

SOURCES: dict[str, tuple[str, str]] = {
    "russia_nato": (
        f"Заявление правительства пострадавшей страны или НАТО, подтверждённое {WIRES_RU}.",
        f"A statement by the victim government or NATO, confirmed by {WIRES_EN}.",
    ),
    "russia_nato_war": (
        "Официальные заявления НАТО о применении статьи 5 или о боях; UCDP Candidate.",
        "Official NATO statements on Article 5 or on fighting; UCDP Candidate.",
    ),
    "ukraine_ceasefire": (
        f"Объявление обеих сторон и отсутствие боёв по сводкам UCDP Candidate и {WIRES_RU} "
        "в течение 30 дней.",
        f"Announcement by both sides and no fighting per UCDP Candidate and {WIRES_EN} for "
        "30 days.",
    ),
    "china_taiwan": (
        f"Министерство обороны Тайваня или правительство США, подтверждено {WIRES_RU}.",
        f"Taiwan's defence ministry or the US government, confirmed by {WIRES_EN}.",
    ),
    "iran_strikes": (
        f"Признание удара хотя бы одной стороной, подтверждённое {WIRES_RU}.",
        f"Acknowledgement of a strike by at least one side, confirmed by {WIRES_EN}.",
    ),
    "india_pakistan": (
        f"Признание хотя бы одной стороной (армия, МИД), подтверждено {WIRES_RU}.",
        f"Acknowledgement by at least one side (army, foreign ministry), confirmed by {WIRES_EN}.",
    ),
    "korea": (
        f"Объединённый комитет начальников штабов Южной Кореи, подтверждено {WIRES_RU}.",
        f"South Korea's Joint Chiefs of Staff, confirmed by {WIRES_EN}.",
    ),
    "moldova_transnistria": (
        f"Правительство Молдовы или ОБСЕ, подтверждено {WIRES_RU}.",
        f"The government of Moldova or the OSCE, confirmed by {WIRES_EN}.",
    ),
    "belarus_front": (
        f"Генштаб Украины или НАТО, подтверждено {WIRES_RU}; UCDP Candidate.",
        f"Ukraine's General Staff or NATO, confirmed by {WIRES_EN}; UCDP Candidate.",
    ),
    "serbia_kosovo": (
        f"KFOR, полиция Косово или правительство Сербии, подтверждено {WIRES_RU}.",
        f"KFOR, Kosovo police or the government of Serbia, confirmed by {WIRES_EN}.",
    ),
    "venezuela_guyana": (
        f"Правительство Гайаны, подтверждено {WIRES_RU}.",
        f"The government of Guyana, confirmed by {WIRES_EN}.",
    ),
    "turkey_greece": (
        f"Министерство обороны Греции или Турции, подтверждено {WIRES_RU}.",
        f"The Greek or Turkish defence ministry, confirmed by {WIRES_EN}.",
    ),
    "sahel_coups": (
        "Cline Center Coup Data или Powell & Thyne; до их обновления — заявление военных о "
        f"захвате власти, подтверждённое {WIRES_RU}, и 7 дней удержания власти.",
        "Cline Center Coup Data or Powell & Thyne; until they update, a military statement "
        f"of seizing power confirmed by {WIRES_EN} and held for 7 days.",
    ),
    "us_guarantee": (
        "Официальные документы правительства США (Белый дом, Пентагон, Конгресс).",
        "Official US government documents (White House, Pentagon, Congress).",
    ),
    "us_iran": (
        f"Министерство обороны США (CENTCOM), подтверждено {WIRES_RU}.",
        f"The US Department of Defense (CENTCOM), confirmed by {WIRES_EN}.",
    ),
    "armenia_azerbaijan": (
        f"Министерство обороны Армении или Азербайджана, подтверждено {WIRES_RU}.",
        f"The Armenian or Azerbaijani defence ministry, confirmed by {WIRES_EN}.",
    ),
    "israel_hezbollah": (
        f"Армия обороны Израиля или Минздрав Ливана, подтверждено {WIRES_RU}.",
        f"The Israel Defense Forces or Lebanon's health ministry, confirmed by {WIRES_EN}.",
    ),
    "hormuz_reopening": (
        "Данные о проходе судов (UKMTO, Lloyd's List, JMIC) за 30 дней подряд.",
        "Ship transit data (UKMTO, Lloyd's List, JMIC) for 30 days in a row.",
    ),
    "georgia_crisis": (
        f"Официальные решения парламента или правительства Грузии, подтверждено {WIRES_RU}.",
        f"Official decisions of Georgia's parliament or government, confirmed by {WIRES_EN}.",
    ),
    "iraq_strikes": (
        f"Признание хотя бы одной стороной или правительство Ирака, подтверждено {WIRES_RU}.",
        f"Acknowledgement by at least one side or Iraq's government, confirmed by {WIRES_EN}.",
    ),
}

HORIZON_DAYS = {"1m": 30, "1y": 365, "5y": 5 * 365 + 1, "10y": 10 * 365 + 2}


def window(start: date) -> dict[str, dict[str, str]]:
    return {
        h: {"from": start.isoformat(), "to": (start + timedelta(days=d)).isoformat()}
        for h, d in HORIZON_DAYS.items()
    }


def scenario_resolution(key: str, start: date) -> dict:
    ru, en = SOURCES[key]
    return {"source_ru": ru, "source_en": en, "window": window(start)}
