from geointel.risk.snapshot import mark_grouped


def _c(iso3, p, question="onset_within"):
    return {
        "iso3": iso3,
        "risks": {"coup_attempt": {"question": question, "horizons": {"1y": {"p": p}}}},
    }


def test_grouped_display_marks_background_and_elevated():
    snap = {
        "countries": [
            _c("A", 0.01),
            _c("B", 0.01),
            _c("C", 0.01),
            _c("D", 0.07),
            _c("E", 0.5, "active_at_end"),
        ]
    }
    mark_grouped(snap, ("coup_attempt",))
    by = {c["iso3"]: c["risks"]["coup_attempt"].get("display") for c in snap["countries"]}
    assert by["A"]["group"] == "background" and by["D"]["group"] == "elevated"
    assert by["E"] is None
