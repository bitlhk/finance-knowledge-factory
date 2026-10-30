# V1.5 UI alignment correction

## Why this correction exists

The first real-production frontend replaced the V1.5 process lanes with a
four-row status list, omitted the product home, and put candidates under the
formal artifact/consumption navigation. Similar colors and navigation did not
make that implementation faithful to the frozen design.

This correction uses the original V1.5 stylesheet directly after verifying
SHA-256 `a12cf30a5771b59cd9fabb00ea67d1bc84361d2a73c916c354593b1adc15eb80`.
It no longer inherits V0.1's evidence-viewer style overrides. The original HTML
and its simulated JavaScript are not changed or executed by this preview.

## Restored interaction structure

- Product home, pending production records and product selector. The preview
  currently groups products by one immutable source, explicitly labelled
  single-source trial production. It is not a new M0 product registry or a
  claim of multi-source product lifecycle support.
- Three-column workshop: source tiles and inline upload/library entry; common
  parsing followed by separate document/rule lanes; actual candidate outputs.
- Clickable steps and source/output tiles open a three-pane input/output/check
  inspector. Original source anchors, responses, IR and receipts remain folded
  technical details. Stage status comes from saved backend events, not timers.
- Four-step recipe with pipeline/component linkage, editable question/expected
  clause rows and JSON test import. Cancelling edits leaves the active frozen
  run unchanged. Unsupported components and IAM roles are disabled.
- Candidate checks and sandbox tests stay in production. Formal artifact
  catalogue contains zero published products. Formal service use is disabled;
  consumption history can display saved candidate receipts without reexecution.
- The five crafts are retained. Only native HTML document processing and the
  existing bounded rule recipe execute. No fake RAGFlow, FAQ, approval, publish,
  Harness connection, PDF or Word support has been introduced.

## Verification

`check-v15.cjs` is a repeatable browser test. It rejects any rule/model production
submission, verifies the old full export before/after, and performs one new
document-only production. The first complete alignment run is
`run-cbf2b3ac3be24c1aa321e6561a935d04`: two actual synthetic HTML clauses, one user
retrieval check passed, no model calls and no rule-engine calls. This is UI and
pipeline verification, not independent semantic quality acceptance.

The first alignment pass checks the product home, original three-column/lane
structure, three-pane inspector, component linkage, draft cancellation,
refresh/readback, disabled formal publication, invalid source rejection and
1366/390/320 layouts. No JavaScript exceptions or whole-page horizontal overflow
were observed. Whole old export before/after:
`f2f58c2998caf0e47d9e97284b08e5ce540df0f7cdbb930a8a1cd4432478cfc6`.

A separate retained-rule regression adds four explicitly new receipts, not
replacements for old receipts: MET, NOT_MET, INVALID_INPUT, NOT_APPLICABLE. Two
primary Flowable calls and one recovery call; two guard-only cases. No new model
calls. The old attempts and sealed candidate are unchanged. Full exports after
this separate test naturally include those new receipts.

Python regression: **281 passed**. The added test refuses a modified UI baseline;
HTTP tests also verify that served CSS begins with the original baseline CSS and
the workshop script is available. Core, model prompts, gold sets, execution,
provider and installation contracts are unchanged.

## Preview and walkthrough

Development host only: `http://127.0.0.1:61352/`.

1. Open Knowledge Production. Open the public-loan product's workshop.
2. Select the saved run and article 43. Click Semantic Extraction and Controlled
   Lowering. Inspect the supported numeric condition and unsupported half-term
   expression, with original source and model evidence.
3. Open Recipe / Components. Toggle rule processing to see its component panel
   appear/disappear; cancel to retain the frozen run.
4. Use inline Upload for numbered HTML, configure the four recipe steps and a
   user retrieval question, then Start Production. Document-only needs no model.
5. Open Candidate Testing below the workshop. Published products stay separate;
   no approval or publish permission is granted by this preview.

The isolated preview is updated, not a production deployment. PR #4 stays Draft;
no merge. M0, M1 semantic acceptance and Harness H1 remain separate work.
