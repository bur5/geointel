from geointel.risk.sources import protests, vdem_mob


def _data():
    # Two countries; A has big protests whenever the score is high.
    score = {"AAA": {}, "BBB": {}}
    truth = {"AAA": set(), "BBB": set()}
    for year in range(2000, 2026):
        score["AAA"][year] = 2.0 if year % 2 else -1.0
        score["BBB"][year] = -1.5
        if year % 2 and year <= 2020:
            truth["AAA"].add(year)
    return score, truth


def test_calibration_matches_rate_and_checks_agreement():
    score, truth = _data()
    out = vdem_mob.calibrate(score, truth, ["AAA", "BBB"])
    assert out["usable"] and out["threshold"] == 2.0
    assert out["check"]["accuracy"] == 1.0 and out["check"]["kappa"] == 1.0


def test_unusable_when_stand_in_disagrees():
    score, truth = _data()
    flipped = {"AAA": {y: -s for y, s in score["AAA"].items()}, "BBB": score["BBB"]}
    flipped["AAA"].update({y: score["AAA"][y] for y in range(2000, 2016)})
    out = vdem_mob.calibrate(flipped, truth, ["AAA", "BBB"])
    assert not out["usable"]


def test_extend_adds_only_years_after_mass_mobilization():
    score, truth = _data()
    payload = {"last": 2020, "covered": ["AAA", "BBB"], "years": {"AAA": sorted(truth["AAA"])}}
    out = vdem_mob.extend(payload, score, 2.0)
    assert out["last"] == 2025 and out["proxy_from"] == 2021
    assert [y for y in out["years"]["AAA"] if y > 2020] == [2021, 2023, 2025]
    assert out["years"]["AAA"][:3] == [2001, 2003, 2005]
    history = protests.history(out)
    assert history.end_year == 2025 and "V-Dem" in history.source
