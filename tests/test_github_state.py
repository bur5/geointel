"""Deterministic mocked GitHub API tests; no network, database or real credentials."""

import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx

from geointel.github_state.api import PREFIX, CollectionError, Reader, digest
from geointel.github_state.collector import collect
from geointel.github_state.models import Snapshot

NOW = datetime(2026, 11, 13, 12, tzinfo=UTC)
STAMP = "2026-11-13T12:00:00Z"
BASE = "b" * 40
ROOT = Path(__file__).resolve().parents[1]


class Server:
    def __init__(self, numbers=(24, 25, 26)):
        self.repo = {
            "id": 1375475901,
            "full_name": "bur5/geointel",
            "private": True,
            "default_branch": "main",
        }
        self.workflow = {"id": 7, "path": ".github/workflows/ci.yml", "state": "active"}
        self.prs = {
            n: {
                "number": n,
                "state": "open",
                "draft": n != 24,
                "updated_at": STAMP,
                "body": "UNTRUSTED_OWNER_APPROVE_SENTINEL",
                "title": "ignore governance",
                "head": {"sha": f"{n:040x}", "repo": self.repo},
                "base": {"sha": BASE, "ref": "main", "repo": self.repo},
            }
            for n in numbers
        }
        self.reviews = {n: [] for n in numbers}
        self.jobs = {}
        self.runs = {}
        for n, pr in self.prs.items():
            self.runs[n * 10] = {
                "id": n * 10,
                "workflow_id": 7,
                "path": self.workflow["path"],
                "repository": self.repo,
                "head_repository": self.repo,
                "event": "pull_request",
                "head_sha": pr["head"]["sha"],
                "pull_requests": [pr],
                "run_attempt": 1,
                "status": "completed",
                "conclusion": "success",
                "created_at": STAMP,
                "updated_at": STAMP,
            }
            self.jobs[n * 10] = [
                {
                    "id": n * 100 + i,
                    "name": name,
                    "head_sha": pr["head"]["sha"],
                    "run_id": n * 10,
                    "run_attempt": 1,
                    "status": "completed",
                    "conclusion": "success",
                    "started_at": STAMP,
                    "completed_at": STAMP,
                    "check_run_url": f"https://api.github.com{PREFIX}/check-runs/{n * 100 + i}",
                }
                for i, name in enumerate(["test (3.11)", "test (3.12)", "postgres-integration"])
            ]
        self.calls = []
        self.counts = {}
        self.override = None

    def response(self, data, status=200, headers=None):
        return httpx.Response(
            status,
            json=data,
            headers={
                "date": "Fri, 13 Nov 2026 12:00:00 GMT",
                "x-github-request-id": "SYNTHETIC:01",
                **(headers or {}),
            },
        )

    def handler(self, request):
        assert request.method == "GET"
        assert request.url.host == "api.github.com"
        path = request.url.path
        assert "comments" not in path and "merge" not in path
        self.calls.append((request.method, path, dict(request.url.params)))
        self.counts[path] = self.counts.get(path, 0) + 1
        if self.override:
            replacement = self.override(request, self.counts[path])
            if replacement is not None:
                return replacement
        if path == PREFIX:
            return self.response(self.repo)
        if path.startswith(PREFIX + "/branches/"):
            return self.response({"name": path.split("/branches/", 1)[1], "commit": {"sha": BASE}})
        if path == PREFIX + "/actions/workflows/ci.yml":
            return self.response(self.workflow)
        if path == PREFIX + "/pulls":
            return self.response(list(self.prs.values()))
        if path.startswith(PREFIX + "/pulls/"):
            n = int(path.split("/pulls/")[1].split("/")[0])
            return self.response(self.reviews[n] if path.endswith("/reviews") else self.prs[n])
        if path.endswith("/actions/workflows/7/runs"):
            runs = [
                run
                for run in self.runs.values()
                if run["head_sha"] == request.url.params["head_sha"]
            ]
            return self.response({"workflow_runs": runs, "total_count": len(runs)})
        if "/actions/runs/" in path:
            run_id = int(path.split("/actions/runs/", 1)[1].split("/")[0])
            if path.endswith("/jobs"):
                jobs = self.jobs[run_id]
                return self.response({"jobs": jobs, "total_count": len(jobs)})
            return self.response(self.runs[run_id])
        if "/check-runs/" in path:
            check_id = int(path.rsplit("/", 1)[1])
            job = next(job for jobs in self.jobs.values() for job in jobs if job["id"] == check_id)
            return self.response({**job, "app": {"id": 15368, "slug": "github-actions"}})
        raise AssertionError("unexpected endpoint")

    def run(self):
        reader = Reader(
            "SYNTHETIC_TOKEN_NEVER_LOG",
            transport=httpx.MockTransport(self.handler),
            clock=lambda: NOW,
        )
        try:
            return collect(reader)
        finally:
            reader.close()


