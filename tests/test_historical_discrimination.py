import pytest
from pydantic import ValidationError

from geointel.historical_validation.discrimination import (
    BinaryScore,
    PairedBinaryScore,
    discrimination,
    paired_discrimination,
)


def test_ties_and_input_order():
    rows = [
        BinaryScore(probability=0.9, outcome=1),
        BinaryScore(probability=0.9, outcome=0),
        BinaryScore(probability=0.5, outcome=1),
        BinaryScore(probability=0.1, outcome=0),
    ]
    result = discrimination(rows)
    assert result.roc_auc == pytest.approx(0.625)
    assert result.average_precision == pytest.approx(7 / 12)
    assert result.undefined_reason is None
    assert result == discrimination(reversed(rows))


def test_all_tied_rare_event():
    rows = [BinaryScore(probability=0.01, outcome=1)]
    rows.extend([BinaryScore(probability=0.01, outcome=0)] * 99)
    result = discrimination(rows)
    assert result.average_precision == pytest.approx(0.01)
    assert result.roc_auc == pytest.approx(0.5)


@pytest.mark.parametrize(("positive", "negative", "auc"), [(1.0, 0.0, 1), (0.0, 1.0, 0)])
def test_perfect_and_reverse_order(positive, negative, auc):
    result = discrimination(
        [BinaryScore(probability=positive, outcome=1), BinaryScore(probability=negative, outcome=0)]
    )
    assert result.roc_auc == auc
    assert result.average_precision == (1 if auc else 0.5)


@pytest.mark.parametrize(
    ("outcomes", "reason"), [([], "empty"), ([0], "single_class"), ([1], "single_class")]
)
def test_undefined_auc(outcomes, reason):
    result = discrimination(BinaryScore(probability=0.0, outcome=y) for y in outcomes)
    assert result.undefined_reason == reason
    assert result.average_precision is None
    assert result.roc_auc is None


@pytest.mark.parametrize(
    ("probability", "outcome"),
    [(None, 0), (0.5, None), (float("nan"), 1), (float("inf"), 0), (0.5, True), (1.1, 1)],
)
def test_missing_and_invalid_values_fail_schema(probability, outcome):
    with pytest.raises(ValidationError):
        BinaryScore(probability=probability, outcome=outcome)


def test_model_and_baseline_share_outcomes():
    rows = [
        PairedBinaryScore(model_probability=0.8, baseline_probability=0.4, outcome=1),
        PairedBinaryScore(model_probability=0.2, baseline_probability=0.4, outcome=0),
    ]
    comparison = paired_discrimination(iter(rows))
    assert comparison.model.positives == comparison.baseline.positives == 1
    assert comparison.model.negatives == comparison.baseline.negatives == 1
    assert comparison.model.roc_auc == 1
    assert comparison.baseline.roc_auc == 0.5
    with pytest.raises(ValidationError, match="baseline_probability"):
        PairedBinaryScore.model_validate({"model_probability": 0.8, "outcome": 1})
