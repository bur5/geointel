from datetime import UTC, datetime

import httpx
import pytest

from geointel.connectors.newsapi import NewsAPIConnector, NewsAPIError
from geointel.news.corroboration import CorroborationStatus, assess_cluster, cluster_reports
from geointel.news.query import QUERY_PLAN_VERSION, plan_news_queries
from geointel.providers.runtime import FailureCategory, HardenedTransport

NOW = datetime(2026, 9, 23, 12, tzinfo=UTC)
SECRET = "never-render-this-key"


def article(url="https://example.com/a?utm_source=x", title="Report"):
    return {
        "source": {"id": "example", "name": "Example"},
        "author": "Reporter",
        "title": title,
        "description": "Untrusted media text",
        "url": url,
        "publishedAt": "2026-09-21T12:00:00Z",
    }


def connector(pages, *, statuses=None, requests=None, **bounds):
    bounds.setdefault("request_budget", 1)
    calls = [] if requests is None else requests

    def handler(request):
        calls.append(request)
        index = len(calls) - 1
        status = statuses[index] if statuses else 200
        return httpx.Response(status, json=pages[index], request=request)

    transport = HardenedTransport(
        client=httpx.Client(transport=httpx.MockTransport(handler)), retries=0
    )
    return NewsAPIConnector(
        "https://newsapi.org",
        SECRET,
        transport=transport,
        now=lambda: NOW,
        **bounds,
    )


def test_official_contract_header_window_normalization_and_secret_safety():
    requests = []
    news = connector(
        [{"status": "ok", "totalResults": 1, "articles": [article()]}], requests=requests
    )
    reports = news.collect("Spain", 12)
    request = requests[0]
    assert request.headers["X-Api-Key"] == SECRET
    assert SECRET not in str(request.url)
    assert request.url.path == "/v2/everything"
    assert request.url.params["from"] == "2026-09-15T12:00:00+00:00"
    assert request.url.params["to"] == "2026-09-22T12:00:00+00:00"
    assert reports[0].provider == "NEWSAPI"
    assert reports[0].publication_timestamp != reports[0].retrieval_timestamp
    assert reports[0].temporal_classification == "publication_timestamp_not_event_date"
    assert SECRET not in str(news.last_audit.public())


def test_pagination_record_and_request_bounds_are_truncated():
    payload = {"status": "ok", "totalResults": 99, "articles": [article()]}
    news = connector([payload, payload], max_pages=5, request_budget=2, max_records=10)
    assert len(news.collect("Spain")) == 1
    assert news.last_audit.request_count == 2
    assert news.last_audit.page_count == 2
    assert news.last_audit.duplicates == 1
    assert news.last_audit.truncated is True


@pytest.mark.parametrize(
    "code,status,category",
    [
        ("apiKeyInvalid", 401, FailureCategory.AUTHENTICATION_ERROR),
        ("apiKeyExhausted", 429, FailureCategory.QUOTA_EXHAUSTED),
        ("rateLimited", 429, FailureCategory.RATE_LIMITED),
        ("parameterInvalid", 400, FailureCategory.INVALID_REQUEST),
        ("unexpectedError", 500, FailureCategory.PROVIDER_5XX),
    ],
)
def test_documented_error_mapping_is_body_and_secret_safe(code, status, category):
    news = connector([{"status": "error", "code": code, "message": SECRET}], statuses=[status])
    with pytest.raises(NewsAPIError) as exc:
        news.collect("Spain")
    assert exc.value.category == category
    assert SECRET not in str(exc.value)
    assert SECRET not in str(news.last_audit.public())


@pytest.mark.parametrize(
    "bad",
    [
        {"url": "", "title": "x", "publishedAt": "2026-09-21T00:00:00Z"},
        {"url": "https://e.test/a", "title": "x"},
        {"url": "https://e.test/a", "title": "x", "publishedAt": "bad"},
    ],
)
def test_malformed_articles_are_rejected(bad):
    news = connector([{"status": "ok", "totalResults": 1, "articles": [bad]}])
    assert news.collect("Spain") == []
    assert news.last_audit.rejected == 1


def test_exact_cross_provider_identity_clusters_but_ambiguous_titles_do_not():
    news = connector(
        [
            {
                "status": "ok",
                "totalResults": 2,
                "articles": [article(), article("https://other.test/b", "Report")],
            }
        ]
    )
    reports = news.collect("Spain")
    gdelt_copy = reports[0].model_copy(update={"provider": "GDELT", "source_record_id": "g"})
    clusters = cluster_reports([*reports, gdelt_copy])
    assert len(clusters) == 2
    duplicate = next(x for x in clusters if len(x.member_report_ids) == 2)
    assessment = assess_cluster(duplicate, [*reports, gdelt_copy], assessed_at=NOW)
    assert assessment.status == CorroborationStatus.LIKELY_SYNDICATED
    assert assessment.independent_chain_count == 0
    assert assessment.candidate_indicator_eligible is False


def test_query_plan_is_deterministic_bounded_and_not_evidence():
    first = plan_news_queries("Spain", request_budget=3)
    second = plan_news_queries("Spain", request_budget=3)
    assert first == second
    assert first.version == QUERY_PLAN_VERSION
    assert len(first.queries) == 3
    assert len(first.queries) <= first.request_budget
    assert all("Spain" in item.query_text for item in first.queries)
    assert first.boundary == "discovery_instructions_not_article_content_or_evidence"
