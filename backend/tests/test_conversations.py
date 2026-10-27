import copy
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.conversations import ConversationStore
from app import conversations as module
from app.database import DocumentStore
from app.ingestion import extract_document, IngestionError
from app.main import create_app


@pytest.fixture
def configured(tmp_path):
    docs = DocumentStore(tmp_path/'docs.sqlite3')
    document = docs.save(extract_document('policy.txt', '🌞 Return unused products within 14 days.'.encode()))['document']
    detail = docs.get(document['id'])
    parent = detail['segments'][0]
    response = {'question': 'What is the return window?', 'status':'answered','reason':None,
        'claims':[{'text':'Return unused products within 14 days.','evidence':[{'source_id':'S1','quote':'Return unused products within 14 days.'}]}],
        'sources':[{'source_id':'S1','document_id':document['id'],'id':parent['id'],'chunk_id':'chunk',
        'filename':'policy.txt','section':parent['section'],'revision':1,'start_char':parent['start_char'],
        'end_char':parent['end_char'],'text':parent['text']}], 'latency_ms':1, 'model':'fixture-not-a-real-generation',
        'model_digest':'fixture','prompt_version':'fixture','context_version':'fixture','corpus_hash':'fixture',
        'prompt_budget_bytes':10,'generation_diagnostics':None}
    store = ConversationStore(tmp_path/'conversations.sqlite3',docs)
    return store,docs,response


def test_restart_preserves_order_quotes_and_source_revision_state(configured):
    store,docs,response = configured
    first = store.append(response)
    second = store.append({**response,'question':'Second question'},first['conversation_id'],1)
    reopened = ConversationStore(store.path,docs)
    detail = reopened.get(first['conversation_id'])
    assert detail['revision'] == detail['turn_count'] == 2
    assert [turn['turn_id'] for turn in detail['turns']] == [first['turn_id'],second['turn_id']]
    assert detail['turns'][0]['sources'][0]['citation_state'] == 'current'
    doc_id = response['sources'][0]['document_id']
    docs.save(extract_document('new-policy.txt',b'Return within 7 days.'),doc_id)
    changed = reopened.get(first['conversation_id'])['turns'][0]
    assert changed['sources'][0]['citation_state'] == 'changed'
    assert changed['claims'] == response['claims']
    docs.delete(doc_id)
    assert reopened.get(first['conversation_id'])['turns'][0]['sources'][0]['citation_state'] == 'deleted'
    assert reopened.get(first['conversation_id'])['turns'][0]['sources'][0]['text'] == response['sources'][0]['text']


def test_concurrent_tab_compare_and_swap_prevents_lost_updates(configured):
    store,_,response = configured
    first = store.append(response)
    def append(_):
        try: return store.append(response,first['conversation_id'],1)['conversation_revision']
        except IngestionError as error: return error.status
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(append,range(2)))
    assert sorted(results) == [2,409]
    assert store.get(first['conversation_id'])['turn_count'] == 2


def test_deleted_conversation_cannot_be_resurrected_by_late_answer(configured):
    store,_,response = configured
    first = store.append(response)
    store.delete(first['conversation_id'])
    with pytest.raises(IngestionError) as error: store.append(response,first['conversation_id'],1)
    assert error.value.status == 404
    assert store.list() == []
    with store.connect() as connection: assert connection.execute('SELECT count(*) FROM turns').fetchone()[0] == 0


def test_limits_and_transaction_failure_do_not_create_empty_conversations(configured,monkeypatch):
    store,_,response = configured
    with store.connect() as connection:
        connection.execute("CREATE TRIGGER fail BEFORE INSERT ON turns BEGIN SELECT RAISE(ABORT,'test'); END")
    with pytest.raises(sqlite3.IntegrityError): store.append(response)
    assert store.list() == []
    with store.connect() as connection: connection.execute('DROP TRIGGER fail')
    monkeypatch.setattr(module,'MAX_TURNS',1)
    first = store.append(response)
    with pytest.raises(IngestionError,match='30 turns'): store.check(first['conversation_id'],1)
    monkeypatch.setattr(module,'MAX_CONVERSATIONS',1)
    with pytest.raises(IngestionError,match='limit'): store.append(response)
    monkeypatch.setattr(module,'MAX_TURN_BYTES',20)
    with pytest.raises(IngestionError,match='size limit'): store.append(response)


def test_same_revision_but_changed_source_text_does_not_make_saved_citation_current(configured):
    store,docs,response = configured
    first = store.append(response)
    with docs.connect() as connection:
        connection.execute('UPDATE documents SET text=? WHERE id=?',('tampered',response['sources'][0]['document_id']))
    assert store.get(first['conversation_id'])['turns'][0]['sources'][0]['citation_state'] == 'changed'


def test_history_api_revision_validation_persistence_and_delete(tmp_path,configured):
    _,_,response = configured
    # No model execution: this test validates API persistence and CAS only.
    with TestClient(create_app(tmp_path/'api-docs.sqlite3')) as client:
        calls = []
        client.app.state.oracle.ask = lambda question: (calls.append(question) or {**copy.deepcopy(response),'sources':[],'question':question})
        first = client.post('/api/oracle/ask',json={'question':'First question'}).json()
        identity = first['conversation_id']
        assert len(client.get('/api/oracle/conversations').json()) == 1
        assert client.get('/api/oracle/conversations/'+identity).json()['turn_count'] == 1
        assert client.post('/api/oracle/ask',json={'question':'Conflict','conversation_id':identity,'expected_revision':2}).status_code == 409
        assert len(calls) == 1
        assert client.post('/api/oracle/ask',json={'question':'Second','conversation_id':identity,'expected_revision':1}).status_code == 200
        assert client.post('/api/oracle/ask',json={'question':'Bad','conversation_id':identity,'expected_revision':True}).status_code == 422
    with TestClient(create_app(tmp_path/'api-docs.sqlite3')) as client:
        assert client.get('/api/oracle/conversations/'+identity).json()['turn_count'] == 2
        assert client.delete('/api/oracle/conversations/'+identity).status_code == 204
        assert client.get('/api/oracle/conversations/'+identity).status_code == 404
