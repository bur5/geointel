'use strict';
// Test the actual inline collector; no duplicate implementation and no dependencies.
const {readFileSync, writeFileSync, appendFileSync} = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const workflow = readFileSync(path.join(__dirname, '../.github/workflows/pr-evidence.yml'), 'utf8');
const block = workflow.split('// BEGIN TESTABLE COLLECTOR\n')[1].split('            // END TESTABLE COLLECTOR')[0];
const collect = vm.runInNewContext(block.split('\n').map(line => line.replace(/^            /, '')).join('\n') + '\ncollect');
const H = 'a'.repeat(40), B = 'b'.repeat(40), W = 'c'.repeat(40);
const blob = '7418c8175a5f398351de27338d0006fb0795f369';
const repository = {id: 1375475901, full_name: 'bur5/geointel', owner: {login: 'bur5'}, name: 'geointel'};
const names = ['test (3.11)', 'test (3.12)', 'postgres-integration'];
const timestamp = '2026-11-12T00:00:00Z';
function fixture() {
  const pr = {number: 26, state: 'open', head: {sha: H, repo: repository}, base: {sha: B, ref: 'main', repo: repository}};
  const context = {eventName: 'pull_request', repo: {owner: 'bur5', repo: 'geointel'}, payload: {repository, pull_request: pr}};
  const env = {GITHUB_SHA: W, GITHUB_WORKFLOW_SHA: W, GITHUB_WORKFLOW_REF: 'bur5/geointel/.github/workflows/pr-evidence.yml@refs/pull/26/merge', GITHUB_RUN_ID: '99', GITHUB_RUN_ATTEMPT: '1', GITHUB_ACTOR: 'bur5'};
  const run = {id: 10, workflow_id: 363226887, path: '.github/workflows/ci.yml', event: 'pull_request', repository, head_repository: repository, head_sha: H, run_attempt: 1, status: 'completed', conclusion: 'success', pull_requests: [pr], created_at: timestamp, updated_at: timestamp, html_url: 'https://github.com/bur5/geointel/actions/runs/10'};
  const jobs = names.map((name, i) => ({id: 100 + i, name, run_id: 10, run_attempt: 1, head_sha: H, status: 'completed', conclusion: 'success', started_at: timestamp, completed_at: timestamp, html_url: `https://github.com/bur5/geointel/actions/runs/10/job/${100+i}`, check_run_url: `https://api.github.com/repos/bur5/geointel/check-runs/${100+i}`, steps: [{number: 1, status: 'completed', conclusion: 'success'}]}));
  const sources = jobs.map(job => ({...job, app: {id: 15368, slug: 'github-actions'}}));
  const f = {context, env, pr, run, jobs, sources, lists: [run], reads: 0, calls: [], blob, after: null};
  function record(name, args) { f.calls.push({name, args}); }
  f.github = {rest: {
    pulls: {get: async args => { record('pulls.get', args); f.reads++; return {data: f.reads > 1 && f.after ? f.after : f.pr}; }},
    repos: {getContent: async args => { record('repos.getContent', args); return {data: {type: 'file', sha: f.blob}}; }},
    actions: {
      listWorkflowRuns: async args => { record('actions.listWorkflowRuns', args); return {data: {workflow_runs: f.lists, total_count: f.lists.length}}; },
      getWorkflowRun: async args => { record('actions.getWorkflowRun', args); return {data: f.run}; },
      listJobsForWorkflowRunAttempt: async args => { record('actions.listJobsForWorkflowRunAttempt', args); return {data: {jobs: f.jobs, total_count: f.jobs.length}}; },
    },
    checks: {get: async args => { record('checks.get', args); return {data: f.sources.find(x => x.id === args.check_run_id)}; }},
  }};
  f.execute = async () => {
    const report = await collect(f.github, f.context, f.env, () => timestamp);
    if (process.env.EVIDENCE_RESULTS_PATH) appendFileSync(process.env.EVIDENCE_RESULTS_PATH, JSON.stringify(report) + '\n');
    return report;
  };
  return f;
}
async function incomplete(edit, issue) {
  const f = fixture(); edit(f);
  const r = await f.execute();
  assert.equal(r.evidence_complete, false);
  if (issue) assert.ok(r.issues.some(x => x.includes(issue)), JSON.stringify(r.issues));
  return r;
}
test('complete observation is advisory; metadata comparisons do not attest tests', async () => {
  const f = fixture(), r = await f.execute();
  assert.equal(r.evidence_complete, true);
  assert.equal(r.observation_state, 'success');
  assert.equal(r.advisory, true);
  assert.equal(r.observed_only.length, 2);
  assert.ok(!('approved' in r) && !('merge_ready' in r));
  assert.equal(r.candidate.head_sha, H);
  assert.ok(f.calls.every(c => /get|list/.test(c.name)));
  if (process.env.EVIDENCE_SAMPLE_PATH) writeFileSync(process.env.EVIDENCE_SAMPLE_PATH, JSON.stringify(r));
});
test('missing job fails closed', () => incomplete(f => f.jobs.pop(), 'missing_or_duplicate_job'));
test('duplicate job fails closed', () => incomplete(f => f.jobs.push(f.jobs[0]), 'duplicate_job'));
test('wrong job SHA fails closed', () => incomplete(f => {f.jobs[0].head_sha = W;}, 'job_candidate_mismatch'));
test('wrong run SHA fails closed', () => incomplete(f => {f.run.head_sha = W;}, 'missing_ci_run'));
test('stale base before collection', () => incomplete(f => {f.pr = structuredClone(f.pr); f.pr.base.sha = W;}, 'stale_candidate_before'));
test('base moves during collection', () => incomplete(f => {f.after = structuredClone(f.pr); f.after.base.sha = W;}, 'stale_candidate_after'));
test('head moves during collection', () => incomplete(f => {f.after = structuredClone(f.pr); f.after.head.sha = W;}, 'stale_candidate_after'));
test('CI run association has stale base', () => incomplete(f => {f.run.pull_requests = [structuredClone(f.pr)]; f.run.pull_requests[0].base.sha = W;}, 'ci_identity_or_candidate_mismatch'));
test('skipped job is not success', async () => {
  const r = await incomplete(f => {f.jobs[0].conclusion = f.sources[0].conclusion = 'skipped';}, 'skipped_checks');
  assert.equal(r.checks[0].state, 'skipped');
});
test('skipped step is not a successful verification', () => incomplete(f => {f.jobs[0].steps[0].conclusion = 'skipped';}, 'incomplete_steps'));
test('pending CI snapshot returns immediately without polling', async () => {
  const f = fixture(); f.run.status = 'in_progress'; f.run.conclusion = null;
  f.jobs[0].status = f.sources[0].status = 'in_progress'; f.jobs[0].conclusion = f.sources[0].conclusion = null;
  const r = await f.execute();
  assert.equal(r.observation_state, 'pending');
  assert.equal(r.evidence_complete, false);
  assert.equal(f.calls.filter(x => x.name === 'actions.listWorkflowRuns').length, 1);
});
test('failure retained separately from unknown', async () => {
  const r = await incomplete(f => {f.jobs[0].conclusion = f.sources[0].conclusion = 'failure'; f.run.conclusion = 'failure';}, 'ci_run_not_successful');
  assert.equal(r.observation_state, 'failure');
});
test('neutral conclusion is unknown', () => incomplete(f => {f.jobs[0].conclusion = f.sources[0].conclusion = 'neutral';}, 'unknown_checks'));
test('forged status names cannot substitute for missing Actions jobs', () => incomplete(f => {f.jobs = []; f.github.rest.repos.getCombinedStatusForRef = async () => {throw new Error('must never use statuses');};}, 'missing_or_duplicate_job'));
test('same-named check from another App fails closed', () => incomplete(f => {f.sources[0].app = {id: 1, slug: 'spoof'};}, 'untrusted_or_racing_check'));
test('spoofed check URL never receives API credentials', () => incomplete(f => {f.jobs[0].check_run_url = 'https://attacker.invalid/check-runs/100';}, 'invalid_check_source'));
test('check API and job conclusions race', () => incomplete(f => {f.sources[0].conclusion = 'failure';}, 'untrusted_or_racing_check'));
test('CI baseline changed by author', () => incomplete(f => {f.blob = H;}, 'ci_baseline_mismatch'));
test('same-named workflow with wrong workflow id rejected', () => incomplete(f => {f.run.workflow_id = 1;}, 'missing_ci_run'));
test('API denied: sanitized unknown report, no exception contents', async () => {
  const r = await incomplete(f => {f.github.rest.pulls.get = async () => {throw new Error('SECRET_RESPONSE');};}, 'api_or_collector_error');
  assert.ok(!JSON.stringify(r).includes('SECRET_RESPONSE'));
});
test('pagination bounded and truncation fails closed', async () => {
  const f = fixture(); let calls = 0;
  f.github.rest.actions.listWorkflowRuns = async () => {calls++; return {data: {workflow_runs: [f.run], total_count: 400}};};
  const r = await f.execute();
  assert.equal(calls, 3); assert.equal(r.evidence_complete, false); assert.ok(r.issues.includes('pagination_limit'));
});
test('latest failed CI cannot be replaced with older successful run', async () => {
  const f = fixture(); f.lists = [{...f.run, id: 9}, f.run]; f.run.conclusion = 'failure';
  const r = await f.execute(); assert.equal(r.evidence_complete, false); assert.equal(r.ci_run.id, 10);
});
test('workflow has no checkout, AI, comments, schedule or privileged trigger', () => {
  assert.ok(!/pull_request_target|workflow_run:|schedule:|workflow_dispatch:|actions\/checkout|secrets\.|: write|createComment|createReview|mergePullRequest/.test(workflow));
  assert.ok(workflow.includes('retries: 0') && workflow.includes('retention-days: 1'));
  assert.ok(workflow.includes('if: ${{ always() }}'));
});
test('missing provenance identity is incomplete', () => incomplete(f => {delete f.env.GITHUB_WORKFLOW_SHA;}, 'invalid_event'));
test('new CI attempt during snapshot invalidates evidence', async () => {
  const f = fixture(); let calls = 0;
  f.github.rest.actions.getWorkflowRun = async () => ({data: ++calls === 1 ? f.run : {...f.run, run_attempt: 2}});
  const r = await f.execute(); assert.equal(r.evidence_complete, false); assert.ok(r.issues.includes('ci_run_changed_during_snapshot'));
});
test('missing completion timestamp is incomplete', () => incomplete(f => {f.jobs[0].completed_at = null;}, 'missing_job_timestamps'));
test('malformed PR refs are incomplete, not a collector crash', () => incomplete(f => {f.pr = {number: 26, state: 'open'};}, 'stale_candidate_before'));
test('malformed CI detail is incomplete', () => incomplete(f => {f.github.rest.actions.getWorkflowRun = async () => ({data: {id: 10}});}, 'ci_identity_or_candidate_mismatch'));
