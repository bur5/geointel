import math

from geointel.risk.sources import ucdp_term

CSV = (
    "conflict_id,location,type_of_conflict,year,c_epterm,c_outcome,c_ep_endyear\n"
    "1,Azerbaijan,3,2020,1,6,2020\n"
    "1,Azerbaijan,3,2016,1,5,2016\n"
    "2,Peru,3,2010,0,,\n"
    "3,Peru,2,2010,1,3,2010\n"
)


def test_episodes_and_features_use_only_known_endings():
    ended = ucdp_term.episodes(CSV)
    assert ended == {"AZE": [(2016, 5), (2020, 6)]}
    assert ucdp_term.features(ended, "AZE", 2018) == [1.0, 0.0, 1.0, math.log1p(2)]
    assert ucdp_term.features(ended, "AZE", 2023) == [1.0, 1.0, 0.0, math.log1p(3)]
    assert ucdp_term.features(ended, "PER", 2023) == [1.0, 0.0, 0.0, math.log1p(50)]


def test_pick_url_takes_newest_version():
    html = (
        '<a href="https://ucdp.uu.se/downloads/monadterm/'
        'UCDPConflictTerminationDataset_v3_2021_Conflict.csv">'
        '<a href="https://ucdp.uu.se/downloads/monadterm/'
        'UCDPConflictTerminationDataset_v4_2024_Conflict.csv">'
    )
    assert ucdp_term.pick_url(html).endswith("v4_2024_Conflict.csv")
