"""Local handoff workflow tests. No model generation or outbound messages."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.database import DocumentStore
from app.conversations import ConversationStore
from app.ingestion import extract_document, IngestionError
from app.main import create_app
from app.tickets import TicketStore
from app import tickets as module


@pytest.fixture
def configured(tmp_path):
    docs=DocumentStore(tmp_path/'docs.sqlite3')
    conversation=ConversationStore(tmp_path/'conversations.sqlite3',docs)
    tickets=TicketStore(tmp_path/'tickets.sqlite3',conversation)
    return docs,conversation,tickets


def turn(store,question='هل يوجد مخزون حالي؟',status='needs_human',reason='insufficient_evidence',sources=None):
    return store.append({'question':question,'status':status,'reason':reason,'claims':[],
        'sources':sources or [],'model':'fixture-no-inference','model_digest':None,'provider':'fixture',
        'model_version':None,'prompt_version':'fixture','context_version':'fixture','corpus_hash':None,
        'prompt_budget_bytes':0,'latency_ms':0,'generation_diagnostics':None})


def create(store,saved): return store.create(saved['conversation_id'],saved['turn_id'])


def test_ticket_creation_is_explicit_idempotent_and_survives_restart(configured):
    _,conversations,tickets=configured
    saved=turn(conversations)
    assert tickets.list()==[]  # Merely abstaining must not silently create a ticket.
    first=create(tickets,saved)
    duplicate=create(tickets,saved)
    assert first['outcome']=='created' and duplicate['outcome']=='existing'
    assert first['ticket']['id']==duplicate['ticket']['id']
    assert len(duplicate['ticket']['events'])==1
    reopened=TicketStore(tickets.path,conversations)
    assert reopened.get(first['ticket']['id'])==first['ticket']
    assert reopened.list('resolved')==[] and len(reopened.list('open'))==1
    assert reopened.links([saved['turn_id']])=={saved['turn_id']:first['ticket']['id']}


def test_two_simultaneous_creates_produce_one_ticket(configured):
    _,conversations,tickets=configured
    saved=turn(conversations)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:create(tickets,saved),range(2)))
    assert sorted(result['outcome'] for result in results)==['created','existing']
    assert len({result['ticket']['id'] for result in results})==1 and len(tickets.list())==1


def test_resolution_reopen_notes_and_revision_history(configured):
    _,conversations,tickets=configured
    identity=create(tickets,turn(conversations))['ticket']['id']
    with pytest.raises(IngestionError,match='resolution note'): tickets.update(identity,1,'resolved',' ')
    assert tickets.get(identity)['revision']==1
    working=tickets.update(identity,1,'in_progress','جارٍ مراجعة المخزون مع الموظف.')
    resolved=tickets.update(identity,2,'resolved','تمت مراجعة الحالة يدويًا في هذا الاختبار.')
    assert resolved['resolution']=='تمت مراجعة الحالة يدويًا في هذا الاختبار.'
    reopened=tickets.update(identity,3,'open','مطلوب تحقق إضافي.')
    assert reopened['resolution']=='' and len(reopened['events'])==4
    assert reopened['events'][2]['note']==resolved['resolution']
    noted=tickets.update(identity,4,'open','Internal note without a status change.')
    assert noted['events'][-1]['kind']=='note_added'
    with pytest.raises(IngestionError,match='new status'): tickets.update(identity,5,'open','')
    assert working['status']=='in_progress'


def test_compare_and_swap_prevents_concurrent_updates_and_stale_deletion(configured):
    _,conversations,tickets=configured
    identity=create(tickets,turn(conversations))['ticket']['id']
    def update(_):
        try: return tickets.update(identity,1,'in_progress','Review started')['revision']
        except IngestionError as error: return error.status
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(update,range(2)))
    assert sorted(results)==[2,409]
    with pytest.raises(IngestionError,match='changed'): tickets.delete(identity,1)
    assert len(tickets.get(identity)['events'])==2


def test_ticket_retains_snapshot_after_conversation_delete_and_marks_changed_sources(configured):
    docs,conversations,tickets=configured
    doc=docs.save(extract_document('policy.txt',b'Return within 14 days.'))['document']
    original=docs.get(doc['id']); parent=original['segments'][0]
    source={'source_id':'S1','document_id':doc['id'],'id':parent['id'],'chunk_id':'fixture',
        'filename':'policy.txt','section':parent['section'],'revision':1,'start_char':parent['start_char'],
        'end_char':parent['end_char'],'text':parent['text']}
    saved=turn(conversations,'Please review this answer','answered',None,[source])
    created=create(tickets,saved)['ticket']
    assert created['reason']=='requested_review' and created['snapshot']['sources'][0]['citation_state']=='current'
    conversations.delete(saved['conversation_id'])
    assert tickets.get(created['id'])['origin_available'] is False
    docs.save(extract_document('new.txt',b'Return within 7 days.'),doc['id'])
    assert tickets.get(created['id'])['snapshot']['sources'][0]['citation_state']=='changed'
    docs.delete(doc['id'])
    final=tickets.get(created['id'])
    assert final['snapshot']['sources'][0]['citation_state']=='deleted'
    assert final['snapshot']['sources'][0]['text']=='Return within 14 days.'


def test_missing_or_wrong_conversation_turn_is_not_accepted(configured):
    _,conversations,tickets=configured
    one,two=turn(conversations),turn(conversations,'Different question')
    with pytest.raises(IngestionError) as error: tickets.create(one['conversation_id'],two['turn_id'])
    assert error.value.status==404 and tickets.list()==[]
    saved=turn(conversations,'What about it?','needs_clarification','ambiguous_followup')
    assert create(tickets,saved)['ticket']['reason']=='clarification_review'


def test_ticket_and_event_caps_and_delete_cascade(configured,monkeypatch):
    _,conversations,tickets=configured
    first=turn(conversations)
    identity=create(tickets,first)['ticket']['id']
    monkeypatch.setattr(module,'MAX_TICKETS',1)
    assert create(tickets,first)['outcome']=='existing'
    with pytest.raises(IngestionError,match='limit'): create(tickets,turn(conversations,'Another question'))
    monkeypatch.setattr(module,'MAX_EVENTS',1)
    with pytest.raises(IngestionError,match='event limit'): tickets.update(identity,1,'in_progress','Review')
    tickets.delete(identity,1)
    with tickets.connect() as connection:
        assert connection.execute('SELECT count(*) FROM ticket_events').fetchone()[0]==0
    assert conversations.get(first['conversation_id'])['turn_count']==1


def test_failed_event_write_rolls_back_ticket_creation_and_status(configured):
    _,conversations,tickets=configured
    saved=turn(conversations)
    with tickets.connect() as connection:
        connection.execute("CREATE TRIGGER fail BEFORE INSERT ON ticket_events BEGIN SELECT RAISE(ABORT,'test'); END")
    with pytest.raises(sqlite3.IntegrityError): create(tickets,saved)
    assert tickets.list()==[]
    with tickets.connect() as connection: connection.execute('DROP TRIGGER fail')
    identity=create(tickets,saved)['ticket']['id']
    with tickets.connect() as connection:
        connection.execute("CREATE TRIGGER fail BEFORE INSERT ON ticket_events BEGIN SELECT RAISE(ABORT,'test'); END")
    with pytest.raises(sqlite3.IntegrityError): tickets.update(identity,1,'resolved','Resolved in test')
    original=tickets.get(identity)
    assert original['status']=='open' and original['revision']==1 and len(original['events'])==1


def test_api_flow_validates_payload_and_links_tickets_to_saved_answers(tmp_path,monkeypatch):
    from app.rag.gemini import GeminiClient
    from app.rag.ollama import OllamaClient
    def fail(*args,**kwargs): raise AssertionError('Ticket workflow must not call any LLM')
    monkeypatch.setattr(GeminiClient,'generate',fail); monkeypatch.setattr(OllamaClient,'generate',fail)
    path=tmp_path/'api-docs.sqlite3'
    with TestClient(create_app(path)) as client:
        saved=turn(client.app.state.conversations)
        body={'conversation_id':saved['conversation_id'],'turn_id':saved['turn_id']}
        response=client.post('/api/tickets',json=body)
        assert response.status_code==201,response.text
        ticket=response.json()['ticket']; identity=ticket['id']
        assert client.post('/api/tickets',json=body).status_code==200
        detail=client.get('/api/oracle/conversations/'+saved['conversation_id']).json()
        assert detail['turns'][0]['ticket_id']==identity
        assert client.get('/api/tickets?status=resolved').json()==[]
        assert client.get('/api/tickets?status=unknown').status_code==422
        assert client.post('/api/tickets',json={**body,'reason':'forged'}).status_code==422
        assert client.post('/api/tickets',json={**body,'turn_id':'invalid'}).status_code==422
        for bad in ({'expected_revision':True,'status':'open','note':'test'},
                    {'expected_revision':1,'status':'closed'},
                    {'expected_revision':1,'status':'open','note':'x'*2001}):
            assert client.patch('/api/tickets/'+identity,json=bad).status_code==422
        assert client.patch('/api/tickets/'+identity,json={'expected_revision':1,'status':'resolved'}).status_code==422
        assert client.patch('/api/tickets/'+identity,json={'expected_revision':1,'status':'in_progress','note':'Review started'}).status_code==200
        assert client.patch('/api/tickets/'+identity,json={'expected_revision':1,'status':'open'}).status_code==409
    with TestClient(create_app(path)) as client:
        assert client.get('/api/tickets/'+identity).json()['revision']==2
        assert client.delete('/api/tickets/'+identity+'?expected_revision=1').status_code==409
        assert client.delete('/api/tickets/'+identity+'?expected_revision=2').status_code==204
        assert client.get('/api/tickets/'+identity).status_code==404
        assert client.get('/api/oracle/conversations/'+saved['conversation_id']).json()['turns'][0]['ticket_id'] is None
