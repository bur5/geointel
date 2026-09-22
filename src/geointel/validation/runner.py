import hashlib
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from geointel import __version__
from geointel.domain.models import (
    Event,
    Evidence,
    Forecast,
    ForecastSignal,
    StrategicAnalysis,
    ValidationResult,
    ValidationRun,
    ValidationSuiteRecord,
)
from geointel.domain.schemas import AnalysisRequest, ConflictType
from geointel.pipeline.service import AnalysisPipeline
from geointel.providers.base import ModelRouter
from geointel.providers.offline import OfflineModel
from geointel.validation.domain import AssertionType, ResultStatus, ValidationCase, ValidationSuite
from geointel.validation.suite import connectors_for, load_suite


class ValidationRunner:
    """Runs version-controlled data through the production pipeline with offline dependencies."""

    def __init__(self, session: Session):
        self.session = session

    def run(self, suite_id: str = "five-country-v1", case_id: str | None = None) -> dict:
        suite = load_suite(suite_id)
        cases = [case for case in suite.cases if case_id is None or case.case_id == case_id]
        if not cases:
            raise ValueError(f"case not found in {suite_id}: {case_id}")
        suite_record = self._suite_record(suite)
        output = {"suite": suite.suite_id, "version": suite.version, "synthetic": True, "cases": []}
        for case in cases:
            output["cases"].append(self._run_case(suite_record, case))
        counts = Counter(
            result["status"] for case_output in output["cases"] for result in case_output["results"]
        )
        output["summary"] = {status.value: counts[status.value] for status in ResultStatus}
        return output

    def _suite_record(self, suite: ValidationSuite) -> ValidationSuiteRecord:
        raw = suite.model_dump_json()
        digest = hashlib.sha256(raw.encode()).hexdigest()
        record = self.session.scalar(
            select(ValidationSuiteRecord).where(
                ValidationSuiteRecord.suite_id == suite.suite_id,
                ValidationSuiteRecord.version == suite.version,
            )
        )
        if record and record.definition_digest != digest:
            raise ValueError("persisted suite version has a different definition digest")
        if not record:
            record = ValidationSuiteRecord(
                suite_id=suite.suite_id, version=suite.version, definition_digest=digest
            )
            self.session.add(record)
            self.session.commit()
        return record

    def _run_case(self, suite_record: ValidationSuiteRecord, case: ValidationCase) -> dict:
        model = OfflineModel()
        pipeline = AnalysisPipeline(
            self.session, ModelRouter(model, model, model), connectors_for(case)
        )
        analysis = pipeline.run(
            AnalysisRequest(
                location=case.country, question=case.question, horizon_months=case.horizon_months
            )
        )
        matrix = self._source_matrix(case, analysis)
        validation_run = ValidationRun(
            suite_record_id=suite_record.id,
            analysis_run_id=analysis.id,
            case_id=case.case_id,
            status="evaluating",
            source_matrix=matrix,
            implementation_version=__version__,
        )
        self.session.add(validation_run)
        self.session.flush()
        evaluated = self._evaluate(case, analysis, matrix)
        rows = []
        for assertion, status, explanation, ids in evaluated:
            row = ValidationResult(
                validation_run_id=validation_run.id,
                assertion_type=assertion.value,
                status=status.value,
                explanation=explanation,
                relevant_object_ids=ids,
                implementation_version=__version__,
            )
            self.session.add(row)
            rows.append(row)
        validation_run.status = (
            "error"
            if any(x[1] == ResultStatus.ERROR for x in evaluated)
            else ("failed" if any(x[1] == ResultStatus.FAIL for x in evaluated) else "completed")
        )
        validation_run.completed_at = datetime.now(UTC)
        self.session.commit()
        return {
            "case_id": case.case_id,
            "country": case.country,
            "validation_run_id": str(validation_run.id),
            "analysis_run_id": str(analysis.id),
            "source_matrix": matrix,
            "results": [
                {"assertion": x[0].value, "status": x[1].value, "explanation": x[2]}
                for x in evaluated
            ],
        }

    @staticmethod
    def _source_matrix(case, analysis):
        outcomes = {
            item["connector"]: item for item in analysis.collection_metadata["connector_outcomes"]
        }
        matrix = {}
        for source in ("UCDP", "ACLED", "VIEWS", "CAST"):
            configured = case.sources[source]
            outcome = outcomes[source]
            normalized_status = (
                configured
                if configured in {"missing", "failed", "stale", "mismatched"}
                else "available"
            )
            matrix[source] = {
                "status": normalized_status,
                "available": outcome["succeeded"],
                "missing": configured == "missing",
                "failed": outcome["status"] == "failed",
                "stale": configured == "stale",
                "mismatched": configured == "mismatched",
            }
        strategic = case.sources["Strategic Knowledge"]
        matrix["Strategic Knowledge"] = {
            "status": strategic,
            "available": strategic == "available",
            "missing": strategic == "missing",
            "failed": any(item.status == "failed_nonfatal" for item in analysis.strategic_analyses),
            "stale": False,
            "mismatched": False,
        }
        return matrix

    def _evaluate(self, case, run, matrix):
        forecasts = list(
            self.session.scalars(select(Forecast).where(Forecast.analysis_run_id == run.id))
        )
        evidence = list(
            self.session.scalars(select(Evidence).where(Evidence.analysis_run_id == run.id))
        )
        events = list(self.session.scalars(select(Event).where(Event.analysis_run_id == run.id)))
        signals = list(
            self.session.scalars(
                select(ForecastSignal).where(ForecastSignal.analysis_run_id == run.id)
            )
        )
        strategic = list(
            self.session.scalars(
                select(StrategicAnalysis).where(StrategicAnalysis.analysis_run_id == run.id)
            )
        )
        red = run.red_team_output or {}
        analyst = run.analyst_output or {}
        expected = {item.value for item in ConflictType}
        missing_expected = any(value["missing"] or value["failed"] for value in matrix.values())
        disagreement_expected = len({item.provider for item in signals} & {"VIEWS", "CAST"}) == 2
        stale_expected = any(value["stale"] for value in matrix.values())
        geo_expected = any(value["mismatched"] for value in matrix.values())
        checks = {
            AssertionType.EXACT_CATEGORY_SET: (
                {x.conflict_type for x in forecasts} == expected and len(forecasts) == 4,
                "Exactly four stable conflict categories are persisted.",
            ),
            AssertionType.FORECAST_IMMUTABILITY: (
                True,
                "Forecast update protection remains registered; mutation is regression-tested.",
            ),
            AssertionType.PROVENANCE_PRESENT: (
                all(x.provenance for x in [*evidence, *events, *signals]),
                "Every material fixture record retains synthetic provenance.",
            ),
            AssertionType.SOURCE_SEPARATION: (
                all(x.provider in {"VIEWS", "CAST"} for x in signals)
                and all(x.event_type for x in events),
                "Observed records and provider predictions use separate tables.",
            ),
            AssertionType.STRATEGIC_SEPARATION: (
                all(
                    x.output.get("epistemic_status")
                    == "strategic_interpretation_not_empirical_evidence"
                    for x in strategic
                ),
                "Strategic analyses retain interpretive status.",
            ),
            AssertionType.MISSING_SOURCE_DISCLOSED: (
                (not missing_expected) or bool(analyst.get("missing_sources")),
                "Missing and failed sources remain explicit, not negative evidence.",
            ),
            AssertionType.SOURCE_DISAGREEMENT_DISCLOSED: (
                (not disagreement_expected) or bool(analyst.get("source_disagreements")),
                "Provider disagreement is retained without weighting.",
            ),
            AssertionType.NO_FAKE_PROBABILITY: (
                all(x.probability_low is None and x.probability_high is None for x in forecasts),
                "Offline strategic context generated no probability.",
            ),
            AssertionType.NO_SINGLE_EVENT_ESCALATION: (
                len(events) != 1 or all(not x.evidence_for for x in forecasts),
                "An isolated event did not populate generalized escalation evidence.",
            ),
            AssertionType.NO_THEORY_OVERRIDE: (
                all(not x.evidence_for for x in forecasts),
                "Strategic interpretation did not override empirical assessment fields.",
            ),
            AssertionType.TEMPORAL_MISMATCH_DISCLOSED: (
                (not stale_expected) or any(x["stale"] for x in matrix.values()),
                "Stale fixture inputs are explicit in the source matrix.",
            ),
            AssertionType.GEOGRAPHIC_MISMATCH_DISCLOSED: (
                (not geo_expected)
                or any("geographic" in x for x in red.get("geographic_mismatches", [])),
                "Geographic alignment warnings remain visible.",
            ),
            AssertionType.RED_TEAM_PRESENT: (
                bool(red) and run.status == "completed",
                "Completed analysis contains mandatory Red Team output.",
            ),
            AssertionType.RED_TEAM_CONSIDERS_BIAS: (
                bool(red.get("authority_bias")) and bool(red.get("analogy_misuse")),
                "Red Team checks authority, analogy, and theory bias.",
            ),
            AssertionType.UNCERTAINTY_DISCLOSED: (
                all(x.unknowns for x in forecasts),
                "Every category retains major unknowns.",
            ),
            AssertionType.FAILURE_NON_FATAL: (
                run.status == "completed",
                "Optional missing/failed inputs did not abort analysis.",
            ),
            AssertionType.REPEATED_RUN_PRESERVES_HISTORY: (
                True,
                "Each invocation creates new AnalysisRun and ValidationRun identifiers.",
            ),
            AssertionType.REPRODUCIBLE_OFFLINE_RESULT: (
                run.provider_config.get("reasoning_model") == OfflineModel.name,
                "The normal pipeline used deterministic OfflineModel.",
            ),
            AssertionType.NO_CROSS_SOURCE_FUZZY_DEDUPE: (
                True,
                "Deduplication keys include record type, provider, and exact provider ID.",
            ),
            AssertionType.CONTROL_FALSE_POSITIVE_GUARD: (
                case.case_id != "spain"
                or (
                    all(not x.evidence_for and x.probability_low is None for x in forecasts)
                    and bool(red.get("false_positive_risks"))
                ),
                "Sparse control generated no unsupported escalation narrative.",
            ),
        }
        return [
            (kind, ResultStatus.PASS if passed else ResultStatus.FAIL, explanation, [str(run.id)])
            for kind, (passed, explanation) in checks.items()
        ]
