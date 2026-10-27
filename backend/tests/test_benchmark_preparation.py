"""Candidate structure and isolation checks; these are not human reviews."""

from collections import Counter
import json
import pytest

from app.database import DocumentStore
from app.ingestion import extract_document,IngestionError
from app.evaluation.dataset import ROOT,RESERVED_PATH,load_dataset,resolve_evidence,EvidenceLabel
from app.evaluation.store import EvaluationStore
from app.evaluation.audit import development_audit,review_packet
from test_evaluation_runner import configured,setup,wait


def test_candidate_pack_is_balanced_grouped_and_all_quotes_exist(tmp_path):
    _,examples=load_dataset()
    private_count=30 if RESERVED_PATH.exists() else 0
    assert len(examples)==120+private_count
    per_language=40+private_count//3
    assert Counter(row.language for row in examples)=={'en':per_language,'ar_msa':per_language,'ar_egy':per_language}
    assert sum(row.split=='dev' for row in examples)==120
    assert sum(row.split=='test' for row in examples)==private_count
    assert len({row.group_id for row in examples})==40+private_count//3
    for group in {row.group_id for row in examples}:
        family=[row for row in examples if row.group_id==group]
        assert len(family)==3 and len({row.split for row in family})==1
    docs=DocumentStore(tmp_path/'docs.sqlite3')
    for path in sorted((ROOT/'data'/'demo'/'ecommerce').glob('*.md')):
        docs.save(extract_document(path.name,path.read_bytes()))
    for example in examples:
        labels,_=resolve_evidence(example,docs)
        assert bool(labels)==example.answerable


def test_public_pack_contains_only_development_and_private_merge_is_validated(tmp_path):
    public=ROOT/'data/benchmarks/development.json'
    payload=json.loads(public.read_text(encoding='utf8'))
    assert len(payload['examples'])==120
    assert all(row['split']=='dev' for row in payload['examples'])
    fixture=tmp_path/'development.json'
    fixture.write_text(json.dumps(payload),encoding='utf8')
    assert len(load_dataset(fixture)[1])==120
    reserved=tmp_path/'reserved.json'
    candidate={**payload['examples'][0],'id':'private-holdout','group_id':'private-group',
        'split':'test','question':'An independent reserved request?',
        'answerable':False,'reference_answer':'No supporting evidence.','evidence':[]}
    reserved.write_text(json.dumps({'dataset_id':payload['dataset_id'],'examples':[candidate]}),encoding='utf8')
    assert len(load_dataset(fixture,reserved_path=reserved)[1])==121
    candidate['split']='dev'
    reserved.write_text(json.dumps({'dataset_id':payload['dataset_id'],'examples':[candidate]}),encoding='utf8')
    with pytest.raises(ValueError,match='test examples only'):
        load_dataset(fixture,reserved_path=reserved)


def test_duplicate_question_cannot_hide_behind_a_different_group(tmp_path):
    _,examples=load_dataset(); first=examples[0].model_dump()
    second={**first,'id':'other-question','group_id':'different-group','split':'test',
        'question':'  '+first['question'].upper()+'   '}
    path=tmp_path/'candidates.json'
    path.write_text(json.dumps({'dataset_id':'fixture','examples':[first,second]}))
    with pytest.raises(ValueError,match='Duplicate normalized'): load_dataset(path)


def test_contained_label_quotes_cannot_cross_split(tmp_path):
    _,examples=load_dataset(); first=examples[0].model_dump()
    second={**first,'id':'other-question','group_id':'different-group','split':'test','question':'A different wording?',
        'evidence':[{**first['evidence'][0],'quote':'within 14 calendar days of delivery.'}]}
    path=tmp_path/'candidates.json'
    path.write_text(json.dumps({'dataset_id':'fixture','examples':[first,second]}))
    with pytest.raises(ValueError,match='evidence cannot cross'): load_dataset(path)


def test_preflight_resolves_chunks_without_search_or_review(configured,tmp_path,monkeypatch):
    _,manager,store,_,_=setup(configured,tmp_path)
    def forbidden(*args,**kwargs): raise AssertionError('Preflight must not search or infer.')
    monkeypatch.setattr(manager,'search',forbidden)
    audit=development_audit(store,manager)
    assert audit['invalid_count']==0 and audit['encoder_generation']
    assert audit['results'][0]['positive_chunk_count']==1
    assert store.dataset()['examples'][0]['review_status']=='unreviewed'
    assert store.runs()==[]


def test_preflight_reports_bad_labels_and_no_encoder_without_scores(configured,tmp_path,monkeypatch):
    docs,manager,store,example,_=setup(configured,tmp_path)
    seed=store.seeds[0].model_copy(deep=True)
    seed.evidence[0].quote='Missing evidence for a deliberate temporary fixture.'
    store.seeds=[seed]
    audit=development_audit(store,manager)
    assert audit['invalid_count']==1 and audit['results'][0]['status']=='invalid'
    assert 'metrics' not in audit and store.runs()==[]
    monkeypatch.setattr(manager,'status',lambda:{'state':'missing'})
    audit=development_audit(store,manager)
    assert audit['encoder_generation'] is None and audit['warning']


