# OpenJiuwen Python Evaluation Worker acceptance

## Scope and result

PR #12 implements the first Factory-owned evaluation path without JiuwenSwarm,
Harness identity, a new Agent platform, or workbench controls:

1. Core freezes a Candidate, test set, retrieval evaluation, prompt, source
   classification, model identity, assignment, and single-use lease.
2. The Worker requests Candidate evidence through Core. It cannot choose a
   replacement question, source, index, tenant, or business date.
3. A qualified gateway invokes OpenJiuwen `0.1.17.post1` on Python 3.12 using the
   existing authorized Volcengine `deepseek-v4-flash` configuration.
4. Core correlates Candidate receipts, model receipts, original answers, citations,
   facts, and the quality admission. The Worker cannot claim `PASS`.

The trust-boundary implementation used for the final real execution is
`f276b02e2cfe7da25d0be73f060e552c787402cb`. The earlier REJECT and PASS evidence
from `9b6b2a10cf60a513e0735fd0328461f5e87f7717` remains unchanged. A third isolated
execution on the endpoint/receipt boundary fix passed every Core quality check.
After the final lease-at-admission check, a fresh run was correctly rejected for an
incomplete answer and a second fresh run passed without changing gold, prompt, or
thresholds. PR #12 is not deployed.

## Retained real executions

Both executions used the same Worker build, exact requirements lock, Candidate,
test set, quality profile, and retrieval evaluation. They used separate immutable
assignments, leases, receipts, and isolated Core database copies.

### Attempt 1: correctly rejected

- Runtime evidence: `7b919061968fe69c578ae29d598964f4a3d25a13d9b93dc670b9f25e9511e1c9`
- Answer evaluation: `a7972800545433f5d8bf82638b3a1fa69b708a666c66f9cd8f77c54fd3601efb`
- Quality admission: `f5dbe1d0b5d5d4ee6b35fe2efc89d25d5c3be8d956a983ad7df02e7a522fad44`
- Decision: `REJECT`

DeepSeek omitted one required prohibition in one answer. Core retained the original
answer and rejected `allAnswerCasesClassified` and
`answerFactAccuracyComplete`. No gold item, threshold, or answer was edited.

### Attempt 2: passed

- Runtime evidence: `3c065654ec528a0da1f8201bc29033742475d4334bfeabfda850b203cfbb4940`
- Answer evaluation: `6abef80c42cb45b1cfe7b0b833bd4656b39e3d895e9c01b7b06e59c86f871b6a`
- Quality admission: `6fe8bd951045f932654267c36ae8c33cfbedb0d14d62e9ffd2a9670ea6cc3e2e`
- Decision: `PASS`

All six cases were classified correctly. Five answers cited the required clauses;
the no-answer case refused with no citation. Core resolved explicit clause names
and its own numbered evidence references. Unknown numbered references remain
unmatched and fail the gate.

### Attempt 3: trust-boundary revalidation passed

- Assignment: `f5807a64a7397a0d7b86c4af8e69ffe0ed647f190ba7d477b58474c826454347`
- Lease: `7d8a55801c5e8393f05a8b0d461c49da5038483e40e4cea621f0eb24c051822a`
- Gateway registration: `69644931aab62983895ab18f31d83bd813a25834dc11f9d2ba6dda32e76502d1`
- Runtime evidence: `384296c3e66622da34a67fab7ce87b5f93d3e4cc7990a34db763019c7070ea46`
- Answer evaluation: `0ec7b688e4d09e45b2a32be81ada4f5eb1c40e8213468e915494d0eb9f40f0e1`
- Quality admission: `1fa51ac9f121a001fee2f2f69141cea75164f97f941654c049c67ed8bb183cb0`
- Decision: `PASS`

This run used the same frozen six questions, gold, prompt, retrieval evaluation,
quality thresholds, and model configuration. It produced six single-use model
attempts, six invocation receipts, and six original-answer archives. The isolated
database passed `PRAGMA integrity_check`.

### Attempt 4: final code correctly rejected

