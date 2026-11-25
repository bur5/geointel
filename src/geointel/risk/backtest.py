"""Backtest: what the warning-sign method would have shown before Russia's full-scale
invasion of Ukraine on 24 February 2022.

The timeline lists publicly reported signs with the date they became public. The same sign
catalogue and likelihood ratios as the live site are used. Caveat shown on the site: the
catalogue was written in 2026, knowing the outcome, so this is a consistency check of the
method, not proof of foresight. April 2021 is kept as a false alarm: the build-up then did not
lead to an invasion.
"""

from datetime import date, timedelta

from geointel.risk.warning_signs import INTERSTATE, Entry, active_entries, adjust, combine

EVENT_DATE = "2022-02-24"
BASE_ANNUAL = 0.05  # prior for a new large-scale Russian offensive into Ukraine, 2014–2021 war

UKRAINE_2022: tuple[Entry, ...] = (
    Entry(
        "2021-03-30",
        "UKR",
        "posture",
        "Около 100 тыс. российских военных у границ Украины и в Крыму.",
        "About 100,000 Russian troops near Ukraine's borders and in Crimea.",
        "Media and Ukrainian government reports",
        "",
        "RUS",
        until="2021-04-22",
    ),
    Entry(
        "2021-04-22",
        "UKR",
        "deescalation",
        "Объявлен отвод войск; часть техники осталась у границы.",
        "Pull-back announced; part of the equipment left near the border.",
        "Russian Ministry of Defence",
        "",
        "RUS",
        strength=0.5,
        until="2021-07-31",
    ),
    Entry(
        "2021-04-22",
        "UKR",
        "posture",
        "Техника, оставленная у границы после апрельских учений.",
        "Equipment left near the border after the April exercises.",
        "OSINT and media reports",
        "",
        "RUS",
        strength=0.5,
        until=EVENT_DATE,
    ),
    Entry(
        "2021-07-12",
        "UKR",
        "rhetoric",
        "Статья Путина «Об историческом единстве русских и украинцев».",
        "Putin's article 'On the Historical Unity of Russians and Ukrainians'.",
        "Kremlin",
        "",
        "RUS",
        until=EVENT_DATE,
    ),
    Entry(
        "2021-10-30",
        "UKR",
        "posture",
        "Новая переброска войск к границе, подтверждённая спутниковыми снимками.",
        "New troop movements to the border confirmed by satellite imagery.",
        "Washington Post; commercial satellite imagery",
        "",
        "RUS",
        until=EVENT_DATE,
    ),
    Entry(
        "2021-11-15",
        "UKR",
        "intel_warning",
        "США предупреждают союзников о возможном вторжении.",
        "The US warns allies of a possible invasion.",
        "Media reports of US briefings",
        "",
        "RUS",
        until=EVENT_DATE,
    ),
    Entry(
        "2021-12-03",
        "UKR",
        "intel_warning",
        "Разведка США: план наступления силами около 175 тыс. в начале 2022 года.",
        "US intelligence: plan for an offensive with about 175,000 troops in early 2022.",
        "Washington Post",
        "",
        "RUS",
        strength=2.0,
        until=EVENT_DATE,
    ),
    Entry(
        "2021-12-17",
        "UKR",
        "rhetoric",
        "Россия публикует проекты договоров с требованиями к США и НАТО.",
        "Russia publishes draft treaties with demands on the US and NATO.",
        "Russian Foreign Ministry",
        "",
        "RUS",
        strength=1.5,
        until=EVENT_DATE,
    ),
    Entry(
        "2022-01-14",
        "UKR",
        "cyber",
        "Атака на сайты правительства Украины, вредонос WhisperGate стирает данные.",
        "Attack on Ukrainian government sites; WhisperGate malware wipes data.",
        "Microsoft; Ukrainian government",
        "",
        "RUS",
        until=EVENT_DATE,
    ),
    Entry(
        "2022-01-17",
        "UKR",
        "posture",
        "Российские войска прибывают в Беларусь на учения «Союзная решимость».",
        "Russian troops arrive in Belarus for the 'Allied Resolve' exercises.",
        "Belarusian and Russian defence ministries",
        "",
        "RUS",
        strength=1.5,
        until=EVENT_DATE,
    ),
    Entry(
        "2022-01-23",
        "UKR",
        "diplomatic",
        "США велят семьям сотрудников посольства в Киеве уехать.",
        "The US orders families of embassy staff in Kyiv to leave.",
        "US State Department",
        "",
        "RUS",
        strength=0.5,
        until=EVENT_DATE,
    ),
    Entry(
        "2022-01-28",
        "UKR",
        "medical",
        "Россия перебросила запасы крови к границе с Украиной.",
        "Russia moved blood supplies near the Ukrainian border.",
        "Reuters, citing US officials",
        "",
        "RUS",
        until=EVENT_DATE,
    ),
    Entry(
        "2022-02-12",
        "UKR",
        "diplomatic",
        "Большинство сотрудников посольства США покидают Киев; многие страны призывают "
        "граждан уехать.",
        "Most US embassy staff leave Kyiv; many countries tell citizens to leave.",
        "US State Department and other governments",
        "",
        "RUS",
        until=EVENT_DATE,
    ),
    Entry(
        "2022-02-18",
        "UKR",
        "staged",
        "Видео «эвакуации» из Донбасса записаны за два дня до публикации.",
        "Donbas 'evacuation' videos were recorded two days before publication.",
        "Bellingcat (file metadata)",
        "",
        "RUS",
        until=EVENT_DATE,
    ),
    Entry(
        "2022-02-20",
        "UKR",
        "masking",
        "На технике у границы появляются новые опознавательные знаки (буква «Z»).",
        "New markings (the letter 'Z') appear on vehicles near the border.",
        "Social media video, approximate date",
        "",
        "RUS",
        until=EVENT_DATE,
    ),
    Entry(
        "2022-02-21",
        "UKR",
        "legal",
        "Россия признаёт «ДНР» и «ЛНР».",
        "Russia recognises the 'DNR' and 'LNR'.",
        "Kremlin",
        "",
        "RUS",
        until=EVENT_DATE,
    ),
)


