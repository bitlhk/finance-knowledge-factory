"""Controlled transport tests, not evidence of a running RAGFlow or Harness."""
import copy
from dataclasses import replace
from pathlib import Path

import pytest

from knowledge_core.contracts import Rejected
from knowledge_core.core import Actor
from knowledge_core.documents import DocumentCore
from m2.pipeline import parse, produce
from tests.support import AUTHOR, READER, CONTEXT, ir, policy, prepare

AUTHOR = replace(AUTHOR, privileges=AUTHOR.privileges | {'document.approve'})
RAW = (Path(__file__).parent / 'fixtures/m2-document.html').read_bytes()
CASES = [
    {'question':'合成客服服务时间是什么？','expectedClause':'第一条'},
    {'question':'客户如何申请历史对账单？','expectedClause':'第二条'},
    {'question':'信息缺失时如何处理？','expectedClause':'第三条'},
]


class ControlledClient:
    def __init__(self):
        self.calls = 0
        self.callback = None
        self.error = None
        self.tamper = False

    def ingest(self, raw):
        self.chunks = [{'id':f'chunk-{i}', 'text':c['text']} for i,c in enumerate(parse(raw))]
        return {'datasetId':'test-dataset','documentId':'test-doc','buildId':'test-build',
                'engineIdentity':'CONTROLLED_TEST_ONLY','embeddingIdentity':'NONE',
                'chunks':copy.deepcopy(self.chunks)}

    def retrieve(self, dataset_id, document_id, question):
        self.calls += 1
        if self.callback:
            self.callback()
        if self.error:
            raise Rejected(self.error)
        i = next(i for i,c in enumerate(CASES) if c['question']==question)
        chunk = self.chunks[i]
        return [{'id':chunk['id'], 'text':chunk['text']+('fake' if self.tamper else ''),
                 'documentId':document_id}]


@pytest.fixture
def prepared(tmp_path):
    db = tmp_path / 'core.db'
    core, client = DocumentCore(db), ControlledClient()
    core.set_policy(AUTHOR,policy(),0)
    data = produce(core,AUTHOR,'faq',1,RAW,ir()['rules'][0]['scope'],CASES,['reader'],client)
    yield core,client,data,db
    core.close()


def released(prepared, activate=True):
    core,client,data,_ = prepared
    if activate:
        core.activate_source(AUTHOR,data['sourceDigest'],'2026-01-01')
    validation = core.validate_document(AUTHOR,data['candidateDigest'],client)
    approval = core.approve_document(AUTHOR,data['candidateDigest'],validation,'Synthetic test approval only')
    manifest = core.publish_document(AUTHOR,data['candidateDigest'],validation,approval,1)
    core.bind_document(AUTHOR,manifest,0)
    return manifest,validation,approval


def query(prepared, manifest, actor=READER, context=CONTEXT):
    core,client,_,_ = prepared
    return core.query_document(actor,'faq',manifest,context,CASES[0]['question'],'req-1','trace-1',client)


def test_lifecycle_restart_and_zero_execution_replay(prepared):
    core,client,data,db = prepared
    manifest,validation,approval = released(prepared)
    receipt = query(prepared,manifest)
    assert receipt['result']['decision']=='EVIDENCE_FOUND'
    assert receipt['result']['evidence'][0]['anchors'][0]['quote'] in RAW.decode()
    assert core._get(AUTHOR,manifest,'document-manifest')['approvalDigest']==approval
    reopened = DocumentCore(db)
    try:
        before = client.calls
        assert reopened.replay_document(READER,receipt['receiptDigest'])['result']==receipt['result']
        assert client.calls == before
    finally:
        reopened.close()


def test_candidate_cannot_be_queried_or_bound(prepared):
    core,client,data,_ = prepared
    with pytest.raises(Rejected):
        query(prepared,data['candidateDigest'])
    with pytest.raises(Rejected):
        core.bind_document(AUTHOR,data['candidateDigest'],0)
    assert client.calls==0


@pytest.mark.parametrize('error',['RAGFLOW_BUSINESS_ERROR','RAGFLOW_UNAVAILABLE'])
def test_failed_validation_cannot_be_approved(prepared,error):
    core,client,data,_ = prepared
    client.error = error
    validation = core.validate_document(AUTHOR,data['candidateDigest'],client)
    assert not core._get(AUTHOR,validation,'document-validation')['passed']
    with pytest.raises(Rejected,match='DOCUMENT_VALIDATION_FAILED'):
        core.approve_document(AUTHOR,data['candidateDigest'],validation,'test')


def test_approval_required(prepared):
    core,client,data,_ = prepared
    validation = core.validate_document(AUTHOR,data['candidateDigest'],client)
    with pytest.raises(Rejected):
        core.publish_document(AUTHOR,data['candidateDigest'],validation,validation,1)
    with pytest.raises(Rejected,match='FORBIDDEN'):
        core.approve_document(READER,data['candidateDigest'],validation,'test')


@pytest.mark.parametrize('case',['manifest','user','tenant','source','context','not-effective'])
def test_denied_before_retrieval(prepared,case):
    core,client,data,_ = prepared
    manifest,_,_ = released(prepared,activate=case!='not-effective')
    actor, context = READER,CONTEXT
    if case=='manifest': manifest='0'*64
    if case=='user': actor=replace(READER,principal='outsider')
    if case=='tenant': actor=replace(READER,tenant='other-tenant')
    if case=='context': context=replace(CONTEXT,source='')
    if case=='source': core.set_policy(AUTHOR,policy(2,source_reader=False),1)
    before=client.calls
    with pytest.raises(Rejected): query(prepared,manifest,actor,context)
    assert client.calls==before


