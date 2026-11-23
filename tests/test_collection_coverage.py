from datetime import UTC, datetime, timedelta

import httpx
import pytest

from geointel.connectors.acled import ACLEDConnector
from geointel.connectors.ucdp import UCDPConnector
from geointel.coverage import CoverageDecision, CoverageState, assess_record
from geointel.domain.models import AnalysisRun, Event
from geointel.domain.schemas import (
    AnalysisRequest,
    NormalizedForecastSignal,
    NormalizedOperationalEvent,
)
from geointel.monitoring.data_quality import source_health_report
from geointel.pipeline.service import AnalysisPipeline
from geointel.providers.base import ModelRouter
from geointel.providers.offline import OfflineModel

NOW = datetime(2026, 11, 23, 12, tzinfo=UTC)
REQUEST = AnalysisRequest(location="Spain", question="Assess conflict risks", horizon_months=12)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


class OAuth:
    def access_token(self):
        return "offline-token"


def run_with(session, *connectors):
    model = OfflineModel()
    return AnalysisPipeline(session, ModelRouter(model, model, model), list(connectors)).run(
        REQUEST
    )


def load_collection(session, analysis_id):
    session.expire_all()
    run = session.get(AnalysisRun, analysis_id)
    return run, CoverageDecision.from_metadata(run.collection_metadata).collections[0]


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr("geointel.connectors.acled.datetime", Clock)
    monkeypatch.setattr("geointel.pipeline.service.datetime", Clock)


@pytest.mark.parametrize(
    ("envelope", "state", "confirmed"),
    [
        (
            {"next_cursor": None, "data_query_restrictions": {"date_recency": "unrestricted"}},
            CoverageState.COMPLETE_EMPTY,
            0,
        ),
        ({"next_cursor": None}, CoverageState.UNKNOWN, None),
        (
            {"data_query_restrictions": {"date_recency": "unrestricted"}},
            CoverageState.UNKNOWN,
            None,
        ),
    ],
)
def test_empty_event_query(session, clock, envelope, state, confirmed):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": [], **envelope}))
    ) as client:
        connector = ACLEDConnector(
            "https://example.test", None, client=client, official_api=True, oauth=OAuth()
        )
        run, decision = load_collection(session, run_with(session, connector).id)
    assert decision.state == state
    assert decision.event_counts.confirmed == confirmed
    assert decision.event_counts.retrieved == 0
    assert run.collection_metadata["recent_event_count"] == 0
    report = source_health_report(session, run.id, as_of=NOW)
    assert report["sources"]["ACLED"]["collection_coverage"]["collections"] == [
        decision.model_dump(mode="json")
    ]


