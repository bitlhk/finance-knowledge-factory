# Native evidence adapter v0.1 (M1 only)

Implementation: `probes/documents/anchor_bridge.py`. This is a sidecar contract,
not an extension silently accepted by the M0 publisher or a new public API.

## Identities and locations

| Object | Required identity and meaning |
| --- | --- |
| Original | SHA-256 of original bytes, media type and preserved acquisition receipt |
| Native HTML anchor | `evidence-anchor.v0.1`, original byte digest, `HTML_DOM_TEXT`, XPath selecting one text node, Unicode-codepoint `[start,end)`, exact quote and quote digest |
| Anchor ID | Canonical digest of the entire native anchor, including source digest; same XPath in another source version is not the same anchor |
| Derived source | Existing `source-revision.v0.1`, explicitly `text/plain`; copied original quotes joined into derived lines, separate content and object digests |
| Bridge | `html-anchor-bridge.v0.1`, original byte digest, derived-source object digest, `DERIVED_TEXT_ONLY`, producer and complete contiguous line-to-anchor mappings |
| Rule binding | `rule-evidence-binding.v0.1`, Rule IR object digest, bridge digest, all condition/exception/unresolved-reference mappings, `publicationAllowed=false` |

The legacy IR's `lineStart/lineEnd/quoteDigest` address **derived text only**.
They never represent HTML lines, XPath numbers, PDF pages or a Word page count.
The bridge must accompany the IR. Resolving validates both source identities,
the pinned bridge digest, exact original XPath/offset quotes and derived line
coverage. Corruption, duplicate native anchors, wrong hashes, boolean offsets
and missing/overlapping ranges are rejected by focused tests.

Explicit subclause selection is a new input revision: it preserves original
offsets and bytes, records its selection in the experiment freeze, and does not
delete the original full-clause attempt. It must not imply complete coverage of
the parent clause or its cross-references.

## Trust boundary

`expected_digest` must ultimately come from a trusted candidate/Manifest binding,
not an untrusted caller's assertion. In M1 it is pinned in the retained experiment
record and independently checked against the saved source. M2 still needs to bind
source, native sidecar, extraction, validation and approval as an atomic candidate
closure. **An M0 line reference alone cannot establish native evidence validity.**

Retrieval uses the same original anchors: a returned chunk must contain the whole
source clause, not merely mention its number. The frozen question's answer needle
must also be present. Original scores and supplementary source checks are separate.

## Other formats

PDF native rectangles are preserved with source bytes, true 1-based page number,
coordinate convention and parser identity. Independent Poppler checks are in
`check_pdf_locations.py`; the M0 IR bridge currently accepts HTML only. Docling's
bottom-left coordinates are explicitly transformed using the original page height.
Typography normalization is NFKC plus whitespace removal; it is not a semantic
similarity test. Mismatches remain unresolved. No fuzzy fallback makes them pass.

Word conversion and parser text do not establish an original Word anchor. The
current binary `.doc` fixture lacks a verified locator contract. Derived DOCX, if
introduced later, must keep its own hash and a conversion receipt linked to the
original; no derived paragraph/page may be advertised as a native original page.
