from fastapi.testclient import TestClient
from app.main import create_app
from app.evaluation.dataset import RESERVED_PATH


def test_evaluation_api_is_honest_before_review_and_rejects_unsupported_runs(tmp_path):
    with TestClient(create_app(tmp_path/'documents.sqlite3')) as client:
        private_count=30 if RESERVED_PATH.exists() else 0
        dataset=client.get('/api/evaluation/dataset').json()
        assert len(dataset['examples'])==120 and dataset['heldout_count']==private_count
        assert dataset['candidate_count']==120+private_count and len(dataset['candidate_pack_fingerprint'])==64
        assert all(row['review_status']=='unreviewed' for row in dataset['examples'])
        assert client.get('/api/evaluation/runs').json()==[]
        assert client.post('/api/evaluation/runs',json={'methods':['bm25'],'reviewed_only':True}).status_code==409
        assert client.post('/api/evaluation/runs',json={'methods':['rerank']}).status_code==422
        assert client.post('/api/evaluation/runs',json={'methods':['bm25'],'split':'test'}).status_code==422
        assert client.get('/api/evaluation/runs/'+'a'*32).status_code==404
        example=dataset['examples'][0]['example']
        assert client.post('/api/evaluation/reviews/'+example['id'],json={'example':example,'expected_revision':0,'approve':True,'reviewer':''}).status_code==422
        packet=client.get('/api/evaluation/review-packet')
        assert 'attachment;' in packet.headers['content-disposition']
        assert len(packet.json()['examples'])==120
        assert all(row['example']['split']=='dev' for row in packet.json()['examples'])
        audit=client.get('/api/evaluation/preflight')
        assert audit.status_code==200 and audit.json()['reserved_test_count']==private_count
        assert {row['example_id'] for row in audit.json()['results']}=={row['example']['id'] for row in dataset['examples']}
