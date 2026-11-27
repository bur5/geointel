from geointel.risk.sources import outlook, trade

MILEX = (
    "entity,code,year,share_gdp,owid_region\n"
    "Ukraine,UKR,2020,4.0,Europe\nUkraine,UKR,2024,34.5,Europe\n"
)
VDEM = "entity,code,year,electdem_vdem__estimate_best,owid_region\nNorway,NOR,2024,0.91,Europe\n"
REGIME = "entity,code,year,regime_row_owid\nNorway,NOR,2024,Liberal democracy\n"


def test_owid_value_column_skips_region_label():
    assert trade.owid_series(MILEX)["UKR"] == [(2020, 4.0), (2024, 34.5)]
    assert outlook.owid_latest(VDEM)["NOR"]["value"] == 0.91
    assert outlook.owid_regime_series(REGIME)["NOR"][2024] == 3
