# Advisory risk classifier v1

`geointel.risk_classifier.evaluate` evaluates a proposed repository revision using an independently collected inventory. It returns a deterministic advisory record. `CLASSIFIED` records a supported R0 or R1 classification. R2 and R3 remain blocked pending the applicable Owner action, and missing or ambiguous evidence also produces `BLOCKED`. This component grants no execution, approval, or merge authority. PR #25 is proposed governance and is outside the policy inputs.

## Classification rules

| Tier | Evidence or rule | Required authorization |
| --- | --- | --- |
| R0 | Analysis request with a verified empty change inventory | None for read-only work |
| R1 | Same-path, non-executable Markdown under `docs/`, independently verified to be inert, with a change limited to trailing blank lines. Both versions must have at least two final LF characters and otherwise identical printable ASCII content. Index and README files are excluded. | Enforceable safeguards before any future autonomous action |
| R2 | Indicators of significant architecture, scientific forecasting, evidence provenance or uncertainty, security implementation, data integrity, migrations, or persistence | Owner approval |
| R3 | Indicators of governance, Owner or Manager authority, repository permissions and secrets, reviewer identity or independence, protected workflows, merge or deployment control, spending, or classifier integrity | Advance Owner authorization |

The evaluator checks both prior and proposed paths and full contents. Paths and text indicators can raise risk. A path alone cannot qualify for R1. The highest detected tier wins. A protected file rename, deletion, or move can retain its tier through the old path or old content. An unmatched edit, unreadable or unsupported blob, conflicting record, or incomplete or stale snapshot blocks classification. When uncertain evidence accompanies an R2 or R3 finding, the reported tier is the highest detected lower bound. An uncertain result with only R0 or R1 findings has a null tier.

Examples on a fresh matching snapshot

| Proposed change | Output |
| --- | --- |
| Read-only inspection with an empty inventory | R0, `CLASSIFIED` |
| Add one trailing blank line to independently verified inert `docs/notes.md` | R1, `CLASSIFIED`, safeguards required |
| Edit an Alembic migration or change forecast logic in a utility | R2, `BLOCKED`, Owner approval required |
| Move a workflow out of `.github/`, change a reviewer-independence setting in a generic utility, or modify the classifier | R3, `BLOCKED`, advance Owner authorization required |
| Omit a modified file or replace a full blob with a partial excerpt | `BLOCKED`, uncertainty recorded |

## Contract and trust boundaries

Use the Pydantic models as the versioned wire contract. Export JSON Schema with `Proposal.model_json_schema()`, `TrustedSnapshot.model_json_schema()`, and `Decision.model_json_schema(mode="serialization")`. Use `model_validate_json` on each input channel and serialize the result with `model_dump_json`. A caller must handle invalid wire input as blocked. The Python evaluator itself returns a blocked decision for invalid proposal dictionaries and for missing or invalid trusted snapshot objects.

- **Proposal** carries version `"1"`, repository, immutable base and head commit SHAs, intended operation, and proposed changes. Each change carries a before and after side with repository-relative path, Git file mode, and complete UTF-8 text. A null side represents creation or deletion. A present side with null text represents unavailable evidence. Full before and after blobs serve as the diff evidence, including for renames. Description and declared tier are ignored. A claimed Owner authorization is unverified and blocks.
- **TrustedSnapshot** arrives via a separate trusted caller. It binds repository and both commit SHAs to a complete inventory using an independent count and SHA-256 digest, and identifies its source. Its explicit, timezone-aware observation and evaluation times must be within 15 minutes, with the observation at or before evaluation. The integration must obtain the evaluation time from its own clock. The optional inert document catalog defaults to empty. Populate it only from separately reviewed policy for the exact revisions, after checking that no executable, generated, integrity-sensitive, or other whitespace-sensitive consumer uses those documents.
- **Decision** reports advisory status, tier, rule findings with path and evidence side, the required authorization, uncertainty, separate blocking conditions, and snapshot provenance. It exposes neither submitted file text nor PR prose. Consumers must check both status and uncertainty. The result is always advisory, even when the input data is complete.

Inventory digest v1 hashes the ASCII bytes of the following representation. Serialize each change as an object with keys in lexical order recursively. Preserve null values, use ASCII JSON escapes, and use a single space after each comma and colon inside each record, as in Python's `json.dumps(..., ensure_ascii=True, sort_keys=True)`. Sort the serialized records lexically and join them with one LF, with no final LF. An empty inventory hashes the empty byte string. The integration must derive the inventory from both revision trees independently, including complete enumeration and both sides of recognized renames. It must define consistent rename representation, path handling, exact decoding, and serialization across producers. A truncated compare API response or replacement-decoded text cannot support a complete snapshot.

The evaluator verifies binding and completeness against the supplied trusted snapshot. It cannot authenticate the caller, inspect GitHub state, prove who owns an account, or prove that a collector honestly and correctly obtained its evidence. The Manager and Developer must have no path to set the trusted snapshot, its clock, its inert catalog, or the evaluator implementation. Computing the trusted digest from their proposal defeats the independent check.

## Limitations and prerequisites for a gate

Whole-file lexical indicators can elevate harmless mentions, comments, or formatting in protected files. They can also miss indirect behavior, aliases, generated files, moved code with unfamiliar naming, external settings, and obfuscated semantics. An unrecognized edit outside the narrow verified documentation transformation is blocked. Among recognized edits, an unseen R3 effect can still be reported as R2. The observation window alone cannot detect a concurrent branch update. V1 also lacks wire size limits, a duplicate JSON key check, persistent audit storage, signature verification, and an Owner authorization protocol.

Before any enforceable merge gate, run the evaluator from a pinned, trusted revision in infrastructure isolated from the proposal. Use a read-only authenticated collector that independently derives complete inventories and promptly invalidates evidence when either revision changes. Cap input size and execution time and treat failures as blocks. Audit decision provenance and expand the protected surface using observed false positives and false negatives during a shadow period. Verify reviewer identity and independence separately, and verify Owner approvals out of band with the exact scope, revision, and approval timing. An independently protected gate must require all applicable safeguards and recheck the exact revisions at the point of merge. Keep the evaluator itself advisory and free of GitHub write privileges.
