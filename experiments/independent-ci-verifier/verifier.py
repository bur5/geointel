"""Local feasibility model. All callers represent trusted control-plane adapters."""
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class Candidate:
    repository: int
    pr: int
    head: str
    base: str
    integration: str
    policy: str


@dataclass(frozen=True)
class Run:
    candidate: Candidate
    workflow: int
    run_id: int
    attempt: int


@dataclass(frozen=True)
class Job:
    run: Run
    name: str
    job_id: int
    conclusion: str


class Gate:
    """Single-PR in-memory verifier and simulated atomic merge target."""

    jobs = frozenset({"python-3.11", "python-3.12", "postgres", "aggregate"})

    def __init__(self, repository, pr, policy, workflow, publisher, owner, reviewer):
        if owner == reviewer:
            raise ValueError("review and Owner identities must be distinct")
        self.repository = repository
        self.pr = pr
        self.policy = policy
        self.workflow = workflow
        self.publisher = publisher
        self.owner = owner
        self.reviewer = reviewer
        self.lock = Lock()
        self.candidate = None
        self.generation = 0
        self.active = None
        self.used_run_ids = set()
        self.completed = False
        self.receipt = None
        self.approvals = set()
        self.merged = False

    def observe(self, candidate):
        """Trusted ref observation with independently established integration provenance."""
        with self.lock:
            if (candidate.repository, candidate.pr, candidate.policy) != (
                self.repository, self.pr, self.policy
            ):
                return False
            if candidate != self.candidate:
                self.candidate = candidate
                self.generation += 1
                self.active = None
                self.receipt = None
                self.approvals.clear()
            return True

    def begin(self, run):
        """The dispatcher records the attempt before allowing it to run."""
        with self.lock:
            if (
                self.merged or run.candidate != self.candidate
                or run.workflow != self.workflow or run.run_id <= 0
            ):
                return False
            if self.active and run.run_id == self.active.run_id:
                if run.attempt != self.active.attempt + 1:
                    return False
            elif run.run_id in self.used_run_ids or run.attempt != 1:
                return False
            self.used_run_ids.add(run.run_id)
            self.active = run
            self.completed = False
            self.receipt = None
            return True

    def finish(self, run, publisher, conclusion, jobs):
        with self.lock:
            if publisher != self.publisher or run != self.active or self.completed:
                return False
            jobs = tuple(jobs)
            self.completed = True
            if (
                conclusion != "success"
                or len(jobs) != len(self.jobs)
                or {job.name for job in jobs} != self.jobs
                or len({job.job_id for job in jobs}) != len(jobs)
                or any(job.run != run or job.job_id <= 0 or job.conclusion != "success"
                       for job in jobs)
            ):
                return False
            self.receipt = (run, publisher, jobs)
            return True

    def snapshot(self):
        with self.lock:
            return self.generation, self.candidate

    def approve(self, snapshot, identity):
        """Identity is supplied by an authenticated, independently controlled adapter."""
        with self.lock:
            if (
                self.candidate is None or snapshot != (self.generation, self.candidate)
                or identity not in {self.owner, self.reviewer}
            ):
                return False
            self.approvals.add(identity)
            return True

    def merge_locally(self, snapshot, identity):
        """Model an atomic validate-and-write operation. Makes no GitHub calls."""
        with self.lock:
            if (
                self.merged or identity != self.owner
                or snapshot != (self.generation, self.candidate)
                or self.receipt is None
                or self.approvals != {self.owner, self.reviewer}
            ):
                return False
            self.merged = True
            return True
