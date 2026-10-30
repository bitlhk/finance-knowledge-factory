"""Document production adapter. All authoritative objects belong to Core."""
import re
from lxml import html
from jsonschema import Draft202012Validator
from knowledge_core.contracts import Rejected, digest, text_digest
from knowledge_core.document_contracts import CASE
from knowledge_core.documents import normal
from knowledge_core.rules import validate_scope
from probes.documents.anchor_bridge import build
from probes.documents.html_evidence import locate, verify


def parse(raw):
    if not raw or len(raw) > 1_000_000:
        raise Rejected('HTML_SIZE_LIMIT')
    text = raw.decode('utf-8', errors='strict')
    if '<html' not in text.lower() and not re.search(r'<(?:p|div|article)\b', text, re.I):
        raise Rejected('HTML_REQUIRED')
    tree = html.fromstring(text, parser=html.HTMLParser(no_network=True))
    texts = tree.xpath('//text()[not(ancestor::script) and not(ancestor::style) and not(ancestor::noscript)]')
    chunks = locate(raw, list(map(str, texts)))
    if not chunks or len(chunks) > 300 or not all(verify(raw, c) for c in chunks):
        raise Rejected('NO_VERIFIABLE_NUMBERED_CLAUSES')
    if len({c['clause'] for c in chunks}) != len(chunks):
        raise Rejected('DUPLICATE_CLAUSE_NUMBER')
    return chunks


def produce(core, actor, product_id, revision, raw, scope, tests, consumers, client):
    actor.require('artifact.produce')
    validate_scope(scope)
    if not isinstance(tests,list) or not 1 <= len(tests) <= 30 or any(
            not Draft202012Validator(CASE).is_valid(t) for t in tests):
        raise Rejected('RETRIEVAL_GOLD_INVALID')
    chunks = parse(raw)
    if any(t['expectedClause'] not in {c['clause'] for c in chunks} for t in tests):
        raise Rejected('RETRIEVAL_GOLD_INVALID')
    source, bridge = build(raw, chunks, product_id+'-source')
    source['revision'] = revision
    bridge['derivedSourceDigest'] = digest(source)
    source_sha = core.register_source(actor, source)
    core._source_access(actor, source_sha)
    index = client.ingest(raw)
    for chunk in index['chunks']:
        chunk['textDigest'] = text_digest(chunk['text'])
        chunk['clauses'] = [c['clause'] for c in chunks if normal(c['text']) in normal(chunk['text'])]
    index_sha = core.register_document_index(actor, source_sha, raw, bridge, index,
                                            [{'clause':c['clause'],'text':c['text']} for c in chunks])
    refs = []
    lines = source['content'].splitlines()
    for clause in chunks:
        mappings = [m for m in bridge['mappings'] if m['clause']==clause['clause']]
        start, end = mappings[0]['lineStart'], mappings[-1]['lineEnd']
        refs.append({'sourceDigest':source_sha, 'lineStart':start, 'lineEnd':end,
                     'quoteDigest':text_digest('\n'.join(lines[start-1:end]))})
    test_sha = core.register_test_set(actor, {'schemaVersion':'test-set.v0.1',
        'id':product_id+'-tests','revision':revision,'ruleCases':[], 'evidenceCases':refs})
    recipe_sha = core.save_recipe(actor, {'schemaVersion':'recipe.v0.1','id':product_id+'-recipe',
        'revision':revision,'productId':product_id,'sourceDigests':[source_sha], 'processes':['document'],
        'testSetDigest':test_sha,'intendedConsumers':consumers,'intendedHistoryReaders':consumers,
        'versionPolicy':'PINNED'}, revision-1)
    artifact_sha = core.register_artifact(actor, {'schemaVersion':'artifact.v0.1',
        'id':product_id+'-evidence','revision':revision,'kind':'evidence','sourceDigests':[source_sha],
        'scope':scope,'evidence':refs,'ruleSetDigest':None})
    candidate_sha = core.create_candidate(actor,recipe_sha,[artifact_sha])
    document_candidate = core.create_document_candidate(actor,candidate_sha,index_sha,tests)
    return {'sourceDigest':source_sha,'indexDigest':index_sha,'recipeDigest':recipe_sha,
            'artifactDigest':artifact_sha,'coreCandidateDigest':candidate_sha,'candidateDigest':document_candidate}
