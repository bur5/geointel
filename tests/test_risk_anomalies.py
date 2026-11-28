from geointel.risk import anomalies


def _country(iso3, coup, events=0):
    return {
        "iso3": iso3,
        "risks": {
            "coup_attempt": {
                "horizons": {"1y": {"p": coup}},
                "basis": {"event_years": events, "exposure_years": 36},
            }
        },
    }


def test_anomaly_checks():
    snapshot = {
        "countries": [_country(c, 0.075, i) for i, c in enumerate(("A1", "A2", "A3", "A4", "A5"))]
        + [_country(c, 0.02) for c in ("B1", "B2", "B3", "B4", "B5")]
        + [_country("USA", 0.09), _country("NOR", 0.001)],
        "event_types": [{"key": "coup_attempt"}],
        "sources": [{"key": "ioda", "name": "IODA", "status": "failed"}],
    }
    signals = {
        "countries": {"GBR": {"danger": {"level": 3, "model_level": 3, "ministry_median": 1}}}
    }
    previous_signals = {"countries": {"GBR": {"danger": {"level": 1}}}}
    previous = {"countries": [_country("USA", 0.01)]}
    regimes = {"USA": {"value": 3}, "NOR": {"value": 3}, "A1": {"value": 0}, "A2": {"value": 0}}
    found = anomalies.check(snapshot, signals, previous, previous_signals, regimes)
    kinds = anomalies.summary(found)
    assert kinds["level_jump"] == 1 and kinds["mfa_divergence"] == 1
    assert kinds["identical"] == 1 and kinds["source_failed"] == 1
    assert any(f["kind"] == "regime_inversion" and f["iso3"] == "USA" for f in found)
    assert any(f["kind"] == "probability_jump" and f["iso3"] == "USA" for f in found)
    assert not any(f.get("iso3") == "NOR" for f in found)
