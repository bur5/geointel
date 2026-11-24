import json
from datetime import date

import pytest
from pydantic import ValidationError

from geointel.timeline.analysis import reconstruct
from geointel.timeline.models import (
    DateRange,
    Event,
    EventType,
    Evidence,
    Hypothesis,
    Location,
    Observation,
    Relationship,
    TurningPointReview,
)


def day(value):
    return date(2001, 4, value)


def bounds(first, last=None):
    return DateRange(earliest=day(first), latest=day(first if last is None else last))


def evidence(identifier, available=14, basis="contextual"):
    return Evidence(
        evidence_id=identifier,
        source="Fictional North Estuary archive",
        locator=f"synthetic:{identifier}",
        available_on=day(available),
        quality="medium",
        uncertainty="Synthetic single-source record",
        finding="A fictional observer supplied this record.",
        basis=basis,
    )


def event(identifier, start, *, latest=None, end=None, intensity=None, kind="negotiation"):
    return Event(
        event_id=identifier,
        event_type=kind,
        location=Location(country="Lumen", region="North Estuary"),
        actors=("Lumen Council",),
        observations=(
            Observation(
                evidence=evidence(f"source-{identifier}", available=end or latest or start),
                start=bounds(start, latest),
                end=bounds(end) if end is not None else None,
                intensity=intensity,
            ),
        ),
        crisis_id="estuary-crisis",
    )


def event_ids(snapshot):
    return [item["event_id"] for item in snapshot["events"]]


def test_ordering_filters_grouping_and_tie_breaker():
    events = [
        event("transition", 12, kind="political_transition"),
        event("talks-b", 3),
        event("talks-a", 3),
    ]
    snapshot = reconstruct(events, cutoff=day(14))
    assert event_ids(snapshot) == ["talks-a", "talks-b", "transition"]
    assert snapshot["crises"][0]["event_ids"] == event_ids(snapshot)
    filtered = reconstruct(
        events,
        cutoff=day(14),
        country="lumen",
        region="NORTH ESTUARY",
        actor="lumen council",
        event_type=EventType.NEGOTIATION,
    )
    assert event_ids(filtered) == ["talks-a", "talks-b"]
    assert not reconstruct(events, cutoff=day(14), actor="Unknown")["events"]


def test_overlap_is_inclusive_and_distinguishes_uncertain_dates():
    snapshot = reconstruct(
        [event("talks", 2, end=5), event("protest", 5), event("vote", 4, latest=6)],
        cutoff=day(14),
    )
    assert [(item["event_ids"], item["certainty"]) for item in snapshot["overlaps"]] == [
        (["talks", "vote"], "possible"),
        (["talks", "protest"], "definite"),
        (["vote", "protest"], "possible"),
    ]
    assert snapshot["events"][1]["date_status"] == "uncertain"


def test_conflicting_sources_remain_distinct_without_filling_date_gaps():
    talks = event("talks", 2)
    late = Observation(evidence=evidence("alternate", available=9), start=bounds(8))
    talks = talks.model_copy(update={"observations": (*talks.observations, late)})
    protest = event("protest", 5)
    snapshot = reconstruct([talks, protest], cutoff=day(14))
    assert snapshot["events"][0]["date_status"] == "conflicting"
    assert len(snapshot["events"][0]["observations"]) == 2
    assert snapshot["overlaps"] == []
    earlier = reconstruct([talks, protest], cutoff=day(7))
    assert earlier["events"][0]["date_status"] == "exact"
    assert len(earlier["events"][0]["observations"]) == 1


def test_duplicate_events_do_not_increase_counts_and_collisions_raise():
    talks = event("talks", 2)
    reordered = talks.model_copy(update={"observations": talks.observations * 2})
    assert event_ids(reconstruct([talks, reordered], cutoff=day(14))) == ["talks"]
    with pytest.raises(ValueError, match="conflicting records for event_id"):
        reconstruct([talks, event("talks", 3)], cutoff=day(14))


def test_missing_provenance_and_foreknowledge_are_rejected():
    raw = event("talks", 2).model_dump()
    raw["observations"][0]["evidence"]["locator"] = "   "
    with pytest.raises(ValidationError, match="locator"):
        Event.model_validate(raw)
    with pytest.raises(ValidationError, match="observations"):
        Event.model_validate({**raw, "observations": []})
    with pytest.raises(ValidationError, match="availability"):
        Observation(evidence=evidence("premature", available=3), start=bounds(4))


def hypothesis(**updates):
    fields = {
        "hypothesis_id": "talks-effect",
        "cause_event_id": "talks",
        "outcome_event_id": "agreement",
        "proposed_mechanism": "Talks resolved a procedural disagreement.",
        "available_on": day(9),
        "alternative_explanations": ("Independent mediation",),
        "confounding_factors": ("Leadership change",),
        "uncertainty": "Decision records are incomplete.",
        "limitations": ("No counterfactual observation",),
    }
    return Hypothesis(**(fields | updates))


def relationship(kind, support):
    return Relationship(
        relationship_id=kind,
        available_on=day(8),
        source_event_id="talks",
        target_event_id="agreement",
        relationship_type=kind,
        evidence=support,
    )


def test_temporal_correlation_does_not_support_causal_attribution():
    timing = evidence("chronology", basis="temporal")
    events = [event("talks", 2), event("agreement", 8, kind="peace_agreement")]
    links = [relationship(kind, [timing]) for kind in ("precedes", "possible_contributor")]
    result = reconstruct(
        events,
        cutoff=day(14),
        relationships=links,
        hypotheses=[hypothesis(supporting_evidence=[timing])],
    )
    assert [item["relationship_type"] for item in result["relationships"]] == ["precedes"]
    assert result["hypotheses"][0]["assessment"] == "insufficient_mechanism_evidence"
    assert result["hypotheses"][0]["causality_established"] is False
    with pytest.raises(ValidationError, match="evidence"):
        relationship("associated_with", [])


