"""Review attestations and immutable report files; no fabricated approval/results."""

from contextlib import contextmanager
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import sqlite3

from app.ingestion import IngestionError
from app.evaluation.dataset import Example,load_dataset,fingerprint,corpus_fingerprint,resolve_evidence,validate_separation


def now(): return datetime.now(timezone.utc).isoformat()


class EvaluationStore:
    def __init__(self,path,documents,reports,dataset_path=None):
        self.path=Path(path); self.documents=documents; self.reports=Path(reports)
        self.dataset_id,self.seeds=load_dataset(dataset_path) if dataset_path else load_dataset()
        self.path.parent.mkdir(parents=True,exist_ok=True); self.reports.mkdir(parents=True,exist_ok=True)
        with self.connect() as connection:
            if connection.execute('PRAGMA user_version').fetchone()[0]>1: raise RuntimeError('Evaluation needs a newer app.')
            connection.execute('''CREATE TABLE IF NOT EXISTS reviews (example_id TEXT PRIMARY KEY,
                seed_hash TEXT NOT NULL,example_json TEXT NOT NULL,revision INTEGER NOT NULL,
                reviewer TEXT NOT NULL,reviewed_at TEXT,corpus_hash TEXT NOT NULL)''')
            connection.execute('''CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY,status TEXT NOT NULL,
                created_at TEXT NOT NULL,completed INTEGER NOT NULL,total INTEGER NOT NULL,
                summary_json TEXT,error TEXT)''')
            connection.execute("UPDATE runs SET status='interrupted',error='API restarted before run completion.' WHERE status='running'")
            connection.execute('PRAGMA user_version=1')

    @contextmanager
    def connect(self):
        connection=sqlite3.connect(self.path,timeout=10); connection.row_factory=sqlite3.Row
        try:
            with connection: yield connection
        finally: connection.close()

    def dataset(self):
        corpus=corpus_fingerprint(self.documents)
        with self.connect() as connection: reviews={row['example_id']:dict(row) for row in connection.execute('SELECT * FROM reviews')}
        result=[]
        for seed in self.seeds:
            if seed.split!='dev': continue  # Held-out contents are never exposed by this foundation UI.
            review=reviews.get(seed.id); current=bool(review and review['seed_hash']==fingerprint(seed.model_dump()))
            example=Example.model_validate_json(review['example_json']) if current else seed
            status='unreviewed'
            if current: status='reviewed' if review['reviewed_at'] and review['corpus_hash']==corpus else 'stale' if review['reviewed_at'] else 'draft'
            result.append({'example':example.model_dump(),'revision':review['revision'] if review else 0,
                'review_status':status,'reviewer':review['reviewer'] if current else '',
                'reviewed_at':review['reviewed_at'] if current else None})
        return {'dataset_id':self.dataset_id,'examples':result,'corpus_fingerprint':corpus,
            'candidate_count':len(self.seeds),'candidate_pack_fingerprint':fingerprint([seed.model_dump() for seed in self.seeds]),
            'heldout_count':sum(seed.split=='test' for seed in self.seeds),'target_reviewed_questions':150}

    def review(self,identity,example,revision,approve,reviewer):
        seed=next((item for item in self.seeds if item.id==identity and item.split=='dev'),None)
        if not seed: raise IngestionError('Development example not found.',404)
        if example.id!=identity or example.group_id!=seed.group_id or example.split!='dev':
            raise IngestionError('Example identity, group, and split cannot be changed in review.',422)
        reviewer=reviewer.strip()
        if approve and len(reviewer)<2: raise IngestionError('A reviewer name is required for a personal review attestation.',422)
        corpus=corpus_fingerprint(self.documents)
        resolve_evidence(example,self.documents)
        if corpus_fingerprint(self.documents)!=corpus: raise IngestionError('Library changed during review. Reload and check the evidence again.',409)
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            current=connection.execute('SELECT revision FROM reviews WHERE example_id=?',(identity,)).fetchone()
            if revision!=(current['revision'] if current else 0): raise IngestionError('Review changed in another tab. Reload before saving.',409)
            candidates=[example if row['example']['id']==identity else Example.model_validate(row['example'])
                for row in self.dataset()['examples']]+[seed for seed in self.seeds if seed.split=='test']
            try: validate_separation(candidates)
            except ValueError:
                raise IngestionError('This edit conflicts with another candidate or split boundary. Use a distinct question and development evidence.',409) from None
            connection.execute('INSERT OR REPLACE INTO reviews VALUES (?,?,?,?,?,?,?)',
                (identity,fingerprint(seed.model_dump()),example.model_dump_json(),revision+1,reviewer,now() if approve else None,corpus))
        return next(row for row in self.dataset()['examples'] if row['example']['id']==identity)

    def run(self,identity):
        with self.connect() as connection: row=connection.execute('SELECT * FROM runs WHERE id=?',(identity,)).fetchone()
        if row is None: raise IngestionError('Evaluation run not found.',404)
        result=dict(row); summary=result.pop('summary_json'); result['summary']=json.loads(summary) if summary else None
        return result

    def runs(self):
        with self.connect() as connection: identities=[row['id'] for row in connection.execute('SELECT id FROM runs ORDER BY created_at DESC,id LIMIT 50')]
        return [self.run(identity) for identity in identities]

    def report_path(self,identity):
        if not re.fullmatch(r'[a-f0-9]{32}',identity): raise IngestionError('Invalid report identifier.',404)
        path=self.reports/f'{identity}.json'
        if path.is_symlink() or path.resolve().parent!=self.reports.resolve(): raise IngestionError('Invalid report path.',404)
        return path

    def report(self,identity):
        if self.run(identity)['status']!='complete': raise IngestionError('The run has no completed report.',409)
        path=self.report_path(identity)
        if not path.is_file() or path.stat().st_size>16*1024**2: raise IngestionError('Evaluation report is missing or exceeds its size limit.',409)
        return json.loads(path.read_text(encoding='utf8'))
