from geointel.risk.sources import rivalries, ucdp_ged


def test_rivalry_years_carry_on_after_data_end():
    rows = [
        {"ccode1": 365.0, "ccode2": 369.0, "start": 2014.0, "end": 2020.0},
        {"ccode1": 2.0, "ccode2": 365.0, "start": 1946.0, "end": 1989.0},
    ]
    years = rivalries.active_years(rows, {365: "RUS", 369: "UKR", 2: "USA"})
    assert 2024 in years["UKR"] and 2013 not in years["UKR"]
    assert 1989 in years["USA"] and 1990 not in years["USA"]


def test_ged_country_year_splits_state_and_other():
    text = (
        "year,country,type_of_violence,best\n"
        "2019,Mexico,2,30\n2019,Mexico,1,4\n2019,Mexico,3,5\n1985,Mexico,1,9\n"
    )
    assert ucdp_ged.country_year(text) == {"MEX": {2019: (4.0, 35.0)}}
