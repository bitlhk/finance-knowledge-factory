# PR #14 minimal implementation design

## Objective

Complete one real customer-manager workflow in the existing Knowledge Factory workbench:

`registered source -> candidate -> trusted evaluation -> quality report -> independent approval -> fixed Manifest -> existing discovery API`

The first knowledge product is limited to Bank of China (BOC) wealth product `AMSYLJ01`. It must not be presented as a universal bank rule or as proof that the product is currently on sale.

## Existing implementation to reuse

- Workbench entry: `m2/web.py`, `m2/web.js`, and the existing `web_production` shell.
- Candidate, source, index, validation, approval, Manifest, query, and history: `knowledge_core/documents.py`.
- Trusted evaluation services: PR #13 Core, Worker, and Gateway IPC services.
- Quality publication authority: `DocumentCore.publish_quality_document()`.
- External contracts: existing Manifest, Query, History, discovery, and Harness consumption contracts remain unchanged.

The current workbench calls `publish_document()` and exposes an isolated-test release flow. PR #14 replaces that orchestration for a quality-managed candidate; it does not create a second portal or a second publication model.

## Server-side state machine

1. `CANDIDATE_READY`: immutable source revision, derived index, candidate, and retrieval validation exist.
2. `EVALUATION_AUTHORIZED`: an authenticated operator requests evaluation; the Host issues the minimum evaluation assignment and lease.
3. `EVALUATION_RUNNING`: the Host invokes the isolated PR #13 services. Browser input cannot choose service identities, model endpoint, source classification, or publication authority.
4. `QUALITY_REJECTED` or `QUALITY_PASSED`: Core recomputes the result from trusted runtime evidence. Raw failures remain visible and immutable.
5. `APPROVAL_REQUIRED`: a PASS only permits an authorized reviewer to consider publication.
6. `APPROVED`: a distinct reviewer identity records approval for the exact candidate, quality admission, source revision, and intended product version.
7. `PUBLISHED`: Core calls `publish_quality_document()` and binds the resulting fixed Manifest. No automatic upgrade occurs.

Quality PASS never invokes approval or publication automatically.

## Minimal API changes

Extend the existing workbench server rather than adding a new service:

- `POST /api/document-evaluate`
  - accepts only `runId` and expected `candidateDigest`;
  - operator identity is server-authenticated;
  - returns an evaluation run identifier, not a caller-supplied PASS.
- `GET /api/runs/{id}`
  - returns the existing run view plus case status, archived raw answer, answer citations, fact checks, failure codes, runtime-evidence digest, and quality admission.
- `POST /api/document-approve`
  - binds authenticated reviewer, candidate, admission, reason, and intended version;
  - rejects the evaluation executor when separation-of-duties policy requires a second actor.
- `POST /api/document-publish`
  - accepts expected candidate, approval, admission, and version digests;
  - invokes `publish_quality_document()` and existing binding logic.

All endpoints use strict schemas, optimistic digest checks, same-origin protections, idempotency keys, and fail closed on stale or revoked authority.

## Workbench changes

Reuse the current four workbench pages.

- Source page: source URL, captured-at time, publisher, document date/version, original hash, derived-artifact hash, and validity status.
- Production page: canonical units, source anchors, retrieval index, candidate version, and completeness diagnostics.
- Quality section: run action, progress, per-case raw answer, retrieved evidence, actual answer citations, fact support, rejection reason, model/runtime receipt, and aggregate report.
- Release section: separate quality status, approval status, and publication status. Only authorized actions are enabled.
- Product page: fixed Manifest, exact source versions, approval and quality receipt summaries, and existing query/history links.

No hidden technical JSON is placed in the primary task flow. Digests and raw receipts remain available in expandable audit details.

## PDF handling for the first product

PR #14 does not claim generic PDF support. For the BOC product specification only:

1. Preserve the original PDF bytes, official URL, capture timestamp, SHA-256, and page count.
2. Produce a deterministic derived HTML representation in an isolated conversion step.
3. Record converter identity/version, input/output hashes, page boundaries, text spans, and a page-to-HTML anchor map.
4. Verify every publishable quote against page text extracted from the preserved PDF. Derived section labels may aid retrieval but cannot become authoritative quotes.
5. Block quality admission when required sections are missing, truncated, or cannot map back to a unique PDF page and quote.

This is a controlled source adapter, not a general document-parsing platform.

## Business boundary

Knowledge may establish the pinned product document's terms. It cannot establish:

- the customer's current risk rating or its validity;
- the product's current sale status, quota, current yield, or channel availability;
- a customer's actual balance, intent, or source of funds;
- final suitability, purchase approval, or transaction completion.

Those facts must come from authorized CRM/product systems at Agent runtime. The answer must distinguish source facts, live business facts, and unresolved checks.

## Intended code units

After PR #13 is merged, create PR #14 from the new `main` and keep changes scoped to:

- `m2/web.py`: quality-run orchestration and independent approval/publication endpoints.
- `m2/web.js`: source/version, case report, approval, and publication UI in the existing workbench.
- `web_production/server.py`: strict routing for the new workbench actions.
- `knowledge_core/evidence/`: the controlled PDF-derived source adapter and page-anchor verification, if no existing adapter can satisfy the first product.
- `tests/test_m2_web.py`: authentication, state transitions, stale digest, PASS-not-published, independent approval, and failure retention.
- new focused tests for PDF provenance and page-anchor verification.
- versioned examples under `examples/business/` for the source register and test set; no production product is modified.

## Executable acceptance cases

The first product uses `boc-wealth-manager-test-set-v0.1.json`. Acceptance requires:

- correct answers with all required evidence for answerable cases;
- explicit unresolved live facts where CRM/product-system data is required;
- refusal to assert current sale status, current customer suitability, guaranteed returns, or transaction completion;
- exact original-page citations for product-specification conclusions;
- source/version mismatch and source revocation to reject evaluation or publication;
- model/Gateway failure to retain a failed run and never create PASS;
- quality PASS without reviewer approval to remain unpublished;
- unauthorized reviewer, stale candidate, or admission mismatch to be rejected;
- publication to produce a fixed Manifest discoverable through the existing API;
- query and history contracts to remain compatible.

## Second role preparation

`boc-business-loan-review-test-set-draft-v0.1.json` is a separate BOC loan-material completeness draft. It is not included in the first wealth product or PR #14 publication acceptance. ICBC materials remain a separate future product because branch-specific ICBC conditions cannot be combined with BOC requirements.

## Explicit non-goals

- No new Agent runtime, generic model gateway, knowledge portal, auto-approval, or auto-publication.
- No Harness or Builder changes.
- No modification of existing products, Manifests, histories, PR #9, or Shanghai services.
- No claim of universal PDF/DOCX support.
- No automatic determination of suitability, credit approval, or transaction eligibility.