- Runtime evidence: `3f7ea883c0d9b9fb202e417d4da29c8c0e938ceff0173fe198c98dd2514a2e68`
- Answer evaluation: `eb7b128d273f55e4570fd8cd08e348a6bce4864753bcb82b47bc52d8813bd36e`
- Quality admission: `897582139ba8d9ab53b5bb1210ab88d9db92451edf3110adb58df3d66231bf94`
- Decision: `REJECT`

DeepSeek again omitted a required fact in one answer. Core retained all six original
answers and receipts and rejected `allAnswerCasesClassified` and
`answerFactAccuracyComplete`.

### Attempt 5: final code passed

- Assignment: `4335afaca277578d6c582ea5a61da97a52c49f6fb108ef8ca67635ba934aa493`
- Lease: `f7f4ddb207e7c2bc9b1fa920029fe366da207541608dd04a1ce27b92cb3dd80e`
- Gateway registration: `f0bd601973a5301bdb0eb055d2e8a341ee4e764d9d483c4732e356cd8335e5aa`
- Runtime evidence: `6545a4234a143883df96972d581be4df63d03cacba5f012919209071cfc608b8`
- Answer evaluation: `c2493d12e8e9102496e3020970224c6539e6cb1fbad860783a51299682ea3e6d`
- Quality admission: `181734df2a10b4e339adb632dcfe621f0500bd3dc6dfcbdf9904e1f88b73a193`
- Decision: `PASS`

The final run produced six single-use attempts, six invocation receipts, and six
answer archives. Core independently recomputed all answer checks and the isolated
database integrity check returned `ok`.

## Fixed identities

- Final Worker build digest: `5b6eb782578229417fdaea012862119f62b7680d957c016174aef4f3eac4a385`
- Earlier retained Worker build digest: `c5a38b6ee1cde632eb14739b6b65c5a68121be1372e58131bd6c09444d022a4d`
- Requirements lock digest: `c5c387248ffb9ac7a67db30d3050f740fcacf1b940d3253b34ca472865743130`
- Candidate: `635a7c3c3ddf2f48f7ed1799556ec5cf7578584b0e4dbada7e137138c3cbc799`
- Test set: `4ef85edbc3fd1ff3ee23a6a8e81931678d6e0f395df8526950c9ea64f80f6b2a`
- Quality profile: `9536ac8f979b33d842c5c0300ef5f3c623b44c594cf4841d58bdc2a0ed3cf2a7`
- Retrieval evaluation: `399fce51a76fd3185a9aa2817e6ec2686b0820bbdf16d6e40f8e38c65a710f5b`
- Model configuration digest: `a672a438bd6004cc725fac7d61b54cb64338bb1ea497848f5753f558e05d0b3e`

The model secret was neither read into the report nor committed. OpenJiuwen's
default content logs are disabled before model modules load; the accepted run
created no SDK log files. Bounded token counts may be retained in Core receipts.

## Trust-boundary review

The final review closed the code-level bypasses found in the original in-process
acceptance:

- the Worker now receives assignment-bound candidate-query and model-authorization
  clients rather than the complete Core actor and management object;
- provider, model, endpoint, region, execution zone, and external/internal status
  come from one qualified Gateway deployment registration, not Worker input;
- DNS endpoints default to external, and endpoint classification mismatches fail;
- Core checks the exact Gateway runtime identity before an outbound observer or
  model call can run;
- each model authorization creates one single-use invocation attempt, and a second
  attempt or receipt is rejected;
- the evaluation lease pins the Worker build, while runtime evidence rechecks that
  build and the answer archive's content digest.

These controls are verified in the library and real isolated runner. The runner
still hosts Core, narrow clients, Worker, and Gateway in one Python process. Python
object encapsulation is not process isolation, authenticated RPC, or a
cryptographic receipt signature. Separate service identities and process/container
boundaries remain an explicit production deployment prerequisite; this PR does not
claim that prerequisite is complete.

## Compatibility and deployment

The complete local repository regression is `383 passed`. Python 3.10 and 3.12 CI
must pass on the final documentation commit before review. Existing
`document-manifest.v0.1`, published query, authorization, and history contracts are
unchanged. PR #11 remains the only code deployed to the Singapore development
service. After its post-acceptance restart, an existing published product query
returned a new document receipt and the same three anchored clauses.

This PR does not yet add workbench scheduling, Candidate selection UI, or automatic
publication. Those remain later, independently reviewed work.
