import random

from geointel.risk import trained
from geointel.risk.model import TypeHistory
from geointel.risk.taxonomy import EventType


def test_logistic_recovers_direction():
    rng = random.Random(1)
    x, y = [], []
    for _ in range(600):
        a = rng.gauss(0, 1)
        x.append([1.0, a])
        y.append(int(rng.random() < 1 / (1 + 2.718 ** -(2 * a - 1))))
    model = trained.fit_logistic(x, y)
    assert model["beta"][1] > 0.5
    assert trained.predict(model, [1.0, 2.0]) > trained.predict(model, [1.0, -2.0])


def test_features_use_only_the_past():
    events = {"AAA": frozenset({2000, 2010}), "BBB": frozenset({2009})}
    row = trained.features(
        "AAA", 2010, events, {"AAA": {"BBB"}}, {"AAA": {2009: 0, 2006: 1}}, {}, {}
    )
    assert row["events_5y"] == 0.0  # 2010 itself is not visible
    assert row["neighbour_share"] == 1.0
    assert row["regime_0"] == 1.0 and row["regime_change_3y"] == 1.0


def test_topo_neighbours():
    topo = {
        "objects": {
            "countries": {
                "geometries": [
                    {"id": "1", "arcs": [[0, 1]]},
                    {"id": "2", "arcs": [[~1, 2]]},
                    {"id": "3", "arcs": [[3]]},
                ]
            }
        }
    }
    nb = trained.topo_neighbours(topo, {"001": "AAA", "002": "BBB", "003": "CCC"})
    assert nb["AAA"] == {"BBB"} and not nb.get("CCC")


def test_run_type_end_to_end():
    rng = random.Random(3)
    countries = {f"C{i:02d}": None for i in range(40)}
    regimes = {
        c: {y: (0 if i < 15 else 3) for y in range(1990, 2026)} for i, c in enumerate(countries)
    }
    events = {
        c: frozenset(y for y in range(1995, 2026) if rng.random() < (0.12 if i < 15 else 0.01))
        for i, c in enumerate(countries)
    }
    history = TypeHistory(EventType.COUP_ATTEMPT, "t", 1990, 2025, events)
    result = trained.run_type("coup_attempt", history, countries, {}, regimes, {}, {}, False, 2025)
    assert result["test_events"] > 0 and "bss_vs_base" in result
    assert set(result["predictions"]) == set(countries)
    assert result["decision"] in {"switch on", "keep base rate", "not enough data"}


def test_covariance_is_inverse_hessian_and_offset_model_defaults_to_offset():
    import math

    from geointel.risk import trained

    x = [[1.0, float(i % 5)] for i in range(200)]
    y = [1 if i % 7 == 0 else 0 for i in range(200)]
    model = trained.fit_logistic(x, y)
    cov = model["cov"]
    assert cov[0][0] > 0 and cov[1][1] > 0
    assert trained.link_se(model, [1.0, 2.0]) > 0
    # features that carry nothing: the offset model returns the offset forecast
    offset = [math.log(0.1 / 0.9)] * 200
    noise = [[1.0, 0.0] for _ in range(200)]
    flat = trained.fit_offset_logistic(
        noise, [1 if i % 10 == 0 else 0 for i in range(200)], offset, l2=20.0
    )
    assert abs(trained.predict_offset(flat, [1.0, 0.0], offset[0]) - 0.1) < 0.01


def test_fill_missing_uses_reference_medians():
    from geointel.risk import trained

    base = {f: 1.0 for f in trained.FEATURES}
    train = [dict(base), dict(base)]
    test = [dict(base, edi=None)]
    test_other = dict(base, edi=99.0)
    filled = trained.fill_missing(train + test + [test_other], reference=train)
    assert filled[2][1 + trained.FEATURES.index("edi")] == 1.0
