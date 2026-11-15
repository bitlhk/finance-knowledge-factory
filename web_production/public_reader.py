"""Bounded public archive reader; never calls production or consumption services."""
from collections import OrderedDict
from copy import deepcopy
import json
import threading
import time

from knowledge_core.contracts import Rejected
from web_production.published import catalog


class PublicReader:
    def __init__(self, config, *, clock=time.monotonic, ttl=15, limit=120):
        self.config = config
        self.clock, self.ttl, self.limit = clock, ttl, limit
        self.lock = threading.Lock()
        self.cache = OrderedDict()
        self.window, self.requests = clock(), 0

    def admit(self):
        # Aggregate budget also bounds reverse-proxy traffic. Never trust client XFF.
        with self.lock:
            now = self.clock()
            if now - self.window >= 60:
                self.window, self.requests = now, 0
            self.requests += 1
            return self.requests <= self.limit

    def _read(self, code):
        with self.lock:
            now = self.clock()
            cached = self.cache.get(code)
            if cached and now - cached[0] < self.ttl:
                self.cache.move_to_end(code)
                return deepcopy(cached[1])
            self.cache.pop(code, None)
            result = catalog(self.config, code)
            # At most eight verified public projections; never cache a failed refresh.
            size = len(json.dumps(result, ensure_ascii=False).encode())
            if size <= 2_000_000:
                while len(self.cache) >= 8:
                    self.cache.popitem(last=False)
                self.cache[code] = (self.clock(), result)
            return deepcopy(result)

    def summary(self, code=None):
        result = self._read(code)
        if code:
            pages = result.pop('pages')
            result['pageIndex'] = [{k: p[k] for k in ('sourceId', 'page', 'htmlId')}
                                   for p in pages]
        return result

    def page(self, code, number):
        result = self._read(code)
        pages = result['pages']
        if not 1 <= number <= len(pages):
            raise Rejected('PUBLICATION_PAGE_NOT_FOUND')
        return {'code': code, 'manifestDigest': result['manifestDigest'],
                'pageNumber': number, 'totalPages': len(pages), 'page': pages[number - 1]}

    def replay(self, code):
        result = self.summary(code)
        return {'code': code, 'title': result['title'], 'readOnly': True,
                'recordKind': 'PUBLICATION_ARCHIVE_NOT_EXECUTION_TRACE',
                'manifestDigest': result['manifestDigest'],
                'stages': [
                    {'title': '原料校验', 'status': 'VERIFIED', 'evidence': result['sources']},
                    {'title': '原文页码映射', 'status': 'ARCHIVED',
                     'evidence': {'pageCount': len(result['pageIndex'])}},
                    {'title': '候选版本', 'status': 'ARCHIVED',
                     'evidence': {'candidateDigest': result['candidateDigest']}},
                    {'title': '质量准入', 'status': result['qualityDecision'],
                     'evidence': {'checks': result['checks'], 'caseCount': result['caseCount'],
                                  'qualityAdmissionDigest': result['qualityAdmissionDigest']}},
                    {'title': '审批与开发环境发布', 'status': 'ARCHIVED',
                     'evidence': {'approvalMode': result['approvalMode'],
                                  'approvalDigest': result['approvalDigest'],
                                  'manifestDigest': result['manifestDigest'],
                                  'productionAuthorized': result['productionAuthorized']}},
                ]}
