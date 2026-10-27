import json
import pytest
from pydantic import ValidationError

from app.database import DocumentStore
from app.ingestion import extract_document,IngestionError
from app.evaluation.dataset import Example,load_dataset,resolve_evidence
from app.evaluation.store import EvaluationStore


@pytest.fixture
def configured(tmp_path):
    docs=DocumentStore(tmp_path/'docs.sqlite3')
    docs.save(extract_document('policy.txt',b'Shipping normally takes 3 days.'))
    example=Example(id='shipping-en',group_id='shipping',question='How long does shipping take?',language='en',category='factual',
        reference_answer='Normally 3 days.',answerable=True,evidence=[{'document':'policy.txt','quote':'Shipping normally takes 3 days.','grade':1}])
    path=tmp_path/'dataset.json'
    path.write_text(json.dumps({'dataset_id':'fixture-not-a-benchmark','examples':[example.model_dump()]}),encoding='utf8')
    store=EvaluationStore(tmp_path/'eval.sqlite3',docs,tmp_path/'reports',path)
    return docs,store,example,path


def test_no_implicit_approval_draft_review_restart_and_library_invalidation(configured):
    docs,store,example,path=configured
    assert store.dataset()['examples'][0]['review_status']=='unreviewed'
    draft=store.review(example.id,example,0,False,'')
    assert draft['review_status']=='draft' and draft['reviewed_at'] is None
    with pytest.raises(IngestionError,match='name'): store.review(example.id,example,1,True,' ')
    # Synthetic attestation in a temporary test database, not a real human review.
    approved=store.review(example.id,example,1,True,'Synthetic test reviewer')
    assert approved['review_status']=='reviewed' and approved['revision']==2
    reopened=EvaluationStore(store.path,docs,store.reports,path)
    assert reopened.dataset()['examples'][0]==approved
    docs.save(extract_document('new.txt',b'An additional policy.'))
    assert reopened.dataset()['examples'][0]['review_status']=='stale'


def test_conflicts_invalid_quotes_and_changed_seed_do_not_reuse_approval(configured):
    docs,store,example,path=configured
    store.review(example.id,example,0,True,'Synthetic test reviewer')
    with pytest.raises(IngestionError,match='another tab'): store.review(example.id,example,0,False,'')
    bad=example.model_copy(deep=True); bad.evidence[0].quote='Invented evidence that was never uploaded.'
    with pytest.raises(IngestionError,match='absent'): store.review(example.id,bad,1,True,'Synthetic test reviewer')
    data=json.loads(path.read_text()); data['examples'][0]['reference_answer']='Changed candidate answer.'
    path.write_text(json.dumps(data))
    reopened=EvaluationStore(store.path,docs,store.reports,path)
    row=reopened.dataset()['examples'][0]
    assert row['review_status']=='unreviewed' and row['example']['reference_answer']=='Changed candidate answer.'


def test_labels_resolve_uniquely_and_same_filename_collision_is_rejected(configured):
    docs,_,example,_=configured
    evidence,_=resolve_evidence(example,docs)
    assert evidence[0]['source_id'] and evidence[0]['start_char']==0
    docs.save(extract_document('policy.txt',b'An unrelated file with the same filename.'))
    with pytest.raises(IngestionError,match='uniquely'): resolve_evidence(example,docs)


def test_unanswerable_labels_split_leakage_and_duplicate_ids_are_rejected(configured):
    _,_,example,path=configured
    with pytest.raises(ValidationError): Example.model_validate({**example.model_dump(),'answerable':False})
    other={**example.model_dump(),'id':'heldout-example','split':'test'}
    path.write_text(json.dumps({'dataset_id':'fixture','examples':[example.model_dump(),other]}))
    with pytest.raises(ValueError,match='cross'): load_dataset(path)
    path.write_text(json.dumps({'dataset_id':'fixture','examples':[example.model_dump(),example.model_dump()]}))
    with pytest.raises(ValueError,match='uniquely'): load_dataset(path)


def test_report_path_traversal_and_incomplete_runs_are_not_served(configured):
    _,store,_,_=configured
    with pytest.raises(IngestionError): store.report_path('../../private')
    identity='a'*32
    with store.connect() as connection:
        connection.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?)',(identity,'running','test',0,1,None,None))
    with pytest.raises(IngestionError,match='completed'): store.report(identity)
    _,_,_,path=configured
    reopened=EvaluationStore(store.path,store.documents,store.reports,path)
    assert reopened.run(identity)['status']=='interrupted'
