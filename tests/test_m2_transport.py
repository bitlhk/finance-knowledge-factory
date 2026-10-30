"""HTTP envelope gates with controlled responses; not native service evidence."""
import io
import json
from urllib.error import HTTPError

import pytest

from knowledge_core.contracts import Rejected
from m2.ragflow import Ragflow, NoRedirect


class Response(io.BytesIO):
    headers = {}


class Opener:
    def __init__(self,payload): self.payload=payload
    def open(self,*args,**kwargs):
        if isinstance(self.payload,Exception): raise self.payload
        return Response(json.dumps(self.payload).encode())


@pytest.mark.parametrize('payload',[
    {'code':403,'data':{'content':'private'}},
    {'code':False,'data':{'content':'private'}},
    {'code':'0','data':{'content':'private'}},
    {'data':{'content':'private'}},
])
def test_http_success_cannot_mask_business_failure(payload):
    client=object.__new__(Ragflow)
    client.base='http://127.0.0.1:19380/api/v1';client.token=None;client.opener=Opener(payload)
    with pytest.raises(Rejected,match='RAGFLOW_BUSINESS_ERROR'):
        client._http('GET','/retrieval')


def test_redirect_not_followed():
    assert NoRedirect().redirect_request(None,None,302,'redirect',{},'http://external.invalid') is None


def test_endpoint_not_client_selectable(tmp_path):
    with pytest.raises(Rejected,match='UNAPPROVED_RAGFLOW_ENDPOINT'):
        Ragflow(tmp_path/'unused',tmp_path/'unused','http://external.invalid')


def test_http_error_redacts_body_and_token():
    client=object.__new__(Ragflow)
    client.base='http://127.0.0.1:19380/api/v1';client.token='secret-test'
    client.opener=Opener(HTTPError(client.base,403,'secret-test',{},None))
    with pytest.raises(Rejected) as err: client._http('GET','/retrieval')
    assert 'secret-test' not in str(err.value)


def test_foreign_dataset_rejected():
    client=object.__new__(Ragflow)
    client._http=lambda *a,**kw:({'chunks':[{'dataset_id':'other'}]}, {})
    with pytest.raises(Rejected,match='RAGFLOW_DATASET_MISMATCH'):
        client.retrieve('fixed','fixed','query')