@pytest.mark.parametrize("last_page", ["failure", "repeated_cursor", "restriction", "complete"])
def test_acled_preserves_rows_and_audits_scope(session, clock, last_page):
    row = {
        "event_id_cnty": "es-1",
        "event_date": "2026-11-22",
        "event_type": "Battles",
        "country": "Spain",
    }

    def handler(request):
        if request.url.params["cursor"] == "0":
            return httpx.Response(200, json={"data": [row], "next_cursor": "next"})
        if last_page == "failure":
            return httpx.Response(503)
        if last_page == "repeated_cursor":
            return httpx.Response(200, json={"data": [row], "next_cursor": "next"})
        return httpx.Response(
            200,
            json={
                "data": [],
                "next_cursor": None,
                "data_query_restrictions": {"date_recency": {"quantity": 12, "unit": "Months"}},
            },
        )

    def complete_handler(_):
        return httpx.Response(
            200,
            json={
                "data": [row, row],
                "next_cursor": None,
                "data_query_restrictions": {"date_recency": "unrestricted"},
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(complete_handler if last_page == "complete" else handler)
    ) as client:
        connector = ACLEDConnector(
            "https://example.test", None, client=client, official_api=True, oauth=OAuth(), retries=0
        )
        run, decision = load_collection(session, run_with(session, connector).id)
    assert decision.state == (
        CoverageState.COMPLETE_WITH_RECORDS if last_page == "complete" else CoverageState.PARTIAL
    )
    assert decision.event_counts.eligible == 1
    assert decision.event_counts.duplicate == int(last_page in {"repeated_cursor", "complete"})
    assert decision.event_counts.confirmed is None
    assert session.query(Event).filter_by(analysis_run_id=run.id).count() == 1
    assert bool(decision.error_causes) == (last_page != "complete")
    assert run.collection_metadata["connector_outcomes"][0]["succeeded"] is True


def test_geography_and_forecast_target_are_independent():
    event = NormalizedOperationalEvent(
        source_record_id="1",
        event_date=NOW,
        event_type="Battles",
        country="Unmapped",
        retrieved_at=NOW,
    )
    event_decision = assess_record(event, "Unmapped", NOW, 12)
    assert event_decision.geography == "unknown"
    assert event_decision.observation_time == "pass"
    assert event_decision.publication_freshness == "unknown"
    assert event_decision.eligible is False

    signal = NormalizedForecastSignal(
        source_record_id="f",
        model_name="test",
        geographic_unit="country",
        location="Spain",
        issue_date=NOW - timedelta(days=30),
        target_start=NOW - timedelta(days=29),
        target_end=NOW - timedelta(days=1),
        prediction=0,
        target_variable="events",
        retrieved_at=NOW,
    )
    expired = assess_record(signal, "Spain", NOW, 12)
    assert expired.geography == expired.forecast_issuance == "pass"
    assert expired.forecast_target == "fail"
    assert expired.eligible is False


def test_historical_release_is_separate_from_operational_window(session, clock):
    def handler(_):
        return httpx.Response(
            200,
            json={
                "TotalPages": 1,
                "TotalCount": 1,
                "Result": [
                    {
                        "id": 3,
                        "country": "Spain",
                        "country_id": 230,
                        "date_start": "2026-11-22",
                    }
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        connector = UCDPConnector(
            "https://example.test", "25.1", client=client, official_api=True, access_token="fixture"
        )
        run, decision = load_collection(session, run_with(session, connector).id)
    assert decision.state == CoverageState.COMPLETE_WITH_RECORDS
    assert decision.verified_scope.kind == "historical_release"
    assert decision.provider_release == "25.1"
    assert decision.verified_scope.start is decision.verified_scope.end is None
    assert not run.analyst_output["observed_evidence"]
    assert decision.event_counts.confirmed is None
    assert run.collection_metadata["historical_conflict_coverage_available"] is True
    assert run.collection_metadata["current_operational_coverage_available"] is False


def test_legacy_success_and_multiple_invocations(session, clock):
    legacy = {"connector_outcomes": [{"connector": "ACLED", "succeeded": True, "record_count": 0}]}
    assert CoverageDecision.from_metadata(legacy).projection("ACLED")["state"] == "unknown"

    class Unaudited:
        connector_name = "ACLED"

        def collect(self, location, horizon_months):
            return []

    connector = Unaudited()
    run = run_with(session, connector, connector)
    coverage = CoverageDecision.from_metadata(run.collection_metadata)
    assert len({item.collection_id for item in coverage.collections}) == 2
    assert all(item.state == CoverageState.UNKNOWN for item in coverage.collections)
    assert all(item.event_counts.confirmed is None for item in coverage.collections)
    assert run.collection_metadata["external_collection_succeeded"] is True


def test_verified_narrower_query_cannot_produce_assessment_zero(session, clock, monkeypatch):
    class EarlierQueryClock(Clock):
        @classmethod
        def now(cls, tz=None):
            return super().now(tz) - timedelta(days=1)

    monkeypatch.setattr("geointel.connectors.acled.datetime", EarlierQueryClock)
    envelope = {
        "data": [],
        "next_cursor": None,
        "data_query_restrictions": {"date_recency": "unrestricted"},
    }
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=envelope))
    ) as client:
        connector = ACLEDConnector(
            "https://example.test", None, client=client, official_api=True, oauth=OAuth()
        )
        _, decision = load_collection(session, run_with(session, connector).id)
    assert decision.state == CoverageState.COMPLETE_EMPTY
    assert decision.verified_scope == decision.actual_query_scope
    assert decision.verified_scope != decision.requested_scope
    assert "assessment_scope_unverified" in decision.gaps
    assert decision.event_counts.confirmed is None


@pytest.mark.parametrize(
    ("page", "state"),
    [
        ({"TotalPages": 0, "TotalCount": 0, "Result": []}, CoverageState.COMPLETE_EMPTY),
        ({"TotalPages": 0, "Result": []}, CoverageState.UNKNOWN),
    ],
)
def test_empty_historical_release_never_confirms_operational_zero(session, clock, page, state):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=page))
    ) as client:
        connector = UCDPConnector(
            "https://example.test", "25.1", client=client, official_api=True, access_token="fixture"
        )
        run, decision = load_collection(session, run_with(session, connector).id)
    assert decision.state == state
    assert decision.event_counts.confirmed is None
    assert not run.collection_metadata["historical_observation_count"]
    if state == CoverageState.COMPLETE_EMPTY:
        assert decision.verified_scope.kind == "historical_release"
        assert decision.verified_scope.start is decision.verified_scope.end is None


def test_ineligible_events_are_persisted_but_excluded_from_reasoning(session, clock):
    rows = [
        {"event_id_cnty": "stale", "event_date": "2020-01-01", "country": "Spain"},
        {"event_id_cnty": "other", "event_date": "2026-11-22", "country": "France"},
    ]
    payload = {"data": [dict(row, event_type="Battles") for row in rows]}
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        connector = ACLEDConnector(
            "https://example.test", None, client=client, official_api=True, oauth=OAuth()
        )
        run, receipt = load_collection(session, run_with(session, connector).id)
    assert {event.source_record_id for event in run.events} == {"stale", "other"}
    assert receipt.event_counts.eligible == 0
    assert receipt.event_counts.confirmed is None
    assert all("excluded from assessment" in item for item in run.analyst_output["recent_events"])
    assert len(run.analyst_output["recent_events"]) == 2
