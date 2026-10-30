# M2 minimum document end-to-end acceptance

Status: IN PROGRESS, not accepted. Frozen on 2026-10-30 before M2 execution.
Base: Knowledge Factory 784974f; M1 a91add9; Harness H0 df7b08b;
Builder probe baseline 9d33295f. Existing PRs 1, 4 and 95 remain Draft.
V1.5 layout SHA a12cf30a5771b59cd9fabb00ea67d1bc84361d2a73c916c354593b1adc15eb80.

Scope: one newly uploaded numbered synthetic HTML document, native RAGFlow
parse/index/retrieval, Core-owned document candidate/validation/test approval/
immutable manifest/binding, and an installed Harness knowledge Agent.
No automatic FAQ, rule publication, PDF/Word, additional pipeline, new Runtime,
public ingress or production deployment. H1a is knowledge-only installation;
H1b is bank + knowledge providers in one Agent, using separate credentials.

## Fixed synthetic source and retrieval cases

Source: `tests/fixtures/m2-document.html`. UTF-8 bytes are authoritative for this
experiment. It is explicitly synthetic, not a bank-approved rule. Business date
and identities come from a fixed test Host, never the model or browser payload.

| ID | Question | Required source clause |
| --- | --- | --- |
| Q1 | 合成客服服务时间是什么？ | 第一条 |
| Q2 | 客户如何申请历史对账单？ | 第二条 |
| Q3 | 信息缺失时如何处理？ | 第三条 |

Each result must identify the exact original HTML digest, source version,
native DOM location, index build, manifest, request and receipt. Retrieval
completion is separate from correct evidence. Keep all attempts and failures.

## Frozen gates

| ID | Expected behavior |
| --- | --- |
| A01 | New HTML uploaded through UI produces a new native RAGFlow dataset/document/index |
| A02 | All three source clauses have independently verified original anchors |
| A03 | Q1-Q3 retrieve their expected clauses in top 3, without fabricated answers |
| A04 | Unsupported/no-numbered-clause HTML is rejected before index production |
| A05 | Changed, unknown or wrong-document retrieved chunks are rejected |
| A06 | Native parse failure/timeout is retained, cannot produce approved candidate |
| B01 | Candidate, validation and approval identities bind index + source + recipe |
| B02 | Missing/failed validation blocks approval and publication |
| B03 | Unapproved document cannot become a consumer-visible binding |
| B04 | Rule candidates cannot enter the document publication path |
| B05 | Draft edits never change an existing immutable manifest |
| B06 | Manifest mismatch is rejected before retrieval |
| B07 | Source permission revoked before query means zero retrieval requests |
| B08 | Source revoked while retrieval is running means no knowledge disclosure |
| B09 | Unauthorized user/tenant cannot read candidate, service or history |
| B10 | Missing trusted context/invalid date is rejected before retrieval |
| B11 | HTTP 200 with business 403, malformed response or outage is not success |
| B12 | Restart reads immutable versions; replay performs zero retrieval calls |
| B13 | Uploading a new source is not authoritative activation |
| B14 | Failed compare-and-swap binding leaves the old binding intact |
| C01 | H1a Builder admission, build, managed install and real installation Lock |
| C02 | Existing Agent UI calls knowledge tool and traces exact source/manifest |
| C03 | Uninstalled tool, missing grant and withdrawn session are denied |
| C04 | H1b separate bank/knowledge bindings coexist without credential reuse |
| C05 | Stop/release receipts correspond to this Agent/build, no production changes |

All A/B/C results are reported separately. Unit tests cannot substitute for
RAGFlow or Builder evidence. H1a does not imply H1b. Test approval is not bank
business approval. M1 semantic acceptance is independent and remains open.

## Contract adjustment discovered at startup

M0 explicitly rejects document approval (`NO_RULE_APPROVAL_REQUIRED`) and its
manifest mode is `M0_REFERENCE_ONLY`. M2 must not fake a rule or rewrite that
mode. Add versioned document contracts and a document-specific Core extension
using the same object store, policies and immutable transaction primitives.
Native HTML/anchor/index objects belong in that Core closure, not mutable web
files. Existing M0 contracts and reference behavior remain unchanged.

## Isolation

Independent worktree/branch: `knowledge-factory-m2` / `feat/m2-document-e2e`.
Keep port 61352 / PR4 untouched. M2 UI may use an unused loopback port 61353.
RAGFlow's previously stopped local probe stack can be restarted only after
resource checks; no shared database/container or production service is modified.
New datasets, evidence directories and receipts must be distinct from M1.
