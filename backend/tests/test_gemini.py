"""Mocked cloud contract checks. Never use a real API key or external request."""

import json

import pytest

from app import generation_config
from app.ingestion import IngestionError
from app.rag import gemini
from app.rag.gemini import GeminiClient, GEMINI_MODEL
from app.rag.oracle import Oracle, ModelAnswer


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(gemini,'settings',lambda: {'GEMINI_API_KEY':'unit-test-credential'})
    return GeminiClient()


def response(text='{"status":"insufficient_evidence","claims":[]}',finish='STOP'):
    return {'modelVersion':'gemini-3.1-flash-lite-test','candidates':[{'finishReason':finish,
        'content':{'parts':[{'text':text}]}}], 'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':15}}


def mock_connection(monkeypatch,payload,status=200):
    calls = []
    class Connection:
        def __init__(self,host,timeout): calls.append({'host':host,'timeout':timeout})
        def request(self,method,path,body,headers): calls[-1].update(method=method,path=path,body=json.loads(body),headers=headers)
        def getresponse(self):
            class Response:
                def read(self,limit): return payload if isinstance(payload,bytes) else json.dumps(payload).encode()
            result = Response(); result.status = status
            return result
        def close(self): calls[-1]['closed'] = True
    monkeypatch.setattr(gemini.http.client,'HTTPSConnection',Connection)
    return calls


def test_key_only_in_header_and_status_does_not_claim_verified_connection(client,monkeypatch):
    calls = mock_connection(monkeypatch,response())
    schema = ModelAnswer.model_json_schema()
    output = client.generate([{'content':'System rules'},{'content':'Fictional evidence and question'}],schema)
    sent = calls[0]
    assert sent['host'] == 'generativelanguage.googleapis.com'
    assert sent['path'] == f'/v1beta/models/{GEMINI_MODEL}:generateContent'
    assert sent['headers']['x-goog-api-key'] == 'unit-test-credential'
    assert 'unit-test-credential' not in json.dumps(sent['body'])+sent['path']+json.dumps(client.inspect())+json.dumps(output)
    assert client.inspect()['connection_verified'] is False
    config = sent['body']['generationConfig']
    assert config['responseFormat']['text']['schema'] == schema
    assert config['maxOutputTokens'] == 1024
    assert 'tools' not in sent['body'] and sent['closed']
    assert output['model_version'] == 'gemini-3.1-flash-lite-test'


@pytest.mark.parametrize('status',[302,400,401,403,429,500])
def test_errors_are_sanitized_and_never_retried_or_redirected(client,monkeypatch,status):
    calls = mock_connection(monkeypatch,{'error':{'message':'unit-test-credential private prompt'}},status)
    with pytest.raises(IngestionError) as error: client.generate([{'content':'system'},{'content':'question'}],{})
    assert 'unit-test-credential' not in str(error.value) and 'private prompt' not in str(error.value)
    assert error.value.status == (429 if status==429 else 503)
    assert len(calls)==1 and calls[0]['closed']


@pytest.mark.parametrize('payload',[b'x'*65537,b'not json',{},response(finish='MAX_TOKENS'),
    {'candidates':[],'promptFeedback':{'blockReason':'SAFETY'}}, {'candidates':[{'finishReason':'STOP','content':{'parts':[{'functionCall':{}}]}}]}],
    ids=['oversized','invalid-json','empty','truncated','blocked','tool-only'])
def test_partial_blocked_oversized_or_malformed_responses_are_withheld(client,monkeypatch,payload):
    mock_connection(monkeypatch,payload)
    with pytest.raises(IngestionError): client.generate([{'content':'system'},{'content':'question'}],{})


def test_missing_key_does_not_open_a_connection_and_paid_model_switch_is_rejected(monkeypatch):
    monkeypatch.setattr(gemini,'settings',lambda: {})
    client = GeminiClient()
    assert client.inspect()['state']=='key_missing'
    def fail(*args,**kwargs): raise AssertionError('Network must not run')
    monkeypatch.setattr(gemini.http.client,'HTTPSConnection',fail)
    with pytest.raises(IngestionError,match='replacement GEMINI_API_KEY'):
        client.generate([{'content':'system'},{'content':'question'}],{})
    monkeypatch.setattr(gemini,'settings',lambda: {'GEMINI_MODEL':'paid-model'})
    with pytest.raises(ValueError,match='supports only'): GeminiClient()


def test_env_file_is_backend_whitelisted_and_environment_wins(tmp_path,monkeypatch):
    path=tmp_path/'.env'
    path.write_text('GEMINI_API_KEY="file-unit-key"\nGEMINI_MODEL=gemini-3.1-flash-lite\nVITE_LEAK=ignored\nOTHER_KEY=ignored',encoding='utf8')
    monkeypatch.setattr(generation_config,'ENV_PATH',path)
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    assert generation_config.settings()['GEMINI_API_KEY']=='file-unit-key'
    assert 'VITE_LEAK' not in generation_config.settings()
    monkeypatch.setenv('GEMINI_API_KEY','environment-unit-key')
    assert generation_config.settings()['GEMINI_API_KEY']=='environment-unit-key'


def test_cloud_oracle_never_checks_vram_or_reserves_local_llm_memory(client,monkeypatch):
    from app.rag import oracle as module
    from test_oracle import FakeDense, row
    dense=FakeDense()
    instance=Oracle(dense); instance.client=client
    def fail(*args,**kwargs): raise AssertionError('Local LLM operation must not run')
    monkeypatch.setattr(module,'available_vram_mib',fail)
    monkeypatch.setattr(dense,'_claim',fail)
    text=dense.rows[0]['text']
    answer=json.dumps({'status':'answer','claims':[{'text':'Unused products can be returned within 14 days.',
        'evidence':[{'source_id':'S1','quote':text}]}]})
    mock_connection(monkeypatch,response(answer))
    result=instance.ask('What is the return policy?')
    assert result['status']=='answered' and result['provider']=='gemini' and result['model_digest'] is None
    assert not dense.busy and not instance.pending_cleanup