def test_contradictory_hypotheses_and_evidence_preserve_limits():
    support = evidence("minutes", available=9, basis="mechanism")
    opposition = evidence("mediator-diary", available=12, basis="mechanism")
    contested = hypothesis(supporting_evidence=[support], contradictory_evidence=[opposition])
    reverse = hypothesis(
        hypothesis_id="reverse",
        cause_event_id="agreement",
        outcome_event_id="talks",
        supporting_evidence=[opposition],
    )
    events = [event("talks", 2), event("agreement", 8)]
    result = reconstruct(events, cutoff=day(14), hypotheses=[contested, reverse])
    reversed_order, assessment = result["hypotheses"]
    assert reversed_order["assessment"] == "temporally_incompatible"
    assert assessment["assessment"] == "contested"
    assert assessment["contradictory_evidence"][0]["evidence_id"] == "mediator-diary"
    assert assessment["confounding_factors"] == ["Leadership change"]
    assert assessment["causality_established"] is False


def turning_point_review():
    return TurningPointReview(
        review_id="historian-review",
        available_on=day(15),
        crisis_id="estuary-crisis",
        boundary=day(8),
        rationale="A fictional historian linked the change to the opening of formal talks.",
        evidence=[evidence("historian", available=15)],
    )


def test_cutoff_applies_to_events_links_hypotheses_and_reviews():
    events = [event("talks", 2), event("agreement", 8), event("future", 15)]
    mechanism = evidence("minutes", available=10, basis="mechanism")
    links = [relationship("possible_contributor", [mechanism, evidence("later")])]
    proposed = hypothesis(
        supporting_evidence=[mechanism], contradictory_evidence=[evidence("later")]
    )
    review = turning_point_review()
    snapshot = reconstruct(
        events,
        cutoff=day(10),
        relationships=links,
        hypotheses=[proposed],
        turning_point_reviews=[review],
    )
    assert event_ids(snapshot) == ["talks", "agreement"]
    assert [item["evidence_id"] for item in snapshot["relationships"][0]["evidence"]] == ["minutes"]
    assert not snapshot["hypotheses"][0]["contradictory_evidence"]
    assert snapshot["hypotheses"][0]["assessment"] == "mechanism_supported_hypothesis"
    assert snapshot["historical_turning_point_reviews"] == []
    earlier = reconstruct(events, cutoff=day(8), relationships=links, hypotheses=[proposed])
    assert earlier["relationships"] == earlier["hypotheses"] == []


def test_change_detection_and_review_are_reproducible_and_distinct():
    events = [
        event(f"event-{number}", number, intensity=1 if number < 8 else 4)
        for number in (1, 3, 8, 9, 10, 11)
    ]
    options = {
        "cutoff": day(15),
        "pattern_start": day(1),
        "turning_point_reviews": [turning_point_review()],
    }
    snapshot = reconstruct(events, **options)
    assert json.dumps(snapshot, allow_nan=False) == json.dumps(reconstruct(events[::-1], **options))
    [candidate] = snapshot["crises"][0]["turning_point_candidates"]
    assert candidate["boundary"] == "2001-04-08"
    assert candidate["triggered_metrics"] == ["event_count", "mean_intensity"]
    assert candidate["status"] == "algorithmic_candidate"
    assert candidate["event_count_change"] == 2
    assert candidate["mean_intensity_change"] == 3
    assert snapshot["historical_turning_point_reviews"][0]["status"] == "historically_validated"
    assert not reconstruct(events, cutoff=day(13), pattern_start=day(1))["crises"][0][
        "turning_point_candidates"
    ]
    assert not reconstruct(
        [*events, event("uncertain", 7, latest=8)],
        **options,
    )["crises"][0]["turning_point_candidates"]


def test_all_relationship_labels_have_cited_evidence():
    talks = event("talks", 2, end=8)
    agreement = event("agreement", 8)
    support = [evidence("minutes", basis="mechanism")]
    response = relationship("responds_to", support).model_copy(
        update={"source_event_id": "agreement", "target_event_id": "talks"}
    )
    links = [
        relationship(kind, support)
        for kind in (
            "associated_with",
            "contradicts",
            "overlaps",
            "possible_contributor",
            "precedes",
        )
    ]
    snapshot = reconstruct([talks, agreement], cutoff=day(14), relationships=[*links, response])
    assert [item["relationship_type"] for item in snapshot["relationships"]] == [
        "associated_with",
        "contradicts",
        "overlaps",
        "possible_contributor",
        "responds_to",
    ]
    assert all(
        item["evidence"][0]["evidence_id"] == "minutes" for item in snapshot["relationships"]
    )


def test_uncertain_order_blocks_possible_contributions():
    support = [evidence("minutes", basis="mechanism")]
    snapshot = reconstruct(
        [event("talks", 2, latest=9), event("agreement", 8)],
        cutoff=day(14),
        relationships=[relationship("possible_contributor", support)],
        hypotheses=[hypothesis(supporting_evidence=support)],
    )
    assert not snapshot["relationships"]
    [assessment] = snapshot["hypotheses"]
    assert assessment["temporal_order"] == "indeterminate"
    assert assessment["assessment"] == "temporal_order_unresolved"
