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


def test_weather_emergency_is_not_political():
    from geointel.risk.sources import newswire

    batch = [
        {
            "title": "New York declares state of emergency over winter storm",
            "date": "2026-11-26",
            "url": "u",
            "domain": "d",
        }
    ]
    reply = (
        '[{"i": 0, "country": "USA", "sign": "emergency_rule", '
        '"quote": "declares state of emergency", "country_in_text": true}]'
    )
    assert newswire.parse_reply(reply, batch) == []


def test_speculation_is_not_an_event():
    from datetime import date

    news = [
        {
            "date": "2026-11-25",
            "country": "SEN",
            "sign": "leader_exit",
            "domain": "a",
            "url": "1",
            "headline": "Sonko says president could resign or dissolve parliament",
        },
        {
            "date": "2026-11-25",
            "country": "SEN",
            "sign": "snap_election",
            "domain": "b",
            "url": "2",
            "headline": "Speaker calls for dissolution of parliament",
        },
        {
            "date": "2026-11-25",
            "country": "PER",
            "sign": "leader_exit",
            "domain": "c",
            "url": "3",
            "headline": "Peru president removed by Congress",
        },
        {
            "date": "2026-11-25",
            "country": "USA",
            "sign": "emergency_rule",
            "domain": "d",
            "url": "4",
            "headline": "New York declares emergency over storm",
        },
    ]
    out = political_crisis_now(news, date(2026, 11, 27))
    assert set(out) == {"PER"}


def test_speculation_in_other_languages():
    from geointel.risk.sources.newswire import rejected_by_rules

    assert rejected_by_rules(
        "leader_exit", "Sénégal : Ousmane Sonko évoque la démission de Diomaye Faye"
    )
    assert rejected_by_rules("snap_election", "Премьер призвал к досрочным выборам")
    assert not rejected_by_rules("leader_exit", "Le Premier ministre a démissionné")


def test_discussed_status_is_dropped():
    from geointel.risk.sources import newswire

    batch = [
        {
            "title": "Opposition demands snap election in Georgia",
            "date": "2026-11-26",
            "url": "u",
            "domain": "d",
        }
    ]
    reply = (
        '[{"i": 0, "country": "GEO", "sign": "snap_election", "quote": "snap election", '
        '"country_in_text": true, "status": "discussed"}]'
    )
    assert newswire.parse_reply(reply, batch) == []
