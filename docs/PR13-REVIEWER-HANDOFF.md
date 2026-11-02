# PR #13 independent reviewer handoff

## Review target

- implementation head: `d766e612ea354be89eb0978c32dd2c4854c546b6`
- review target: the current PR head, including this handoff document
- base: `main@53cca76e5d8ee9c8ee558200dafa1c03253b4323`
- scope: authenticated local IPC and process/file isolation for the fixed
  Factory evaluation flow
- excluded: publication UI, automatic approval, public service exposure,
  Harness/Builder and production enablement

The author has not approved the PR. Merge requires a real independent review.

## Security boundary to inspect

| Identity | Permitted secret/state | Forbidden state |
| --- | --- | --- |
| Core | isolated database, retrieval credential | model credential, Worker handoff |
| Worker | role credential, frozen task, own handoff | database, retrieval/model credentials, PASS or publication operation |
| Gateway | role credential, model credential | database, retrieval credential, quality decision |
| Host | role credential, Worker handoff | model credential, answer fabrication, automatic publication |

Requests require the expected Unix peer UID and a role credential. Core creates
one SQLite connection per request and keeps SQLite thread checks enabled.

## Defect correction review

1. Confirm `service_task.py`, `prepare_evaluation_service_task.py` and
   `service_process.py` derive purpose, redaction profile, expiry and runtime
   versions from trusted stored/runtime state and exact-compare them before Core
   starts.
2. Confirm task schema/version/type errors and binding tampering fail before a
   socket is exposed; Worker cannot substitute case IDs.
3. Confirm Gateway failure receipts contain only the fixed stage/code enum and
   that OpenJiuwen structured status/cause handling cannot persist exception
   text, prompt, endpoint details or credentials.
4. Confirm a failed attempt cannot produce a response archive, evaluation or
   Admission, and a consumed Lease cannot be retried.
5. Confirm no IPC operation grants source activation, publication, arbitrary
   object access or policy administration.

## Evidence and regression

- Final-head real PASS digests and failure receipt are recorded in
  `TRUSTED-EVALUATION-SERVICES-ACCEPTANCE.md`.
- Real fail-closed checks include wrong UID/credential, operation role mismatch,
  expiry, source revocation, restricted egress, receipt forgery, replay, stopped
  Gateway and service crash recovery.
- Local suite: `418 passed`.
- GitHub CI: Python 3.10 and 3.12 passed at the final head.
- External Manifest, query, authorization, history and publication contracts
  are unchanged.

## Deployment assumptions not proved by merge

Merge does not enable a production Worker or Gateway. Production must separately
provision distinct operating-system identities, filesystem ACLs, credentials,
qualified model registration and systemd units, then repeat the acceptance.
The PR #14 workbench action must remain fail-closed until this is complete.
