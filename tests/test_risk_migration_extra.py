from datetime import date

from geointel.risk.links import build_links
from geointel.risk.sources import migration, undesa


def test_undesa_stock_from_table_rows(monkeypatch):
    monkeypatch.setattr(undesa, "_numeric_map", lambda: {"804": "UKR", "616": "POL", "276": "DEU"})
    rows = [
        ["International migrant stock"],
        [
            "Index",
            "Region of destination",
            "Notes",
            "Location code of destination",
            "Type",
            "Region of origin",
            "Location code of origin",
            "1990",
            "2020",
            "2024",
            "1990",
            "2020",
            "2024",
        ],
        [
            "1",
            "WORLD",
            "",
            "900",
            "",
            "Ukraine",
            "804",
            "5500000",
            "6100000",
            "9800000",
            "1",
            "2",
            "3",
        ],
        ["2", "Poland", "", "616", "", "Ukraine", "804", "100", "300000", "1500000", "", "", ""],
        ["3", "Germany", "", "276", "", "Ukraine", "804", "50", "200000", "1200000", "", "", ""],
        ["4", "Germany", "", "276", "", "Africa", "903", "1", "2", "3", "", "", ""],
    ]
    out = undesa.stock(rows)
    ukr = out["UKR"]
    assert ukr["year"] == 2024 and ukr["total"] == 9_800_000
    assert ukr["series"]["1990"] == 5_500_000
    assert ukr["top"][0] == ["POL", 1_500_000]


def test_irregular_labels_never_zero():
    found = migration.irregular_found({"DEU": [("2024", 249155.0), ("2025", 168360.0)]})
    assert found["DEU"]["found"] == 168360 and found["DEU"]["year"] == "2025"
    assert migration.irregular_label("USA", found)["kind"] == "estimate"
    assert migration.irregular_label("DEU", found)["kind"] == "indirect"
    assert migration.irregular_label("BRA", found) == {"kind": "none"}


def test_policy_journal_and_direction():
    news = [
        {"date": "2026-11-01", "country": "DEU", "sign": "migration_tighten", "url": "a"},
        {"date": "2026-06-01", "country": "DEU", "sign": "migration_ease", "url": "b"},
        {"date": "2026-11-02", "country": "DEU", "sign": "unrest", "url": "c"},
        {"date": "2024-01-01", "country": "DEU", "sign": "migration_tighten", "url": "d"},
    ]
    journal = migration.policy_journal([], news, "2025-10-01")
    assert [e["url"] for e in journal] == ["a", "b"]
    summary = migration.policy_summary(journal, date(2026, 11, 27))
    assert summary["DEU"]["d90"] == 1 and summary["DEU"]["d365"] == 0


def test_links_carry_migration_labels():
    links = build_links(
        trade=None,
        trade_year=None,
        displacement=None,
        asylum=None,
        profiles={"UKR": {"population": {"value": 38_000_000}}},
        diaspora={"UKR": {"year": 2024, "total": 9_800_000, "series": {}, "top": []}},
        irregular={"DEU": {"year": "2025", "found": 1, "series": []}},
        policy=None,
        universe=["UKR", "DEU", "USA"],
    )
    c = links["countries"]
    assert c["UKR"]["migration"]["diaspora"]["per_1000"] == 257.9
    assert c["UKR"]["migration"]["irregular"]["kind"] == "none"
    assert c["DEU"]["migration"]["irregular"]["kind"] == "indirect"
    assert c["USA"]["migration"]["irregular"]["kind"] == "estimate"
