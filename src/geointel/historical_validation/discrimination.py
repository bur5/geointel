"""Discrimination metrics for a single pre-matched binary scoring sample."""

from collections import Counter
from collections.abc import Iterable
from math import fsum
from typing import Annotated, Literal

from pydantic import Field

from geointel.historical_validation.audit import Record

Probability = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
Outcome = Annotated[int, Field(strict=True, ge=0, le=1)]


class BinaryScore(Record):
    probability: Probability
    outcome: Outcome


class PairedBinaryScore(Record):
    model_probability: Probability
    baseline_probability: Probability
    outcome: Outcome


class Discrimination(Record):
    positives: int
    negatives: int
    average_precision: float | None
    roc_auc: float | None
    undefined_reason: Literal["empty", "single_class"] | None


def discrimination(rows: Iterable[BinaryScore]) -> Discrimination:
    """Group exact ties. The caller supplies one eligible target/horizon sample."""
    positive: Counter[float] = Counter()
    negative: Counter[float] = Counter()
    for row in rows:
        counts = positive if row.outcome else negative
        counts[row.probability] += 1

    positives = positive.total()
    negatives = negative.total()
    if not positives or not negatives:
        return Discrimination(
            positives=positives,
            negatives=negatives,
            average_precision=None,
            roc_auc=None,
            undefined_reason="single_class" if positives + negatives else "empty",
        )

    seen_positive = seen_negative = doubled_concordance = 0
    precision_terms = []
    for probability in sorted(positive.keys() | negative.keys(), reverse=True):
        events = positive[probability]
        non_events = negative[probability]
        seen_positive += events
        seen_negative += non_events
        precision_terms.append(
            (events / positives) * (seen_positive / (seen_positive + seen_negative))
        )
        doubled_concordance += events * (2 * (negatives - seen_negative) + non_events)

    return Discrimination(
        positives=positives,
        negatives=negatives,
        average_precision=fsum(precision_terms),
        roc_auc=doubled_concordance / (2 * positives * negatives),
        undefined_reason=None,
    )


class PairedDiscrimination(Record):
    model: Discrimination
    baseline: Discrimination


def paired_discrimination(rows: Iterable[PairedBinaryScore]) -> PairedDiscrimination:
    """Score both sides on the same outcomes after the archive join."""
    model = []
    baseline = []
    for row in rows:
        model.append(BinaryScore(probability=row.model_probability, outcome=row.outcome))
        baseline.append(BinaryScore(probability=row.baseline_probability, outcome=row.outcome))
    return PairedDiscrimination(model=discrimination(model), baseline=discrimination(baseline))