def test_reserved_questions_never_enter_packet_preflight_or_diagnostic(configured,tmp_path):
    docs,manager,store,_,runner=setup(configured,tmp_path)
    test_example=store.seeds[0].model_copy(update={'id':'reserved-question','group_id':'reserved-intent','split':'test',
        'question':'Reserved question must never be retrieved.','reference_answer':'Reserved reference.',
        'answerable':False,'evidence':[]})
    store.seeds.append(test_example)
    packet=review_packet(store)
    assert packet['reserved_test_count']==1 and 'Reserved reference' not in json.dumps(packet)
    audit=development_audit(store,manager)
    assert audit['reserved_test_count']==1 and len(audit['results'])==1
    run=runner.start(['bm25'],False)
    assert wait(store,run['id'])['status']=='complete'
    report=store.report(run['id'])
    assert len(report['results'])==1 and 'Reserved reference' not in json.dumps(report)


def test_preflight_rejects_library_changes(configured,tmp_path,monkeypatch):
    docs,manager,store,_,_=setup(configured,tmp_path)
    import app.evaluation.audit as module
    original=module.resolve_evidence
    def changing(*args,**kwargs):
        result=original(*args,**kwargs)
        docs.save(extract_document('new.txt',b'A new document invalidates this preflight.'))
        return result
    monkeypatch.setattr(module,'resolve_evidence',changing)
    with pytest.raises(IngestionError,match='changed during'): development_audit(store,manager)


def test_review_edits_cannot_introduce_reserved_question_or_evidence(configured,tmp_path):
    docs,_,store,example,_=setup(configured,tmp_path)
    docs.save(extract_document('other.txt',b'Reserved evidence used only in this synthetic test.'))
    reserved=example.model_copy(deep=True)
    reserved.id='reserved'; reserved.group_id='reserved'; reserved.split='test'
    reserved.question='A separate reserved question?'
    reserved.evidence[0].document='other.txt'; reserved.evidence[0].quote='Reserved evidence used only in this synthetic test.'
    store.seeds.append(reserved)
    changed=example.model_copy(update={'question':reserved.question})
    with pytest.raises(IngestionError,match='split boundary'): store.review(example.id,changed,0,False,'')
    changed=example.model_copy(update={'evidence':reserved.evidence})
    with pytest.raises(IngestionError,match='split boundary'): store.review(example.id,changed,0,False,'')
    assert store.dataset()['examples'][0]['revision']==0


def test_single_script_label_note_does_not_claim_invalidity_or_approval(configured,tmp_path):
    docs,manager,store,_,_=setup(configured,tmp_path)
    first=development_audit(store,manager)
    assert first['single_script_label_count']==1 and first['invalid_count']==0
    assert first['results'][0]['review_notes'] and store.dataset()['examples'][0]['review_status']=='unreviewed'
    docs.save(extract_document('arabic.txt','التوصيل خلال ثلاثة أيام عمل.'.encode('utf8')))
    store.seeds[0].evidence.append(EvidenceLabel(document='arabic.txt',quote='التوصيل خلال ثلاثة أيام عمل.',grade=1))
    second=development_audit(store,manager)
    assert second['single_script_label_count']==0 and second['invalid_count']==0
    assert second['results'][0]['review_notes']==[] and store.runs()==[]


def test_reserved_seed_changes_alter_pack_hash_without_exposing_contents(configured,tmp_path):
    _,_,store,example,_=setup(configured,tmp_path)
    reserved=example.model_copy(update={'id':'reserved','group_id':'reserved','split':'test',
        'question':'Hidden candidate?','reference_answer':'SECRET-REFERENCE-A','answerable':False,'evidence':[]})
    store.seeds.append(reserved)
    first=review_packet(store)
    reserved.reference_answer='SECRET-REFERENCE-B'
    second=review_packet(store)
    assert first['candidate_count']==second['candidate_count']==2
    assert first['candidate_pack_fingerprint']!=second['candidate_pack_fingerprint']
    assert first['examples']==second['examples'] and 'SECRET-REFERENCE' not in json.dumps([first,second])


def test_graded_draft_survives_restart_without_review_attestation(configured,tmp_path):
    docs,_,store,example,_=setup(configured,tmp_path)
    changed=example.model_copy(deep=True); changed.evidence[0].grade=3
    result=store.review(changed.id,changed,0,False,'')
    assert result['review_status']=='draft' and result['reviewed_at'] is None
    reopened=EvaluationStore(store.path,docs,store.reports,tmp_path/'fixture.json')
    assert reopened.dataset()['examples'][0]['example']['evidence'][0]['grade']==3
    assert reopened.dataset()['examples'][0]['review_status']=='draft'
