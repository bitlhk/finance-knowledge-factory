import hashlib
import json
import sqlite3

import pytest

from knowledge_core.contracts import Rejected, digest
from web_production.published import catalog


def fixture_catalog(tmp_path):
    def save(name, data):
        path = tmp_path / name
        path.write_text(json.dumps(data))
        return str(path)

    evaluation = {'cases': [{}], 'metricsBps': {'factAccuracy': 10000}}
    admission = {'decision': 'PASS', 'candidateDigest': 'candidate', 'sourceDigest': 'source',
                 'indexDigest': 'index', 'answerEvaluationDigest': digest(evaluation), 'checks': {'test': True}}
    approval = {'candidateDigest': 'candidate', 'qualityAdmissionDigest': digest(admission)}
    manifest = {'productId': 'fund-000343', 'candidateDigest': 'candidate', 'sourceDigest': 'source',
                'indexDigest': 'index', 'approvalDigest': digest(approval), 'revision': 1}
    database = tmp_path / 'core.sqlite'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE objects (digest,kind,body)')
        for kind, obj in [('document-manifest', manifest), ('document-approval', approval),
                          ('document-quality-admission', admission), ('document-answer-evaluation', evaluation)]:
            db.execute('INSERT INTO objects VALUES (?,?,?)', (digest(obj), kind, json.dumps(obj)))
    publication = save('publication.json', {'manifestDigest': digest(manifest), 'manifest': manifest,
        'qualityAdmissionDigest': digest(admission), 'database': str(database), 'ssoLoginAsserted': False,
        'productionAuthorized': False, 'applicability': [], 'limitations': [],
        'actor': 'private-user', 'authorizationReason': 'private-reason'})
    (tmp_path / 'source.pdf').write_bytes(b'public original')
    provenance = save('provenance.json', {'fundShareCode': '000343', 'pageCount': 1,
        'sourceFiles': [{'sourceId': 'summary', 'file': 'source.pdf',
                         'sha256': hashlib.sha256(b'public original').hexdigest(), 'pageCount': 1,
                         'officialUrl': 'https://example.org/original.pdf'}],
        'pages': [{'originalAnchor': {'sourceId': 'summary', 'page': 1}, 'htmlId': 'page-1', 'text': 'Original'}]})
    return save('catalog.json', {'products': [{'code': '000343', 'title': 'Public fund',
        'publication': publication, 'provenance': provenance,
        'provenanceSha256': hashlib.sha256((tmp_path / 'provenance.json').read_bytes()).hexdigest()}]})


def test_projection_is_read_only_and_omits_private_records(tmp_path):
    config = fixture_catalog(tmp_path)
    before = (tmp_path / 'core.sqlite').read_bytes()
    result = catalog(config)
    assert result['products'][0]['caseCount'] == 1
    assert result['products'][0]['approvalMode'] == 'MAINTENANCE'
    text = json.dumps(result)
    assert 'private-user' not in text and 'private-reason' not in text
    assert str(tmp_path) not in text and 'pages' not in result['products'][0]
    assert catalog(config, '000343')['pages'][0]['text'] == 'Original'
    assert (tmp_path / 'core.sqlite').read_bytes() == before


@pytest.mark.parametrize('code', ['../core.sqlite', '000051', '<script>'])
def test_requested_paths_cannot_select_files(tmp_path, code):
    with pytest.raises(Rejected, match='PUBLICATION_NOT_FOUND'):
        catalog(fixture_catalog(tmp_path), code)


def test_modified_original_fails_closed(tmp_path):
    config = fixture_catalog(tmp_path)
    (tmp_path / 'source.pdf').write_bytes(b'changed')
    with pytest.raises(Rejected, match='PUBLICATION_RECORD_UNAVAILABLE'):
        catalog(config)


def test_modified_database_object_fails_closed(tmp_path):
    config = fixture_catalog(tmp_path)
    with sqlite3.connect(tmp_path / 'core.sqlite') as db:
        db.execute("UPDATE objects SET body='{}' WHERE kind='document-manifest'")
    with pytest.raises(Rejected, match='PUBLICATION_RECORD_UNAVAILABLE'):
        catalog(config)


def test_unconfigured_is_not_fake_publication():
    assert catalog(None) == {'products': [], 'configured': False}


def test_unsafe_source_link_is_rejected(tmp_path):
    config = fixture_catalog(tmp_path)
    path = tmp_path / 'provenance.json'
    data = json.loads(path.read_text())
    data['sourceFiles'][0]['officialUrl'] = 'javascript:alert(1)'
    path.write_text(json.dumps(data))
    with pytest.raises(Rejected, match='PUBLICATION_RECORD_UNAVAILABLE'):
        catalog(config)
