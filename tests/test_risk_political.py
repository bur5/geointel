from datetime import date

from geointel.risk.__main__ import political_crisis_now


def test_political_crisis_detection_counts_outlets_and_window():
    news = [
        {
            "date": "2026-11-20",
            "country": "FRA",
            "sign": "leader_exit",
            "domain": "a.com",
            "url": "1",
        },
        {
            "date": "2026-11-21",
            "country": "FRA",
            "sign": "snap_election",
            "domain": "b.com",
            "url": "2",
        },
        {
            "date": "2026-11-21",
            "country": "PER",
            "sign": "impeachment",
            "domain": "c.com",
            "url": "3",
        },
        {
            "date": "2026-08-01",
            "country": "DEU",
            "sign": "leader_exit",
            "domain": "d.com",
            "url": "4",
        },
        {"date": "2026-11-21", "country": "ITA", "sign": "unrest", "domain": "e.com", "url": "5"},
        {
            "date": "2026-11-21",
            "country": "RUS",
            "sign": "elite_split",
            "domain": "f.com",
            "url": "6",
        },
    ]
    out = political_crisis_now(news, date(2026, 11, 27))
    assert set(out) == {"FRA", "PER"}
    assert out["FRA"]["confirmed"] and out["FRA"]["outlets"] == 2
    assert not out["PER"]["confirmed"]
