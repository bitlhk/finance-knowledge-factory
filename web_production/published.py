"""Read-only, explicit public-document projection. Never a consumption grant.

The operator configures exact publication/provenance files. No request may
select a database or filesystem path. Private receipts and identities stay out
of this projection, even though the underlying records contain them.
"""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

from knowledge_core.contracts import Rejected, digest


def _load(path):
    return json.loads(Path(path).read_text())


def _object(db, sha, kind):
    rows = db.execute('SELECT body FROM objects WHERE digest=? AND kind=?',
                      (sha, kind)).fetchall()
    if len(rows) != 1:
        raise ValueError('Missing or ambiguous object')
    body = json.loads(rows[0][0])
    if digest(body) != sha:
        raise ValueError('Object digest mismatch')
    return body


def catalog(config_path, code=None):
    if not config_path:
        if code:
            raise Rejected('PUBLICATION_NOT_FOUND')
        return {'products': [], 'configured': False}
    try:
        config = _load(config_path)
        entries = config['products']
        codes = [entry['code'] for entry in entries]
        if len(set(codes)) != len(codes) or any(not re.fullmatch(r'\d{6}', x) for x in codes):
            raise ValueError('Invalid configured code')
        if code is not None and code not in codes:
            raise Rejected('PUBLICATION_NOT_FOUND')
        results = []
        for entry in entries:
            if code is not None and entry['code'] != code:
                continue
            publication = _load(entry['publication'])
            provenance_path = Path(entry['provenance'])
            provenance = _load(provenance_path)
            if provenance['fundShareCode'] != entry['code']:
                raise ValueError('Product mismatch')
            with sqlite3.connect(Path(publication['database']).resolve().as_uri() + '?mode=ro',
                                 uri=True) as db:
                db.execute('PRAGMA query_only=ON')
                manifest = _object(db, publication['manifestDigest'], 'document-manifest')
                admission = _object(db, publication['qualityAdmissionDigest'], 'document-quality-admission')
                approval = _object(db, manifest['approvalDigest'], 'document-approval')
                evaluation = _object(db, admission['answerEvaluationDigest'], 'document-answer-evaluation')
            if (manifest != publication['manifest']
                    or manifest['productId'] != 'fund-' + entry['code']
                    or admission['decision'] != 'PASS'
                    or admission['candidateDigest'] != manifest['candidateDigest']
                    or approval['candidateDigest'] != manifest['candidateDigest']
                    or approval['qualityAdmissionDigest'] != publication['qualityAdmissionDigest']
                    or admission['sourceDigest'] != manifest['sourceDigest']
                    or admission['indexDigest'] != manifest['indexDigest']):
                raise ValueError('Publication binding mismatch')
            sources = []
            for source in provenance['sourceFiles']:
                path = provenance_path.parent / source['file']
                if path.resolve().parent != provenance_path.parent.resolve():
                    raise ValueError('Source path escapes archive')
                if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
                    raise ValueError('Source checksum mismatch')
                url = urlsplit(source['officialUrl'])
                if url.scheme != 'https' or not url.netloc or url.username or url.password:
                    raise ValueError('Unsafe source URL')
                sources.append({key: source[key] for key in
                                ('sourceId', 'file', 'sha256', 'pageCount', 'officialUrl')})
            item = {'code': entry['code'], 'title': entry['title'],
                    'manifestDigest': publication['manifestDigest'],
                    'candidateDigest': manifest['candidateDigest'],
                    'qualityAdmissionDigest': publication['qualityAdmissionDigest'],
                    'approvalDigest': manifest['approvalDigest'],
                    'revision': manifest['revision'], 'qualityDecision': admission['decision'],
                    'caseCount': len(evaluation['cases']), 'metricsBps': evaluation['metricsBps'],
                    'sources': sources, 'pageCount': provenance['pageCount'],
                    'approvalMode': 'SSO' if publication['ssoLoginAsserted'] else 'MAINTENANCE',
                    'productionAuthorized': publication['productionAuthorized'],
                    'applicability': publication['applicability'],
                    'limitations': publication['limitations'],
                    'recordKind': 'PUBLICATION_RECORD_NOT_ACCESS_GRANT'}
            if code:
                item['pages'] = [{'sourceId': p['originalAnchor']['sourceId'],
                                  'page': p['originalAnchor']['page'],
                                  'htmlId': p['htmlId'], 'text': p['text']}
                                 for p in provenance['pages']]
                item['checks'] = admission['checks']
            results.append(item)
        return results[0] if code else {'products': results, 'configured': True}
    except Rejected:
        raise
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        raise Rejected('PUBLICATION_RECORD_UNAVAILABLE') from None
