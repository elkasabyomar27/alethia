"""Real FAISS/SQLite mechanics with synthetic vectors; not model-quality tests."""

import json
import time
import pytest

from test_dense import configured,add,build
from app.evaluation.dataset import Example
from app.evaluation.store import EvaluationStore
from app.evaluation.runner import EvaluationRunner,markdown_report
from app.ingestion import IngestionError


def setup(configured,tmp_path):
    _,docs,manager=configured
    add(docs,'shipping within 3 days.','policy.txt'); build(manager)
    example=Example(id='shipping',group_id='shipping',question='shipping',language='en',category='factual',
        reference_answer='3 days.',answerable=True,evidence=[{'document':'policy.txt','quote':'shipping within 3 days.','grade':1}])
    path=tmp_path/'fixture.json'; path.write_text(json.dumps({'dataset_id':'synthetic-fixture','examples':[example.model_dump()]}))
    store=EvaluationStore(tmp_path/'eval.sqlite3',docs,tmp_path/'reports',path)
    return docs,manager,store,example,EvaluationRunner(store,manager)


def wait(store,identity):
    deadline=time.monotonic()+5
    while store.run(identity)['status']=='running' and time.monotonic()<deadline: time.sleep(.01)
    return store.run(identity)


def test_diagnostics_do_not_score_unreviewed_cases_and_approved_fixture_scores_shared_corpus(configured,tmp_path):
    _,_,store,example,runner=setup(configured,tmp_path)
    with pytest.raises(IngestionError,match='No currently reviewed'): runner.start(['bm25'],True)
    first=runner.start(['bm25','dense','hybrid'],False)
    assert wait(store,first['id'])['status']=='complete'
    diagnostic=store.report(first['id'])
    assert diagnostic['candidate_pack_fingerprint']==store.dataset()['candidate_pack_fingerprint']
    assert all(value['scored_count']==0 and value['metrics'] is None for value in diagnostic['summary'].values())
    assert all(row['metrics'] is None for row in diagnostic['results'])
    assert len(diagnostic['results'])==3 and 'Not scored' in markdown_report(diagnostic)
    store.review(example.id,example,0,True,'Synthetic temporary test attestation')
    scored=runner.start(['bm25','dense','hybrid'],True)
    assert wait(store,scored['id'])['status']=='complete'
    report=store.report(scored['id'])
    for summary in report['summary'].values():
        assert summary['scored_count']==1 and summary['metrics']['recall_at_5']==1
        assert summary['metrics']['precision_at_5']==.2
    assert len({row['corpus_hash'] for row in report['configurations'].values()})==1


def test_library_change_during_run_never_publishes_partial_scores(configured,tmp_path,monkeypatch):
    docs,manager,store,_,runner=setup(configured,tmp_path)
    original=manager.search
    def changing(*args,**kwargs):
        result=original(*args,**kwargs); add(docs,'warranty information','new.txt'); return result
    monkeypatch.setattr(manager,'search',changing)
    run=runner.start(['bm25'],False)
    failed=wait(store,run['id'])
    assert failed['status']=='failed' and failed['summary'] is None
    assert not store.report_path(run['id']).exists()


def test_busy_unknown_method_and_shutdown_are_clear(configured,tmp_path):
    _,_,store,_,runner=setup(configured,tmp_path)
    with pytest.raises(IngestionError): runner.start(['bm25','bm25'],False)
    with pytest.raises(IngestionError): runner.start(['rerank'],False)
    runner.guard.acquire()
    with pytest.raises(IngestionError,match='already running'): runner.start(['bm25'],False)
    runner.guard.release(); runner.close()
    with pytest.raises(IngestionError,match='shutting down'): runner.start(['bm25'],False)


def test_identical_corpus_rebuild_during_run_is_not_silently_mixed(configured,tmp_path,monkeypatch):
    _,manager,store,_,runner=setup(configured,tmp_path)
    original=manager.search
    def rebuilding(*args,**kwargs):
        result=original(*args,**kwargs); build(manager); return result
    monkeypatch.setattr(manager,'search',rebuilding)
    run=runner.start(['bm25'],False)
    assert wait(store,run['id'])['status']=='failed'
    assert not store.report_path(run['id']).exists()