def _signs_at(day: date) -> list[dict]:
    return [
        {"key": e.sign, "status": "active", "strength": e.strength}
        for e in active_entries(UKRAINE_2022, day)
    ]


def run(start: str = "2021-01-01", end: str = "2022-02-23") -> dict:
    day, stop = date.fromisoformat(start), date.fromisoformat(end)
    p1m = 1 - (1 - BASE_ANNUAL) ** (1 / 12)
    points = []
    while day <= stop:
        combined = combine(_signs_at(day), INTERSTATE)
        points.append(
            {
                "date": day.isoformat(),
                "factor": combined["factor"],
                "p1m": round(adjust(p1m, combined["factor"]), 4),
                "p1y": round(adjust(BASE_ANNUAL, combined["factor"]), 4),
                "signs": combined["signs"],
            }
        )
        day += timedelta(days=7)
    if points[-1]["date"] != end:
        last = date.fromisoformat(end)
        combined = combine(_signs_at(last), INTERSTATE)
        points.append(
            {
                "date": end,
                "factor": combined["factor"],
                "p1m": round(adjust(p1m, combined["factor"]), 4),
                "p1y": round(adjust(BASE_ANNUAL, combined["factor"]), 4),
                "signs": combined["signs"],
            }
        )
    return {
        "key": "ukraine_2022",
        "title_ru": "Вторжение России в Украину, 24 февраля 2022",
        "title_en": "Russia's invasion of Ukraine, 24 February 2022",
        "event_date": EVENT_DATE,
        "base_annual": BASE_ANNUAL,
        "points": points,
        "timeline": [
            {
                "date": e.date,
                "sign": e.sign,
                "summary_ru": e.summary_ru,
                "summary_en": e.summary_en,
                "source": e.source,
                "strength": e.strength,
            }
            for e in UKRAINE_2022
        ],
    }
