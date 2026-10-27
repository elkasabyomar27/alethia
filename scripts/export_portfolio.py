"""Export an explicit allowlist of fictional material; never dump a local database.

Run manually with the local API running, after a reviewed pilot completes.
"""
import hashlib
import json
from pathlib import Path
import sys
import unicodedata
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8000'
EXAMPLES = [
    ('english', 'en', 'English · returns', 'cde930f34bbc44bdbab7503e9db84d5b'),
    ('arabic', 'ar_msa', 'العربية · إرجاع منتج مفتوح', '98d618d58a9d4b099b9b07e3597121f5'),
    ('egyptian', 'ar_egy', 'مصري · تأخر الأوردر', '0a5095124c714d31a316a3e7c31265dd'),
    ('unsupported', 'en', 'Unsupported · live stock', '10ed47660f8845a894a9799ffa929824'),
]


def get(route):
    return json.load(urlopen(BASE + route, timeout=20))


def normalized(text):
    return unicodedata.normalize('NFC', text.replace('\r\n', '\n').replace('\r', '\n'))


def export(run_id):
    documents = []
    source_map = {}
    demo = ROOT / 'data/demo/ecommerce'
    allowed = {p.name: normalized(p.read_text(encoding='utf-8-sig')) for p in demo.glob('*.md')}
    for metadata in get('/api/documents'):
        if metadata['filename'] not in allowed:
            continue
        item = get('/api/documents/' + metadata['id'])
        if item['text'] != allowed[item['filename']]:
            raise ValueError('Fictional source changed; inspect before exporting: ' + item['filename'])
        identity = Path(item['filename']).stem
        sections = []
        for i, section in enumerate(item['segments']):
            public_id = f'{identity}-section-{i+1}'
            source_map[section['id']] = public_id
            sections.append({'id': public_id, 'title': section['section'], 'text': section['text']})
        documents.append({'id': identity, 'filename': item['filename'], 'sections': sections})
    if len(documents) != 6:
        raise ValueError('Expected the original six fictional demo documents.')
    examples = []
    for identity, language, label, conversation in EXAMPLES:
        turn = get('/api/oracle/conversations/' + conversation)['turns'][0]
        evidence = {s['source_id']: s for s in turn['sources']}
        claims = []
        for claim in turn['claims']:
            citations = []
            for citation in claim['evidence']:
                source = evidence[citation['source_id']]
                if source['id'] not in source_map or source['citation_state'] != 'current' or citation['quote'] not in source['text']:
                    raise ValueError('Unverified or private citation in saved example.')
                citations.append({'sourceId': source_map[source['id']], 'quote': citation['quote']})
            claims.append({'text': claim['text'], 'evidence': citations})
        examples.append({'id': identity, 'language': language, 'label': label, 'question': turn['question'],
                         'status': turn['status'], 'claims': claims, 'model': turn['model'], 'savedAt': turn['created_at']})
    report = get('/api/evaluation/runs/' + run_id)
    if report['mode'] != 'reviewed-development' or not report['reviewed_only']:
        raise ValueError('A completed reviewed-development pilot is required.')
    rows = report['review_snapshot']
    pilot = {'runId': report['run_id'], 'completedAt': report['completed_at'],
             'corpusHash': report['encoder_snapshot']['corpus_hash'], 'datasetFingerprint': report['dataset_fingerprint'],
             'samples': len(rows), 'answerable': sum(r['example']['answerable'] for r in rows),
             'groups': len({r['example']['group_id'] for r in rows}),
             'languages': {lang: sum(r['example']['language'] == lang for r in rows) for lang in ('en', 'ar_msa', 'ar_egy')},
             'summary': report['summary'], 'limitations': report['limitations']}
    # Anonymize development failures; never publish benchmark question text or identities.
    pilot['failures'] = [{'question': f"Anonymized {r['language']} / {r['category']} reviewed case", 'method': r['method'], 'recall': r['metrics']['recall_at_5']}
                         for r in report['results'] if r['metrics'] and r['metrics']['recall_at_5'] < 1][:6]
    value = {'schema': 1, 'documents': documents, 'examples': examples, 'pilot': pilot}
    payload = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    path = ROOT / 'frontend/src/portfolio/demo.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding='utf-8')
    print(json.dumps({'export': str(path.relative_to(ROOT)), 'bytes': len(payload.encode()),
                      'sha256': hashlib.sha256(payload.encode()).hexdigest(), 'examples': len(examples)}))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python scripts/export_portfolio.py COMPLETED_REVIEWED_RUN_ID')
    export(sys.argv[1])
