"""Deterministic reconstruction from caller-supplied observations and assessments."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from itertools import combinations
from statistics import mean
from typing import TypeVar

from .models import (
    ChangeSettings,
    Event,
    EventType,
    Evidence,
    EvidenceBasis,
    Hypothesis,
    Observation,
    Record,
    Relationship,
    RelationshipType,
    TurningPointReview,
)

T = TypeVar("T", bound=Record)
DEFAULT_CHANGE_SETTINGS = ChangeSettings()


def _unique(records: Iterable[T], key: str) -> tuple[T, ...]:
    by_id: dict[str, T] = {}
    for record in records:
        identifier = getattr(record, key)
        if identifier in by_id and by_id[identifier] != record:
            raise ValueError(f"conflicting records for {key} {identifier!r}")
        by_id[identifier] = record
    return tuple(by_id[identifier] for identifier in sorted(by_id))


def _evidence_at(evidence: Iterable[Evidence], cutoff: date) -> tuple[Evidence, ...]:
    return _unique((item for item in evidence if item.available_on <= cutoff), "evidence_id")


def _observations_at(event: Event, cutoff: date) -> tuple[Observation, ...]:
    observations = [item for item in event.observations if item.evidence.available_on <= cutoff]
    _unique((item.evidence for item in observations), "evidence_id")
    # A single source can explicitly report multiple date alternatives.
    return tuple(sorted(set(observations), key=lambda item: item.model_dump_json()))


def _start_key(event: Event) -> tuple[date, date, str]:
    return (
        min(item.start.earliest for item in event.observations),
        max(item.start.latest for item in event.observations),
        event.event_id,
    )


def _overlap(left: Event, right: Event) -> str | None:
    pairs = [(a, b) for a in left.observations for b in right.observations]
    if all(
        a.start.latest <= b.finish.earliest and b.start.latest <= a.finish.earliest
        for a, b in pairs
    ):
        return "definite"
    if any(
        a.start.earliest <= b.finish.latest and b.start.earliest <= a.finish.latest
        for a, b in pairs
    ):
        return "possible"
    return None


def _order(cause: Event, outcome: Event) -> str:
    first_min, first_max, _ = _start_key(cause)
    second_min, second_max, _ = _start_key(outcome)
    if first_max < second_min:
        return "cause_starts_before_outcome"
    if first_min > second_max:
        return "cause_starts_after_outcome"
    return "indeterminate"


def _date_status(event: Event) -> str:
    starts = [item.start for item in event.observations]
    ends = [item.finish for item in event.observations]
    if any(
        max(r.earliest for r in bounds) > min(r.latest for r in bounds) for bounds in (starts, ends)
    ):
        return "conflicting"
    if any(r.earliest != r.latest for r in starts + ends):
        return "uncertain"
    return "exact"


def _relationship_at(relationship: Relationship, events: dict[str, Event]) -> dict | None:
    evidence = relationship.evidence
    left = events[relationship.source_event_id]
    right = events[relationship.target_event_id]
    kind = relationship.relationship_type
    if kind == RelationshipType.PRECEDES:
        if max(item.finish.latest for item in left.observations) >= _start_key(right)[0]:
            return None
    if kind == RelationshipType.OVERLAPS and _overlap(left, right) is None:
        return None
    if kind == RelationshipType.RESPONDS_TO and (
        _order(right, left) != "cause_starts_before_outcome"
        or all(item.basis == EvidenceBasis.TEMPORAL for item in evidence)
    ):
        return None
    if kind == RelationshipType.POSSIBLE_CONTRIBUTOR and (
        _order(left, right) != "cause_starts_before_outcome"
        or all(item.basis != EvidenceBasis.MECHANISM for item in evidence)
    ):
        return None
    return relationship.model_dump(mode="json")


def _evaluate(hypothesis: Hypothesis, events: dict[str, Event], cutoff: date) -> dict:
    cause = events[hypothesis.cause_event_id]
    outcome = events[hypothesis.outcome_event_id]
    order = _order(cause, outcome)
    support = _evidence_at(hypothesis.supporting_evidence, cutoff)
    opposition = _evidence_at(hypothesis.contradictory_evidence, cutoff)
    _unique((*support, *opposition), "evidence_id")
    mechanism = any(item.basis == EvidenceBasis.MECHANISM for item in support)
    if order == "cause_starts_after_outcome":
        assessment = "temporally_incompatible"
    elif support and opposition:
        assessment = "contested"
    elif opposition:
        assessment = "contradictory_evidence_only"
    elif order == "indeterminate":
        assessment = "temporal_order_unresolved"
    elif mechanism:
        assessment = "mechanism_supported_hypothesis"
    else:
        assessment = "insufficient_mechanism_evidence"
    record = hypothesis.model_dump(
        mode="json", exclude={"supporting_evidence", "contradictory_evidence"}
    )
    return {
        **record,
        "supporting_evidence": [item.model_dump(mode="json") for item in support],
        "contradictory_evidence": [item.model_dump(mode="json") for item in opposition],
        "temporal_order": order,
        "assessment": assessment,
        "causality_established": False,
    }


def _intensity(event: Event) -> int | None:
    ratings = {item.intensity for item in event.observations}
    return next(iter(ratings)) if len(ratings) == 1 else None


def _detect_changes(
    events: list[Event], start: date, cutoff: date, settings: ChangeSettings
) -> list[dict]:
    window_count = ((cutoff - start).days + 1) // settings.window_days
    windows: dict[int, list[Event]] = defaultdict(list)
    ambiguous: set[int] = set()
    for event in events:
        earliest, latest, _ = _start_key(event)
        first = (earliest - start).days // settings.window_days
        last = (latest - start).days // settings.window_days
        if first == last and 0 <= first < window_count:
            windows[first].append(event)
        elif first != last:
            ambiguous.update(range(max(first, 0), min(last + 1, window_count)))

    candidates = []
    boundaries = windows.keys() | {index + 1 for index in windows}
    for index in sorted(boundaries):
        if not 0 < index < window_count or {index - 1, index} & ambiguous:
            continue
        before, after = windows[index - 1], windows[index]
        count_change = len(after) - len(before)
        before_ratings = [rating for event in before if (rating := _intensity(event)) is not None]
        after_ratings = [rating for event in after if (rating := _intensity(event)) is not None]
        intensity_change = None
        if min(len(before_ratings), len(after_ratings)) >= settings.min_rated_per_window:
            intensity_change = mean(after_ratings) - mean(before_ratings)
        metrics = []
        if abs(count_change) >= settings.min_count_change:
            metrics.append("event_count")
        if intensity_change is not None and abs(intensity_change) >= (
            settings.min_mean_intensity_change
        ):
            metrics.append("mean_intensity")
        if metrics:
            candidates.append(
                {
                    "boundary": (start + timedelta(days=index * settings.window_days)).isoformat(),
                    "status": "algorithmic_candidate",
                    "triggered_metrics": metrics,
                    "before_event_ids": [event.event_id for event in before],
                    "after_event_ids": [event.event_id for event in after],
                    "before_rated_count": len(before_ratings),
                    "after_rated_count": len(after_ratings),
                    "event_count_change": count_change,
                    "mean_intensity_change": intensity_change,
                }
            )
    return candidates


def reconstruct(
    events: Iterable[Event],
    *,
    cutoff: date,
    country: str | None = None,
    region: str | None = None,
    actor: str | None = None,
    event_type: EventType | None = None,
    relationships: Iterable[Relationship] = (),
    hypotheses: Iterable[Hypothesis] = (),
    turning_point_reviews: Iterable[TurningPointReview] = (),
    pattern_start: date | None = None,
    change_settings: ChangeSettings = DEFAULT_CHANGE_SETTINGS,
) -> dict:
    """Build a JSON-compatible snapshot using the inclusive evidence cutoff."""
    if pattern_start is not None and pattern_start > cutoff:
        raise ValueError("pattern_start must be on or before cutoff")
    canonical_events = (
        event.model_copy(
            update={
                "actors": tuple(sorted(set(event.actors))),
                "observations": observations,
            }
        )
        for event in events
        if (observations := _observations_at(event, cutoff))
    )
    registry = _unique(canonical_events, "event_id")
    visible = [
        event
        for event in registry
        if (country is None or country.casefold() == event.location.country.casefold())
        and (region is None or region.casefold() == event.location.region.casefold())
        and (actor is None or actor.casefold() in {name.casefold() for name in event.actors})
        and (event_type is None or event_type == event.event_type)
    ]
    visible.sort(key=_start_key)
    by_id = {event.event_id: event for event in visible}
    groups: dict[str, list[Event]] = defaultdict(list)
    for event in visible:
        if event.crisis_id is not None:
            groups[event.crisis_id].append(event)

    overlap_records = []
    for left, right in combinations(visible, 2):
        if certainty := _overlap(left, right):
            overlap_records.append(
                {
                    "event_ids": [left.event_id, right.event_id],
                    "certainty": certainty,
                    "evidence_ids_by_event": {
                        event.event_id: sorted(
                            {item.evidence.evidence_id for item in event.observations}
                        )
                        for event in (left, right)
                    },
                }
            )

    visible_relationships = _unique(
        (
            relationship.model_copy(update={"evidence": evidence})
            for relationship in relationships
            if relationship.available_on <= cutoff
            and relationship.source_event_id != relationship.target_event_id
            and relationship.source_event_id in by_id
            and relationship.target_event_id in by_id
            and (evidence := _evidence_at(relationship.evidence, cutoff))
        ),
        "relationship_id",
    )
    links = [
        record
        for relationship in visible_relationships
        if (record := _relationship_at(relationship, by_id))
    ]
    assessments = [
        _evaluate(hypothesis, by_id, cutoff)
        for hypothesis in _unique(
            (item for item in hypotheses if item.available_on <= cutoff), "hypothesis_id"
        )
        if hypothesis.cause_event_id != hypothesis.outcome_event_id
        and hypothesis.cause_event_id in by_id
        and hypothesis.outcome_event_id in by_id
    ]
    reviews = _unique(
        (
            review.model_copy(update={"evidence": evidence})
            for review in turning_point_reviews
            if review.crisis_id in groups
            and review.boundary <= review.available_on <= cutoff
            and (evidence := _evidence_at(review.evidence, cutoff))
        ),
        "review_id",
    )
    return {
        "schema_version": 1,
        "cutoff": cutoff.isoformat(),
        "filters": {
            "country": country,
            "region": region,
            "actor": actor,
            "event_type": str(event_type) if event_type is not None else None,
        },
        "events": [
            {**event.model_dump(mode="json"), "date_status": _date_status(event)}
            for event in visible
        ],
        "overlaps": overlap_records,
        "relationships": links,
        "hypotheses": assessments,
        "pattern_start": pattern_start.isoformat() if pattern_start is not None else None,
        "change_settings": change_settings.model_dump(mode="json"),
        "crises": [
            {
                "crisis_id": crisis_id,
                "event_ids": [event.event_id for event in groups[crisis_id]],
                "turning_point_candidates": (
                    _detect_changes(groups[crisis_id], pattern_start, cutoff, change_settings)
                    if pattern_start is not None
                    else []
                ),
            }
            for crisis_id in sorted(groups)
        ],
        "historical_turning_point_reviews": [
            {**review.model_dump(mode="json"), "status": "historically_validated"}
            for review in reviews
        ],
    }
