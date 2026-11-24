"""Offline evaluation of versioned forecasts against an explicit historical panel."""

import argparse
import json
import math
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Horizon = Annotated[int, Field(gt=0)]
LOG_LOSS_FLOOR = 1e-15
CALIBRATION_BINS = 10
SMALL_SAMPLE = 30


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Contract(Record):
    target: Text
    geographic_unit: Text
    horizon_months: Horizon
    kind: Literal["binary_probability", "event_count"]


class Case(Record):
    location: Text
    origin: AwareDatetime
    start: AwareDatetime
    end: AwareDatetime


class Prediction(Record):
    case: Case
    contract: Contract
    record_id: Text
    issued_at: AwareDatetime
    available_at: AwareDatetime
    input_cutoff: AwareDatetime
    value: float | None


class Observation(Record):
    contract: Contract
    location: Text
    start: AwareDatetime
    end: AwareDatetime
    record_id: Text
    available_at: AwareDatetime
    complete: bool
    value: int | None


class ModelArchive(Record):
    model: Text
    version: Text
    snapshot: Text
    predictions: tuple[Prediction, ...]


class Threshold(Record):
    value: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    rationale: Text


class Study(Record):
    contract: Contract
    panel_snapshot: Text
    cases: tuple[Case, ...]
    models: tuple[ModelArchive, ...]
    outcome_snapshot: Text
    observations: tuple[Observation, ...]
    as_of: AwareDatetime
    data_kind: Literal["synthetic", "historical"]
    threshold: Threshold | None = None


K = TypeVar("K")
V = TypeVar("V")


def _index(items: list[tuple[K, V]], label: str) -> dict[K, V]:
    result: dict[K, V] = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate {label}: {key}")
        result[key] = value
    return result


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _metrics(pairs: list[tuple[float, int]], study: Study) -> dict:
    n = len(pairs)
    result: dict = {"n": n, "small_sample": 0 < n < SMALL_SAMPLE}
    if study.contract.kind == "event_count":
        result["mae"] = math.fsum(abs(p - y) / n for p, y in pairs) if n else None
        return result

    bins: list[list[tuple[float, int]]] = [[] for _ in range(CALIBRATION_BINS)]
    for probability, outcome in pairs:
        bins[min(int(probability * CALIBRATION_BINS), CALIBRATION_BINS - 1)].append(
            (probability, outcome)
        )
    result.update(
        positives=sum(y for _, y in pairs),
        brier=math.fsum((p - y) ** 2 for p, y in pairs) / n if n else None,
        log_loss=(
            -math.fsum(math.log(max(LOG_LOSS_FLOOR, p if y else 1 - p)) for p, y in pairs) / n
            if n
            else None
        ),
        calibration=[
            {
                "lower": i / CALIBRATION_BINS,
                "upper": (i + 1) / CALIBRATION_BINS,
                "n": len(group),
                "mean_prediction": math.fsum(p for p, _ in group) / len(group) if group else None,
                "observed_frequency": _ratio(sum(y for _, y in group), len(group)),
            }
            for i, group in enumerate(bins)
        ],
    )
    if study.threshold:
        cutoff = study.threshold.value
        tp = sum(p >= cutoff and y == 1 for p, y in pairs)
        fp = sum(p >= cutoff and y == 0 for p, y in pairs)
        fn = sum(p < cutoff and y == 1 for p, y in pairs)
        result["classification"] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": n - tp - fp - fn,
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn),
            "f1": _ratio(2 * tp, 2 * tp + fp + fn),
        }
    return result


def _outcome_status(observation: Observation | None, study: Study) -> str:
    if observation is None:
        return "missing"
    if observation.available_at < observation.end:
        return "premature"
    if observation.available_at > study.as_of:
        return "unavailable_as_of"
    if not observation.complete:
        return "incomplete"
    if observation.value is None:
        return "missing_value"
    maximum = 1 if study.contract.kind == "binary_probability" else 2**53 - 1
    if not 0 <= observation.value <= maximum:
        return "invalid_value"
    return "eligible"


def _prediction_status(prediction: Prediction | None, study: Study) -> str:
    if prediction is None:
        return "missing"
    if not (
        prediction.input_cutoff
        <= prediction.issued_at
        <= prediction.available_at
        <= prediction.case.origin
    ):
        return "invalid_timing"
    if prediction.value is None:
        return "missing_value"
    maximum = 1 if study.contract.kind == "binary_probability" else 2**53 - 1
    if not math.isfinite(prediction.value) or not 0 <= prediction.value <= maximum:
        return "invalid_value"
    return "eligible"


