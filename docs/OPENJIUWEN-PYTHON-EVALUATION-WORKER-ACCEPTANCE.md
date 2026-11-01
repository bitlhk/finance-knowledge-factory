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

The final implementation code used for real execution is
`9b6b2a10cf60a513e0735fd0328461f5e87f7717`. The second independent execution of
the frozen six-case set passed every Core quality check. PR #12 remains Draft and
is not deployed.

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

## Fixed identities

- Worker build digest: `c5a38b6ee1cde632eb14739b6b65c5a68121be1372e58131bd6c09444d022a4d`
- Requirements lock digest: `c5c387248ffb9ac7a67db30d3050f740fcacf1b940d3253b34ca472865743130`
- Candidate: `635a7c3c3ddf2f48f7ed1799556ec5cf7578584b0e4dbada7e137138c3cbc799`
- Test set: `4ef85edbc3fd1ff3ee23a6a8e81931678d6e0f395df8526950c9ea64f80f6b2a`
- Quality profile: `9536ac8f979b33d842c5c0300ef5f3c623b44c594cf4841d58bdc2a0ed3cf2a7`
- Retrieval evaluation: `399fce51a76fd3185a9aa2817e6ec2686b0820bbdf16d6e40f8e38c65a710f5b`
- Model configuration digest: `a672a438bd6004cc725fac7d61b54cb64338bb1ea497848f5753f558e05d0b3e`

The model secret was neither read into the report nor committed. OpenJiuwen's
default content logs are disabled before model modules load; the accepted run
created no SDK log files. Bounded token counts may be retained in Core receipts.

## Compatibility and deployment

The complete repository regression passes on Python 3.10 and 3.12. Existing
`document-manifest.v0.1`, published query, authorization, and history contracts are
unchanged. PR #11 remains the only code deployed to the Singapore development
service. After its post-acceptance restart, an existing published product query
returned a new document receipt and the same three anchored clauses.

This PR does not yet add workbench scheduling, Candidate selection UI, or automatic
publication. Those remain later, independently reviewed work.