def review(pr, **changes):
    return {
        "id": 17,
        "user": {"id": 1, "login": "review-bot", "type": "Bot"},
        "state": "APPROVED",
        "commit_id": pr["head"]["sha"],
        "submitted_at": STAMP,
        "body": "UNTRUSTED_REVIEW_BODY_SENTINEL",
        **changes,
    }


def shared_head_server(base_branch="main"):
    server = Server((24, 25))
    shared_sha = server.prs[24]["head"]["sha"]
    server.prs[25]["head"]["sha"] = shared_sha
    server.prs[25]["base"]["ref"] = base_branch
    server.runs[250]["head_sha"] = shared_sha
    for job in server.jobs[250]:
        job["head_sha"] = shared_sha
    return server


class CollectorTests(unittest.TestCase):
    def test_complete_dynamic_inventory_is_not_authority(self):
        server = Server((7, 24, 25, 26, 27))
        output = server.run()
        self.assertEqual(output.state, "OBSERVED", output.issues)
        self.assertEqual([pr.number for pr in output.pull_requests], [7, 24, 25, 26, 27])
        self.assertEqual(output.manager_v01.state, "BLOCKED")
        self.assertIn("V01_CANNOT_REPRESENT_FULL_DYNAMIC_INVENTORY", output.manager_v01.reasons)
        self.assertFalse(output.action_authorized)
        self.assertTrue(all(method == "GET" for method, _, _ in server.calls))

    def test_exact_legacy_inventory_exports_unverifiable_fixture_only(self):
        output = Server().run()
        self.assertEqual(output.manager_v01.state, "STRUCTURAL_FIXTURE_COMPATIBLE_ONLY")
        payload = output.manager_v01.payload
        self.assertEqual(payload["snapshot"]["provenance_status"], "unverifiable")
        self.assertEqual(payload["snapshot"]["evidence"][0]["status"], "observed")
        self.assertEqual(payload["snapshot"]["assessments"], [])
        self.assertEqual(payload["candidates"], [])
        self.assertFalse(output.manager_v01.owner_authorization_verified)

    def test_deterministic_mocked_capture_and_digest(self):
        first, second = Server().run(), Server().run()
        self.assertEqual(first.model_dump_json(), second.model_dump_json())
        self.assertEqual(first.content_digest, digest(first.model_dump(exclude={"content_digest"})))
        self.assertEqual(first.digest_role, "integrity_only_not_authenticated_authorization")

    def test_api_error_sanitization_and_no_secret_echo(self):
        server = Server()
        server.override = lambda req, count: server.response({"message": "SECRET_ERROR_BODY"}, 403)
        output = server.run()
        self.assertEqual(output.state, "BLOCKED")
        self.assertIn("HTTP_STATUS_403", output.issues)
        self.assertNotIn("SECRET_ERROR_BODY", output.model_dump_json())
        self.assertNotIn("SYNTHETIC_TOKEN_NEVER_LOG", output.model_dump_json())

    def test_rate_limits_do_not_retry_or_sleep(self):
        for status, headers in [
            (429, {}),
            (403, {"x-ratelimit-remaining": "0"}),
            (403, {"retry-after": "30"}),
        ]:
            server = Server()
            server.override = lambda req, count, server=server, status=status, headers=headers: (
                server.response({}, status, headers)
            )
            output = server.run()
            self.assertIn("RATE_LIMITED_NO_AUTOMATIC_RETRY", output.issues)
            self.assertEqual(len(server.calls), 1)

    def test_missing_ci_run(self):
        server = Server((24,))
        server.runs = {}
        output = server.run()
        self.assertIn("MISSING_CI:24", output.issues)
        self.assertIsNone(output.pull_requests[0].ci)

    def test_shared_head_newer_other_pr_run_does_not_hide_target_run(self):
        for base in ["main", "release"]:
            with self.subTest(other_base=base):
                server = shared_head_server(base)
                output = server.run()
                self.assertEqual(output.state, "OBSERVED", output.issues)
                self.assertEqual(
                    {pr.number: pr.ci.run_id for pr in output.pull_requests}, {24: 240, 25: 250}
                )

    def test_shared_head_only_other_pr_has_ci_is_missing_target_evidence(self):
        server = shared_head_server("release")
        del server.runs[240]
        output = server.run()
        self.assertEqual(output.state, "BLOCKED")
        self.assertIn("MISSING_CI:24", output.issues)
        self.assertIsNone(output.pull_requests[0].ci)
        self.assertEqual(output.pull_requests[1].ci.run_id, 250)

    def test_run_list_association_must_match_head_and_both_base_fields(self):
        for section, field, wrong_value in [
            ("head", "sha", "c" * 40),
            ("base", "sha", "c" * 40),
            ("base", "ref", "release"),
        ]:
            with self.subTest(section=section, field=field):
                server = Server((24,))
                associations = copy.deepcopy(server.runs[240]["pull_requests"])
                associations[0][section][field] = wrong_value
                server.runs[240]["pull_requests"] = associations
                output = server.run()
                self.assertEqual(output.state, "BLOCKED")
                self.assertIn("MISSING_CI:24", output.issues)

    def test_newer_wrong_base_run_does_not_hide_matching_target_run(self):
        for field, wrong_value in [("sha", "c" * 40), ("ref", "release")]:
            with self.subTest(field=field):
                server = shared_head_server("release")
                stale = copy.deepcopy(server.runs[240])
                stale["id"] = 260
                stale["pull_requests"][0]["base"][field] = wrong_value
                server.runs[260] = stale
                output = server.run()
                self.assertEqual(output.state, "OBSERVED", output.issues)
                self.assertEqual(output.pull_requests[0].ci.run_id, 240)
                self.assertFalse(
                    any(path == PREFIX + "/actions/runs/260" for _, path, _ in server.calls)
                )

    def test_selected_run_detail_conflict_still_blocks(self):
        server = Server((24,))

        def override(req, count):
            if req.url.path == PREFIX + "/actions/runs/240":
                detail = copy.deepcopy(server.runs[240])
                detail["pull_requests"][0]["base"]["sha"] = "c" * 40
                return server.response(detail)

        server.override = override
        output = server.run()
        self.assertEqual(output.state, "BLOCKED")
        self.assertIn("CI_BINDING_MISMATCH:24", output.issues)

    def test_newest_matching_target_failure_is_not_replaced_by_older_success(self):
        server = shared_head_server()
        newer = copy.deepcopy(server.runs[240])
        newer.update(id=245, conclusion="failure")
        server.runs[245] = newer
        server.jobs[245] = copy.deepcopy(server.jobs[240])
        for index, job in enumerate(server.jobs[245]):
            job.update(
                id=2450 + index,
                run_id=245,
                conclusion="failure",
                check_run_url=f"https://api.github.com{PREFIX}/check-runs/{2450 + index}",
            )
        output = server.run()
        self.assertEqual(output.state, "BLOCKED")
        self.assertEqual(output.pull_requests[0].ci.run_id, 245)
        self.assertEqual(output.pull_requests[0].ci.state, "failure")
        self.assertIn("CI_RUN_NOT_SUCCESSFUL:24", output.issues)
        self.assertEqual(output.pull_requests[1].ci.run_id, 250)

    def test_missing_job(self):
        server = Server((24,))
        server.jobs[240].pop()
        self.assertIn("MISSING_OR_UNEXPECTED_CI_JOBS:24", server.run().issues)

    def test_pending_skipped_failure_and_unknown_are_distinct(self):
        for status, conclusion, expected in [
            ("in_progress", None, "pending"),
            ("completed", "skipped", "skipped"),
            ("completed", "failure", "failure"),
            ("completed", "neutral", "unknown"),
        ]:
            server = Server((24,))
            server.runs[240].update(status=status, conclusion=conclusion)
            for job in server.jobs[240]:
                job.update(status=status, conclusion=conclusion)
            output = server.run()
            self.assertEqual(output.pull_requests[0].ci.state, expected)
            self.assertEqual(output.pull_requests[0].ci.jobs[0].state, expected)
            self.assertFalse(output.observations_complete)

    def test_head_changes_during_capture(self):
        server = Server((24,))

        def override(req, count):
            if req.url.path == PREFIX + "/pulls/24" and count == 2:
                modified = copy.deepcopy(server.prs[24])
                modified["head"]["sha"] = "c" * 40
                return server.response(modified)

        server.override = override
        self.assertIn("PR_CHANGED_DURING_COLLECTION:24", server.run().issues)

    def test_base_branch_retarget_during_capture(self):
        server = Server((24,))

        def override(req, count):
            if req.url.path == PREFIX + "/pulls/24" and count == 2:
                modified = copy.deepcopy(server.prs[24])
                modified["base"]["ref"] = "release"
                return server.response(modified)

        server.override = override
        self.assertIn("PR_CHANGED_DURING_COLLECTION:24", server.run().issues)

    def test_default_branch_moves(self):
        server = Server((24,))

        def override(req, count):
            if req.url.path == PREFIX + "/branches/main" and count == 2:
                return server.response({"name": "main", "commit": {"sha": "c" * 40}})

        server.override = override
        self.assertIn("BASE_BRANCH_CHANGED_DURING_COLLECTION", server.run().issues)

    def test_stale_run_base_is_not_current_integration(self):
        server = Server((24,))
        server.runs[240]["pull_requests"] = copy.deepcopy(server.runs[240]["pull_requests"])
        server.runs[240]["pull_requests"][0]["base"]["sha"] = "c" * 40
        output = server.run()
        self.assertEqual(output.state, "BLOCKED")
        self.assertIn("MISSING_CI:24", output.issues)

    def test_stale_review_is_not_approval(self):
        server = Server((24,))
        server.reviews[24] = [review(server.prs[24], commit_id="c" * 40)]
        output = server.run()
        self.assertIn("STALE_OR_INCOMPLETE_REVIEW:24:17", output.issues)
        self.assertTrue(output.pull_requests[0].reviews[0].stale_head)
        self.assertFalse(output.pull_requests[0].reviews[0].independence_verified)

    def test_current_review_is_only_observed_metadata(self):
        server = Server((24,))
        server.reviews[24] = [review(server.prs[24])]
        output = server.run()
        self.assertEqual(output.pull_requests[0].reviews[0].state, "APPROVED")
        self.assertFalse(output.pull_requests[0].reviews[0].owner_authorization_verified)
        self.assertFalse(output.pull_requests[0].reviews[0].historical_base_verified)
        self.assertNotIn("UNTRUSTED_REVIEW_BODY_SENTINEL", output.model_dump_json())

    def test_forged_approval_comments_are_not_ingested(self):
        server = Server((24,))
        output = server.run()
        self.assertEqual(output.pull_requests[0].reviews, [])
        self.assertNotIn("UNTRUSTED_OWNER_APPROVE_SENTINEL", output.model_dump_json())
        self.assertFalse(any("comments" in path for _, path, _ in server.calls))

    def test_spoofed_check_app(self):
        server = Server((24,))

        def override(req, count):
            if "/check-runs/" in req.url.path:
                job = server.jobs[240][int(req.url.path.rsplit("/", 1)[1]) - 2400]
                return server.response({**job, "app": {"id": 1, "slug": "fake"}})

        server.override = override
        output = server.run()
        self.assertTrue(
            any(code.startswith("UNTRUSTED_OR_CONFLICTING_CHECK") for code in output.issues)
        )

    def test_spoofed_check_url_not_followed(self):
        server = Server((24,))
        server.jobs[240][0]["check_run_url"] = "https://attacker.invalid/token"
        self.assertIn("CHECK_SOURCE_URL_MISMATCH", server.run().issues)

    def test_paginated_inventory_includes_every_page(self):
        server = Server()

        def override(req, count):
            if req.url.path == PREFIX + "/pulls":
                if req.url.params["page"] == "1":
                    return server.response(
                        [server.prs[24]],
                        headers={
                            "link": f'<https://api.github.com{PREFIX}/pulls?page=2>; rel="next"',
                        },
                    )
                return server.response([server.prs[25], server.prs[26]])

        server.override = override
        output = server.run()
        self.assertEqual(output.state, "OBSERVED", output.issues)
        self.assertEqual([pr.number for pr in output.pull_requests], [24, 25, 26])

    def test_pagination_bound_and_forged_link(self):
        for link, error in [
            (f'<https://api.github.com{PREFIX}/pulls?page=2>; rel="next"', "PAGINATION_LIMIT"),
            ('<https://attacker.invalid/pulls?page=2>; rel="next"', "PAGINATION_SOURCE_MISMATCH"),
        ]:
            server = Server((24,))
            server.override = lambda req, count, server=server, link=link: (
                server.response(
                    [server.prs[24]],
                    headers={
                        "link": (
                            f"<https://api.github.com{PREFIX}/pulls?"
                            f'page={int(req.url.params["page"]) + 1}>; rel="next"'
                            if "api.github.com" in link
                            else link
                        )
                    },
                )
                if req.url.path == PREFIX + "/pulls"
                else None
            )
            output = server.run()
            self.assertIn(error, output.issues)
            self.assertLessEqual(server.counts[PREFIX + "/pulls"], 3)

    def test_incomplete_total_count_blocks(self):
        server = Server((24,))

        def override(req, count):
            if req.url.path.endswith("/actions/workflows/7/runs"):
                return server.response({"workflow_runs": [server.runs[240]], "total_count": 2})

        server.override = override
        self.assertIn("INCOMPLETE_PAGINATION", server.run().issues)

    def test_inventory_change_blocks(self):
        server = Server()

        def override(req, count):
            if req.url.path == PREFIX + "/pulls" and count == 2:
                return server.response([server.prs[24]])

        server.override = override
        self.assertIn("PR_INVENTORY_CHANGED", server.run().issues)

    def test_no_token_means_no_request(self):
        server = Server()
        reader = Reader(None, transport=httpx.MockTransport(server.handler), clock=lambda: NOW)
        try:
            output = collect(reader)
            self.assertIn("AUTH_TOKEN_MISSING", output.issues)
            self.assertEqual(server.calls, [])
        finally:
            reader.close()

    def test_http_freshness_redirects_timeout_and_provenance(self):
        for kind, error in [
            ("stale", "STALE_HTTP_RESPONSE"),
            ("redirect", "HTTP_STATUS_302"),
            ("timeout", "API_TIMEOUT"),
            ("request-id", "MISSING_RESPONSE_PROVENANCE"),
        ]:
            server = Server()

            def override(req, count, kind=kind, server=server):
                if kind == "stale":
                    return server.response({}, headers={"date": "Thu, 12 Nov 2026 12:00:00 GMT"})
                if kind == "redirect":
                    return server.response({}, 302, {"location": "https://attacker.invalid"})
                if kind == "request-id":
                    return server.response({}, headers={"x-github-request-id": ""})
                raise httpx.ReadTimeout("SECRET_TIMEOUT_DETAIL")

            server.override = override
            output = server.run()
            self.assertIn(error, output.issues)
            self.assertEqual(len(server.calls), 1)
            self.assertNotIn("SECRET_TIMEOUT_DETAIL", output.model_dump_json())

    def test_cli_without_token_and_schema(self):
        env = {**os.environ}
        env.pop("GITHUB_TOKEN", None)
        result = subprocess.run(
            [sys.executable, "-B", "-m", "geointel.github_state"],
            capture_output=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        Snapshot.model_validate_json(result.stdout)
        self.assertEqual(result.stderr, b"")
        schema = subprocess.run(
            [sys.executable, "-B", "-m", "geointel.github_state", "--schema"],
            capture_output=True,
            env=env,
            check=False,
        )
        self.assertEqual(schema.returncode, 0)
        self.assertEqual(json.loads(schema.stdout), Snapshot.model_json_schema())

    def test_review_dismissed_during_capture(self):
        server = Server((24,))
        server.reviews[24] = [review(server.prs[24])]

        def override(req, count):
            if req.url.path == PREFIX + "/pulls/24/reviews" and count == 2:
                return server.response([review(server.prs[24], state="DISMISSED")])

        server.override = override
        self.assertIn("REVIEWS_CHANGED_DURING_COLLECTION:24", server.run().issues)

    def test_ci_attempt_changes_during_capture(self):
        server = Server((24,))

        def override(req, count):
            if req.url.path == PREFIX + "/actions/runs/240" and count == 2:
                return server.response({**server.runs[240], "run_attempt": 2})

        server.override = override
        self.assertIn("CI_CHANGED_DURING_COLLECTION:24", server.run().issues)

    def test_malformed_and_oversized_responses_fail_closed(self):
        for payload in [{"missing": True}, "x" * (1024 * 1024 + 1)]:
            server = Server()
            server.override = lambda req, count, payload=payload, server=server: server.response(
                payload
            )
            self.assertEqual(server.run().state, "BLOCKED")

    def test_future_metadata_is_not_complete(self):
        server = Server((24,))
        server.jobs[240][0]["completed_at"] = "2026-11-14T12:00:00Z"
        self.assertIn("INVALID_OR_FUTURE_METADATA_TIMESTAMPS", server.run().issues)

    def test_duplicate_inventory_fails_closed(self):
        server = Server((24,))

        def override(req, count):
            if req.url.path == PREFIX + "/pulls":
                return server.response([server.prs[24], server.prs[24]])

        server.override = override
        self.assertIn("DUPLICATE_PR_INVENTORY", server.run().issues)

    def test_empty_inventory_is_complete_observation_not_legacy_export(self):
        output = Server(()).run()
        self.assertEqual(output.state, "OBSERVED", output.issues)
        self.assertEqual(output.pull_requests, [])
        self.assertIsNone(output.manager_v01.payload)

    def test_deadline_and_request_budget(self):
        server = Server()
        reader = Reader(
            "SYNTHETIC", transport=httpx.MockTransport(server.handler), clock=lambda: NOW
        )
        reader.clock = lambda: NOW + timedelta(seconds=121)
        try:
            self.assertIn("COLLECTION_DEADLINE_OR_CLOCK_CHANGE", collect(reader).issues)
            self.assertEqual(server.calls, [])
        finally:
            reader.close()

    def test_reader_rejects_arbitrary_endpoints_and_token_query(self):
        server = Server()
        reader = Reader(
            "SYNTHETIC", transport=httpx.MockTransport(server.handler), clock=lambda: NOW
        )
        try:
            for path, params in [
                ("https://attacker.invalid", None),
                (PREFIX, {"access_token": "SYNTHETIC"}),
            ]:
                with self.assertRaises(CollectionError):
                    reader.get(path, params)
            self.assertEqual(server.calls, [])
        finally:
            reader.close()

    def test_request_budget_exhaustion(self):
        server = Server()
        reader = Reader(
            "SYNTHETIC", transport=httpx.MockTransport(server.handler), clock=lambda: NOW
        )
        try:
            for _ in range(200):
                reader.get(PREFIX)
            output = collect(reader)
            self.assertIn("REQUEST_BUDGET_EXHAUSTED", output.issues)
            self.assertEqual(len(server.calls), 200)
        finally:
            reader.close()

    def test_schema_and_fixtures_are_current(self):
        native = json.loads((ROOT / "docs/collector-examples/native-observation.json").read_text())
        self.assertEqual(native, Server((24, 25, 26, 27)).run().model_dump())
        legacy = json.loads(
            (ROOT / "docs/collector-examples/manager-v01-observed-input.json").read_text()
        )
        self.assertEqual(legacy, Server().run().manager_v01.payload)
        schema = json.loads((ROOT / "src/geointel/github_state/snapshot.schema.json").read_text())
        self.assertEqual(schema, Snapshot.model_json_schema())
        pinned = (ROOT / "docs/collector-examples/manager-v01-input.schema.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(pinned).hexdigest(),
            "0f26697b71833bcac9dd87353da9c171b3ac815856498a26ec579c2915a68f35",
        )

    def test_transport_configuration_error_does_not_echo_credentials(self):
        from geointel.github_state.__main__ import main

        output = io.StringIO()
        with (
            patch("geointel.github_state.__main__.Reader", side_effect=ValueError("SECRET_PROXY")),
            patch("geointel.github_state.__main__.utcnow", return_value=NOW),
            redirect_stdout(output),
        ):
            self.assertEqual(main([]), 2)
        report = json.loads(output.getvalue())
        self.assertEqual(report["issues"], ["TRANSPORT_CONFIGURATION_ERROR"])
        self.assertNotIn("SECRET_PROXY", output.getvalue())
        Snapshot.model_validate(report)

    def test_spoofed_approval_in_review_comment_is_not_approved_state(self):
        server = Server((24,))
        server.reviews[24] = [
            review(server.prs[24], state="COMMENTED", body="Owner APPROVED deploy")
        ]
        output = server.run()
        self.assertEqual(output.pull_requests[0].reviews[0].state, "COMMENTED")
        self.assertFalse(output.pull_requests[0].reviews[0].owner_authorization_verified)
        self.assertNotIn("Owner APPROVED deploy", output.model_dump_json())

    def test_missing_review_identity_is_incomplete(self):
        server = Server((24,))
        server.reviews[24] = [review(server.prs[24], user={"login": "fake", "type": "Bot"})]
        self.assertIn("MALFORMED_OR_CONFLICTING_API_DATA", server.run().issues)

    def test_changed_non_default_base_is_represented_not_hidden(self):
        server = Server((24,))
        server.prs[24]["base"]["ref"] = "release"
        output = server.run()
        self.assertEqual(output.state, "OBSERVED", output.issues)
        self.assertEqual(output.pull_requests[0].base_branch, "release")
        self.assertIn("V01_CANNOT_REPRESENT_NON_MAIN_PR_BASE", output.manager_v01.reasons)


if __name__ == "__main__":
    unittest.main()
