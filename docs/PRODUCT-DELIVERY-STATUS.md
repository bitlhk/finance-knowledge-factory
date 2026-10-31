# Product delivery candidate, 2026-10-31

## Review and integration boundaries

- Backend A-C: PR #8 `ed350496156070d6a271a03e6b217e1725623d44`, unchanged, Draft.
- Incremental delivery: PR #9, based on that exact backend, not the UI chain.
  Its PR base is the A-C review branch to expose only new files. Do not merge
  both overlapping A-C/D envelopes. Retarget and revalidate after backend approval.
- PR #7/D, original 61353, public zhishi, original M2 data and historical
  evidence remain untouched. No Harness/Builder edits or service deployments.
- Main, PR #1-#8 and their historical outcomes are not promoted by this delivery.

## Contract delivered to Harness

Harness confirmed discovery schema hash
`0b671ae3de0dcb04e0614a9bed80ee38b7cd4672fb9db9df064aabe25f0a7e4e`
in thread `019ef935-6aac-72d1-bd18-4a13d8001606` on 2026-10-31.
See PRODUCT-DELIVERY.md for field mapping, authorization separation and startup.
Query/session/history schemas and implementations are unchanged. New generic
startup only removes the legacy CLI's sample-specific binding by requiring an
explicit operator-supplied binding; it does not relax Runtime validation.

## Verification

| Check | Result and limit |
| --- | --- |
| Regression | 302 passed: 274 backend + 28 new; controlled transport, not Agent acceptance |
| Discovery | Independent Host fixture lease, current Core rights, scope/source/binding checks |
| Metadata safety | No source body, dataset addresses, credentials or audience lists returned |
| Failures | Missing/expired/forged authorization, revoked rights, wrong scope/tenant, malformed HTTP, size limit |
| Runtime separation | Non-H1a generic query/history processes start, anonymous access refuses, workers stop |
| Version pinning | Draft changes leave descriptors unchanged; active revision change invalidates old query pin |
| Native production | 3/3 fixed retrieval questions through actual RAGFlow; one saved Core query |
| Model calls | No generative model used; real local embedding/indexing is not a model quality test |
| Joint Builder delivery | Pending Harness selection, managed installation and actual Agent invocation |

GitHub Actions run `41159558738` independently passed on Python 3.10 and 3.12,
302 tests each, for the `1b5f11d` candidate. The local XML was collected before
the first commit from the corresponding working tree; it is not represented as
a clean committed checkout. CI and native production have separate identities.

The regression XML has twelve pre-existing pytest warnings about record_property
with xunit2. No tests failed. The new synthetic native preparation completed on
clean execution commit `1b5f11d9a1e94f734d1aced2c98747a31361e27f`.
Evidence files and byte digests are listed in `evidence/product-delivery/INDEX.json`.

## Two concrete product descriptions

1. Original M2 sample: `examples/products/h1a-release.json`, read-only export.
   Product `run-39d069d400924257a857cfa7ec64917b`, Manifest
   `8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3`.
   No new grant, activation or receipt was written to that database.
2. New shared-consumption test product: `evidence/product-delivery/release.json`.
   Product `synthetic-product-policy-e1bdc9d3687e`, version 1, Manifest
   `1d51ac2b45f67ad61099c5a741017c23bb5096c7300fe12a3395f5a45de1449f`.
   Descriptor digest `630d800708d62f3bd3c8f696de28cb7f08f0c9a3d11b91e3e85fbd35e3cd7374`.

The new product says CRM provides customer facts, product service provides product
facts, and knowledge provides matching requirements. It installs no rule tool and
cannot produce customer facts itself. Both products are isolated test publications,
not bank-approved rules or production-authorized services.

## Handoff environment

New isolated snapshot and binding:
`/home/ubuntu/outputs/kf-product-delivery-20261031/native-01/`.
Core policy fixtures exist only in this fresh test database. Host credentials,
viewer identity, discovery authority and runtime/history sessions were not created
by Factory. Harness owns their issuance after normal workbench authentication.
Use a fresh SQLite backup for joint tests, especially revocation/mismatch tests;
retain this initial snapshot and saved receipt. The dedicated synthetic RAGFlow
index is retained for integration, not claimed cleaned up.

No always-on product discovery or generic consumption service was installed.
Harness can start the three foreground loopback services using the supplied
non-sensitive instructions and independently supplied private Host files.
Their readiness is not evidence of successful authorization or Agent installation.

## Outstanding joint gate

Harness must pin its code SHA and this Factory candidate, select the new product
via authenticated discovery, verify the descriptor and Lock/configuration binding,
query the actual Factory/RAGFlow service, then verify source revocation, Manifest
mismatch, stopped-Agent independently authorized history and original anchors.
No simulated Provider result substitutes for that gate. Shared-consumption H1b
qualification belongs to Harness; this Factory release does not claim it passed.