def test_return_time_source_revocation(prepared):
    core,client,_,_ = prepared
    manifest,_,_ = released(prepared)
    client.callback=lambda:core.set_policy(AUTHOR,policy(2,source_reader=False),1)
    with pytest.raises(Rejected,match='FORBIDDEN'): query(prepared,manifest)
    assert core.db.execute("SELECT count(*) FROM objects WHERE kind='document-receipt'").fetchone()[0]==0


def test_mutated_upstream_text_is_not_disclosed(prepared):
    _,client,_,_=prepared
    manifest,_,_=released(prepared)
    client.tamper=True
    with pytest.raises(Rejected,match='RETRIEVAL_INDEX_MISMATCH'): query(prepared,manifest)


def test_draft_does_not_change_published_snapshot(prepared):
    core,client,data,_=prepared
    manifest,_,_=released(prepared)
    old=query(prepared,manifest)
    recipe=core._get(AUTHOR,data['recipeDigest'],'recipe')
    recipe.update(revision=2,intendedConsumers=['other-reader'])
    core.save_recipe(AUTHOR,recipe,1)
    assert query(prepared,manifest)['result']==old['result']
    with pytest.raises(Rejected,match='VERSION_CONFLICT'):
        core.bind_document(AUTHOR,manifest,0)


def test_source_registration_is_not_activation(prepared):
    core,_,data,_=prepared
    manifest,_,_=released(prepared)
    source=core._get(AUTHOR,data['sourceDigest'],'source-revision')
    source['revision']=2
    core.register_source(AUTHOR,source)
    assert query(prepared,manifest)['result']['decision']=='EVIDENCE_FOUND'


def test_history_uses_current_permission(prepared):
    core,_,_,_=prepared
    manifest,_,_=released(prepared)
    receipt=query(prepared,manifest)
    core.set_policy(AUTHOR,policy(2,history=False),1)
    with pytest.raises(Rejected,match='FORBIDDEN'):
        core.replay_document(READER,receipt['receiptDigest'])


def test_null_context(prepared):
    manifest,_,_=released(prepared)
    with pytest.raises(Rejected,match='TRUSTED_CONTEXT_REQUIRED'):
        query(prepared,manifest,context=None)


def test_wrong_validation_cannot_approve(prepared):
    core,client,data,_=prepared
    good=core.validate_document(AUTHOR,data['candidateDigest'],client)
    other=core.create_document_candidate(AUTHOR,data['coreCandidateDigest'],data['indexDigest'],CASES[:1])
    with pytest.raises(Rejected,match='DOCUMENT_VALIDATION_FAILED_OR_MISMATCH'):
        core.approve_document(AUTHOR,other,good,'test')


def test_approval_bound_to_exact_candidate(prepared):
    core,client,data,_=prepared
    _,_,approval=released(prepared)
    other=core.create_document_candidate(AUTHOR,data['coreCandidateDigest'],data['indexDigest'],CASES[:1])
    validation=core.validate_document(AUTHOR,other,client)
    with pytest.raises(Rejected,match='DOCUMENT_APPROVAL_MISMATCH'):
        core.publish_document(AUTHOR,other,validation,approval,2)


def test_source_revision_activation_blocks_old_manifest(prepared):
    core,_,data,_=prepared
    manifest,_,_=released(prepared)
    source=core._get(AUTHOR,data['sourceDigest'],'source-revision')
    source['revision']=2
    new=core.register_source(AUTHOR,source)
    core.activate_source(AUTHOR,new,'2026-10-01')
    with pytest.raises(Rejected,match='SOURCE_SUPERSEDED_OR_REVOKED'):
        query(prepared,manifest)


def test_changed_draft_blocks_new_publication(prepared):
    core,_,data,_=prepared
    _,validation,approval=released(prepared)
    recipe=core._get(AUTHOR,data['recipeDigest'],'recipe')
    recipe['revision']=2
    core.save_recipe(AUTHOR,recipe,1)
    with pytest.raises(Rejected,match='DRAFT_CHANGED_REVALIDATE'):
        core.publish_document(AUTHOR,data['candidateDigest'],validation,approval,2)


def test_sql_objects_remain_immutable(prepared):
    import sqlite3
    core,_,_,_=prepared
    released(prepared)
    with pytest.raises(sqlite3.IntegrityError,match='IMMUTABLE_OBJECT'):
        core.db.execute("UPDATE objects SET body='{}' WHERE kind='document-manifest'")


def test_rule_candidate_cannot_use_document_release(prepared):
    core,_,data,_=prepared
    rules=prepare(core,'credit')
    with pytest.raises(Rejected,match='DOCUMENT_ONLY_REQUIRED'):
        core.create_document_candidate(AUTHOR,rules['candidate'],data['indexDigest'],CASES)


@pytest.mark.parametrize('raw',[b'not html',b'<html><p>No numbered clauses</p></html>',b''])
def test_unsupported_input_before_ingestion(prepared,raw):
    core,_,_,_=prepared
    client=ControlledClient()
    with pytest.raises(Rejected):
        produce(core,AUTHOR,'faq',2,raw,ir()['rules'][0]['scope'],CASES,['reader'],client)
    assert not hasattr(client,'chunks')


def test_invalid_gold_before_ingestion(prepared):
    core,_,_,_=prepared
    client=ControlledClient()
    with pytest.raises(Rejected,match='RETRIEVAL_GOLD_INVALID'):
        produce(core,AUTHOR,'faq',2,RAW,ir()['rules'][0]['scope'],[],['reader'],client)
    assert not hasattr(client,'chunks')