def evaluate(study: Study) -> dict:
    """Return a JSON-compatible report. Compare models only over their shared scored cases."""
    if not study.models or not study.cases:
        raise ValueError("the study requires at least one model and one panel case")
    if study.threshold and study.contract.kind != "binary_probability":
        raise ValueError("classification thresholds require binary probabilities")
    if len({(model.model, model.version) for model in study.models}) != len(study.models):
        raise ValueError("duplicate model/version")
    cases = _index([(case, i) for i, case in enumerate(study.cases)], "panel case")
    for case in cases:
        if not case.origin < case.start < case.end or case.origin > study.as_of:
            raise ValueError("panel case requires origin < start < end and origin <= as_of")
        if any(value.utcoffset() != timedelta(0) for value in (case.origin, case.start, case.end)):
            raise ValueError("panel times must use UTC")

    if any(row.contract != study.contract for row in study.observations):
        raise ValueError("incompatible observation contract")
    observations = _index(
        [((row.location, row.start, row.end), row) for row in study.observations], "observation"
    )
    panel_outcomes = [(case.location, case.start, case.end) for case in cases]
    observed = [observations.get(key) for key in panel_outcomes]
    outcome_statuses = [
        "window_open_as_of" if case.end > study.as_of else _outcome_status(row, study)
        for case, row in zip(cases, observed, strict=True)
    ]
    models = []
    scored = []
    for model in study.models:
        if any(row.contract != study.contract for row in model.predictions):
            raise ValueError("incompatible prediction contract")
        predictions = _index([(row.case, row) for row in model.predictions], "prediction")
        pairs = {}
        statuses: Counter[str] = Counter()
        records = []
        for case, outcome, outcome_status in zip(cases, observed, outcome_statuses, strict=True):
            prediction = predictions.get(case)
            status = _prediction_status(prediction, study)
            statuses[status] += 1
            records.append(
                {"record_id": prediction.record_id if prediction else None, "status": status}
            )
            if status == outcome_status == "eligible":
                assert prediction is not None and prediction.value is not None
                assert outcome is not None and outcome.value is not None
                pairs[cases[case]] = prediction.value, outcome.value
        scored.append(pairs)
        models.append(
            {
                "model": model.model,
                "version": model.version,
                "snapshot": model.snapshot,
                "prediction_statuses": dict(statuses),
                "outside_panel": sum(case not in cases for case in predictions),
                "prediction_coverage": statuses["eligible"] / len(cases),
                "scored_coverage": len(pairs) / len(cases),
                "metrics": _metrics(list(pairs.values()), study),
                "records": records,
            }
        )

    comparison = None
    if len(models) > 1:
        shared = sorted(set.intersection(*(set(pairs) for pairs in scored)))
        comparison = {
            "case_indices": shared,
            "n": len(shared),
            "coverage": len(shared) / len(cases),
            "status": "comparable" if shared else "no_shared_cases",
            "models": [
                {
                    "model": model.model,
                    "version": model.version,
                    "metrics": _metrics([pairs[i] for i in shared], study),
                }
                for model, pairs in zip(study.models, scored, strict=True)
            ]
            if shared
            else [],
        }

    return {
        "schema_version": 1,
        "data_kind": study.data_kind,
        "contract": study.contract.model_dump(mode="json"),
        "methodology": {
            "weighting": "equal_per_panel_case",
            "match": "exact_contract_location_origin_and_target_window_for_predictions",
            "target_window": "[start, end)",
            "log_loss_floor": LOG_LOSS_FLOOR,
            "calibration_bins": CALIBRATION_BINS,
            "small_sample_below": SMALL_SAMPLE,
            "threshold_rule": "probability_greater_than_or_equal",
            "threshold": study.threshold.model_dump(mode="json") if study.threshold else None,
        },
        "provenance": {
            "as_of": study.as_of.isoformat(),
            "panel_snapshot": study.panel_snapshot,
            "outcome_snapshot": study.outcome_snapshot,
        },
        "coverage": {
            "panel_n": len(cases),
            "outcome_statuses": dict(Counter(outcome_statuses)),
            "outcome_coverage": outcome_statuses.count("eligible") / len(cases),
            "outside_panel_observations": len(observations.keys() - set(panel_outcomes)),
        },
        "panel": [
            {
                **case.model_dump(mode="json"),
                "outcome_record_id": row.record_id if row else None,
                "outcome_status": status,
            }
            for case, row, status in zip(cases, observed, outcome_statuses, strict=True)
        ],
        "models": models,
        "comparison": comparison,
        "limitations": [
            "Availability, source vintage, horizon semantics and coverage require upstream audit.",
            "Complete-case scores can be biased by selective missingness.",
            "Scores are descriptive. Overlapping windows can produce dependent samples.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path, help="local study JSON file")
    args = parser.parse_args()
    try:
        study = Study.model_validate_json(args.study.read_bytes())
        print(json.dumps(evaluate(study), indent=2, sort_keys=True, allow_nan=False))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
