"""Public-data boundary contracts, without network, models, or local databases."""
import json
from pathlib import Path
import unicodedata

ROOT = Path(__file__).resolve().parents[2]


def data():
    return json.loads((ROOT/'frontend/src/portfolio/demo.json').read_text(encoding='utf-8'))


def test_only_original_fictional_documents_are_published():
    demo = data()
    files = {p.name:p for p in (ROOT/'data/demo/ecommerce').glob('*.md')}
    assert len(demo['documents']) == 6
    assert {d['filename'] for d in demo['documents']} == set(files)
    for document in demo['documents']:
        assert set(document) == {'id','filename','sections'}
        original = unicodedata.normalize('NFC',files[document['filename']].read_text(encoding='utf-8-sig'))
        for section in document['sections']:
            assert set(section) == {'id','title','text'}
            assert section['text'] in original


def test_four_saved_examples_have_resolvable_exact_quotes():
    demo = data()
    assert {e['id'] for e in demo['examples']} == {'english','arabic','egyptian','unsupported'}
    assert {e['language'] for e in demo['examples']} == {'en','ar_msa','ar_egy'}
    sections = {s['id']:s for d in demo['documents'] for s in d['sections']}
    for example in demo['examples']:
        assert set(example) == {'id','language','label','question','status','claims','model','savedAt'}
        for claim in example['claims']:
            assert set(claim) == {'text','evidence'}
            assert claim['evidence']
            for citation in claim['evidence']:
                assert set(citation) == {'sourceId','quote'}
                assert citation['quote'] in sections[citation['sourceId']]['text']
    unsupported = next(e for e in demo['examples'] if e['id']=='unsupported')
    assert unsupported['status'] == 'needs_human' and unsupported['claims'] == []


def test_public_pilot_contains_aggregates_not_review_snapshots():
    pilot = data()['pilot']
    assert set(pilot) == {'runId','completedAt','corpusHash','datasetFingerprint','samples','answerable','groups','languages','summary','limitations','failures'}
    assert sum(pilot['languages'].values()) == pilot['samples']
    assert 0 < pilot['answerable'] <= pilot['samples']
    assert set(pilot['summary']) == {'bm25','dense','hybrid'}
    for result in pilot['summary'].values():
        assert result['query_count'] == pilot['samples']
        assert result['scored_count'] == pilot['answerable']
        assert all(0 <= value <= 1 for value in result['metrics'].values())
    assert pilot['limitations']
