import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

from verifier import Candidate, Gate, Job, Run


class GateTests(unittest.TestCase):
    def setUp(self):
        self.gate = Gate(1375475901, 32, "policy-1", 11, 42, "owner", "reviewer")
        self.candidate = Candidate(1375475901, 32, "head", "base", "merge", "policy-1")
        self.assertTrue(self.gate.observe(self.candidate))
        self.snapshot = self.gate.snapshot()
        self.run_record = Run(self.candidate, 11, 1, 1)
        self.assertTrue(self.gate.begin(self.run_record))

    def jobs(self, run=None):
        run = run or self.run_record
        return [Job(run, name, number, "success")
                for number, name in enumerate(sorted(self.gate.jobs), start=1)]

    def complete(self):
        self.assertTrue(self.gate.finish(self.run_record, 42, "success", self.jobs()))

    def approve(self):
        for actor in ("reviewer", "owner"):
            self.assertTrue(self.gate.approve(self.snapshot, actor))

    def assert_blocked(self):
        self.assertFalse(self.gate.merge_locally(self.snapshot, "owner"))

    def test_success_and_replay(self):
        self.complete()
        self.approve()
        self.assertTrue(self.gate.merge_locally(self.snapshot, "owner"))
        self.assert_blocked()

    def test_missing_owner_reviewer_or_trusted_verdict(self):
        self.assert_blocked()
        self.complete()
        self.assertTrue(self.gate.approve(self.snapshot, "owner"))
        self.assert_blocked()
        self.assertFalse(self.gate.approve(self.snapshot, "developer"))
        self.assertTrue(self.gate.approve(self.snapshot, "reviewer"))
        self.assertFalse(self.gate.merge_locally(self.snapshot, "developer"))

    def test_untrusted_publisher_and_workflow(self):
        self.approve()
        self.assertFalse(self.gate.begin(replace(self.run_record, workflow=99)))
        self.assertFalse(self.gate.finish(self.run_record, 99, "success", self.jobs()))
        self.assert_blocked()

    def test_cancelled_rerun_supersedes_success(self):
        self.complete()
        self.approve()
        later = replace(self.run_record, attempt=2)
        self.assertTrue(self.gate.begin(later))
        self.assert_blocked()
        self.assertFalse(self.gate.finish(later, 42, "cancelled", self.jobs(later)))
        self.assertFalse(self.gate.finish(self.run_record, 42, "success", self.jobs()))
        self.assertFalse(self.gate.finish(later, 42, "success", self.jobs(later)))
        self.assert_blocked()

    def test_superseded_run_cannot_be_reopened(self):
        self.complete()
        self.assertTrue(self.gate.begin(replace(self.run_record, run_id=2)))
        self.assertFalse(self.gate.begin(replace(self.run_record, attempt=2)))

    def test_missing_duplicate_wrong_attempt_and_non_success_jobs(self):
        good = self.jobs()
        cases = [
            good[:-1],
            good[:-1] + [good[0]],
            good[:-1] + [replace(good[-1], job_id=good[0].job_id)],
            good[:-1] + [replace(good[-1], run=replace(self.run_record, attempt=9))],
        ]
        cases.extend(good[:-1] + [replace(good[-1], conclusion=conclusion)]
                     for conclusion in ("failure", "cancelled", "skipped", "neutral", "timed_out"))
        self.approve()
        for run_id, jobs in enumerate(cases, start=2):
            with self.subTest(run_id=run_id):
                run = replace(self.run_record, run_id=run_id)
                jobs = [replace(job, run=replace(job.run, run_id=run_id)) for job in jobs]
                self.assertTrue(self.gate.begin(run))
                self.assertFalse(self.gate.finish(run, 42, "success", jobs))
                self.assert_blocked()

    def test_wrong_repo_pr_or_policy(self):
        for field, value in (("repository", 1), ("pr", 25), ("policy", "unapproved")):
            with self.subTest(field=field):
                self.assertFalse(self.gate.observe(replace(self.candidate, **{field: value})))
                self.assertFalse(self.gate.begin(replace(
                    self.run_record, candidate=replace(self.candidate, **{field: value})
                )))

    def test_stale_candidate_and_aba(self):
        self.complete()
        self.approve()
        for field in ("head", "base", "integration"):
            with self.subTest(field=field):
                self.assertTrue(self.gate.observe(replace(self.candidate, **{field: "changed"})))
                self.assert_blocked()
                self.assertFalse(self.gate.approve(self.snapshot, "owner"))
        self.assertTrue(self.gate.observe(self.candidate))
        self.assert_blocked()
        self.assertFalse(self.gate.begin(self.run_record))
        self.assertFalse(self.gate.approve(self.snapshot, "reviewer"))

    def assert_race_blocked(self, invalidate):
        read = Barrier(2)
        changed = Barrier(2)

        def merge():
            snapshot = self.gate.snapshot()
            read.wait(timeout=5)
            changed.wait(timeout=5)
            return self.gate.merge_locally(snapshot, "owner")

        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(merge)
            read.wait(timeout=5)
            self.assertTrue(invalidate())
            changed.wait(timeout=5)
            self.assertFalse(result.result(timeout=5))

    def test_base_move_after_final_read(self):
        self.complete()
        self.approve()
        self.assert_race_blocked(
            lambda: self.gate.observe(replace(self.candidate, base="new-base"))
        )

    def test_head_move_after_final_read(self):
        self.complete()
        self.approve()
        self.assert_race_blocked(
            lambda: self.gate.observe(replace(self.candidate, head="new-head"))
        )

    def test_retry_after_final_read(self):
        self.complete()
        self.approve()
        self.assert_race_blocked(
            lambda: self.gate.begin(replace(self.run_record, attempt=2))
        )

    def test_concurrent_merge_has_single_winner(self):
        self.complete()
        self.approve()
        start = Barrier(2)

        def merge():
            start.wait(timeout=5)
            return self.gate.merge_locally(self.snapshot, "owner")

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [executor.submit(merge) for _ in range(2)]
            self.assertEqual(sorted(result.result(timeout=5) for result in results), [False, True])
