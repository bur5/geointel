from geointel.risk.sources import protest_history as ph


def _resolve(name):
    return {"Kenya": "KEN", "Chile": "CHL", "Iran": "IRN"}.get(name.strip())


def test_size_parsing():
    assert ph.size_at_least("10,000+") is True
    assert ph.size_at_least("50,000-100,000") is True
    assert ph.size_at_least("5,000") is False
    assert ph.size_at_least("1 million") is True
    assert ph.size_at_least("Thousands") is None


def test_carnegie_rows_to_years_and_check():
    rows = [
        ["Country", "Start Date", "Size", "Motivation"],
        ["Kenya", "July 2018", "15,000+", "taxes"],
        ["Chile", "2019-10-18", "1 million", "fares"],
        ["Iran", "2019", "unknown", "fuel"],
    ]
    events = ph.carnegie_events(rows, _resolve)
    years = ph.big_years(events)
    assert years == {"CHL": [2019], "KEN": [2018]}
    out = ph.check(years, {"CHL": [2019], "KEN": [2018]}, ["CHL", "KEN", "IRN"], (2017, 2020))
    assert out["accuracy"] == 1.0 and out["usable"]


def test_label_needs_quote_in_text_and_hand_check():
    text = "Tens of thousands marched in Nairobi on 7 July against the finance bill."
    reply = (
        '{"country": "Kenya", "year": 2024, "against_government": true, '
        '"participants": "over_10000", "quote": "Tens of thousands marched in Nairobi"}'
    )
    item = ph.parse_label(reply, text, _resolve)
    assert item["big"] and item["iso3"] == "KEN"
    fake = reply.replace("Tens of thousands marched in Nairobi", "A million people")
    assert not ph.parse_label(fake, text, _resolve)["big"]
    history = {
        "check": {"usable": True},
        "hand_check": {"n": 100, "errors": 8},
        "years": {},
        "last_year": 2025,
    }
    assert ph.usable(history)
    assert not ph.usable({**history, "hand_check": {"n": 100, "errors": 12}})
    est = ph.estimate_cost([text] * 10)
    assert est["articles"] == 10 and est["usd"] >= 0


def test_extend_adds_only_later_years():
    mm = {"last": 2020, "covered": ["KEN"], "years": {"KEN": [2018]}}
    out = ph.extend(
        mm, {"last_year": 2025, "years": {"KEN": [2019, 2024], "XXX": [2024]}, "source": "test"}
    )
    assert out["years"]["KEN"] == [2018, 2024] and out["last"] == 2025 and "XXX" not in out["years"]
