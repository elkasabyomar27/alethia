"""Sequential retrieval experiments. No LLM calls or automatic review approval."""

import json
import platform
import sqlite3
import threading
import time
from uuid import uuid4

from app.ingestion import IngestionError
from app.evaluation.dataset import Example,fingerprint,corpus_fingerprint,resolve_evidence,read_encoder_corpus
from app.evaluation.metrics import retrieval_metrics,summarize
from app.evaluation.store import now
from app.rag.analyzer import tokenize


class EvaluationRunner:
    def __init__(self,store,dense):
        self.store=store; self.dense=dense; self.guard=threading.Lock(); self.closed=False

    def start(self,methods,reviewed_only):
        if self.closed: raise IngestionError('Evaluation is shutting down.',503)
        if not methods or len(methods)!=len(set(methods)) or any(method not in ('bm25','dense','hybrid') for method in methods):
            raise IngestionError('Choose unique supported retrieval methods.',422)
        if not self.guard.acquire(blocking=False): raise IngestionError('An evaluation is already running.',409)
        try:
            dataset=self.store.dataset()
            rows=[row for row in dataset['examples'] if not reviewed_only or row['review_status']=='reviewed']
            if not rows: raise IngestionError('No currently reviewed development examples are available. Use diagnostic mode or complete personal review.',409)
            if self.dense.status()['state']!='ready': raise IngestionError('Build a current encoder index before evaluation.',409)
            identity=uuid4().hex
            with self.store.connect() as connection:
                connection.execute('BEGIN IMMEDIATE')
                if connection.execute('SELECT count(*) FROM runs').fetchone()[0]>=50:
                    raise IngestionError('The local 50-run limit was reached. Preserve/export existing reports before changing this limit.',409)
                connection.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?)',(identity,'running',now(),0,len(rows)*len(methods),None,None))
            thread=threading.Thread(target=self.execute,args=(identity,dataset,rows,methods,reviewed_only),daemon=True,name='retrieval-evaluation')
            thread.start()
            return self.store.run(identity)
        except Exception:
            self.guard.release(); raise

    def execute(self,identity,dataset,rows,methods,reviewed_only):
        try:
            folder,manifest,chunks=read_encoder_corpus(self.dense)
            if corpus_fingerprint(self.store.documents)!=dataset['corpus_fingerprint']:
                raise IngestionError('Library changed before evaluation.',409)
            results=[]; configs={}; count=0
            for review in rows:
                example=Example.model_validate(review['example'])
                resolved,relevance=resolve_evidence(example,self.store.documents,chunks)
                terms=list(dict.fromkeys(tokenize(example.question)))
                if not terms or len(terms)>64: raise IngestionError('An evaluation question violates retrieval term limits.',422)
                for method in methods:
                    if self.closed: raise IngestionError('Evaluation cancelled during shutdown.',503)
                    started=time.perf_counter()
                    index,hits,diagnostics=self.dense.search(example.question,terms,10,method)
                    latency=(time.perf_counter()-started)*1000
                    with self.dense._artifacts:
                        current=self.dense._active()
                        if current is None or current[0].name!=folder.name:
                            raise IngestionError('Encoder generation was rebuilt during evaluation.',409)
                    if index['corpus_hash']!=manifest['corpus_hash'] or index['index_revision']!=manifest['source_revision']:
                        raise IngestionError('Encoder corpus changed during evaluation.',409)
                    configs[method]={**index,'fusion':{key:value for key,value in index['fusion'].items() if key!='candidate_counts'} if index.get('fusion') else None}
                    metric=retrieval_metrics([hit['chunk_id'] for hit in hits],relevance) if review['review_status']=='reviewed' and example.answerable else None
                    results.append({'example_id':example.id,'language':example.language,'category':example.category,
                        'answerable':example.answerable,'review_status':review['review_status'],'method':method,
                        'question':example.question,'reference_answer':example.reference_answer,'evidence':resolved,
                        'relevance':relevance,'metrics':metric,'latency_ms':latency,'worker_diagnostics':diagnostics,
                        'fusion_candidate_counts':index.get('fusion',{}).get('candidate_counts') if index.get('fusion') else None,
                        'hits':[{'chunk_id':hit['chunk_id'],'source_id':hit['id'],'document_id':hit['document_id'],
                            'filename':hit['filename'],'section':hit['section'],'revision':hit['revision'],
                            'start_char':hit['start_char'],'end_char':hit['end_char'],'score':hit['score'],
                            'excerpt':hit['text'][:240]} for hit in hits]})
                    count+=1
                    with self.store.connect() as connection: connection.execute('UPDATE runs SET completed=? WHERE id=?',(count,identity))
            state,fingerprint_now=self.dense._source_state()
            with self.dense._artifacts:
                current=self.dense._active()
                if current is None or current[0].name!=folder.name:
                    raise IngestionError('Encoder generation changed before report publication.',409)
            if (state['index_revision']!=manifest['source_revision'] or fingerprint_now!=manifest['source_fingerprint']
                    or corpus_fingerprint(self.store.documents)!=dataset['corpus_fingerprint']):
                raise IngestionError('Library changed during evaluation. No completed report was published.',409)
            summary={method:{**summarize([row for row in results if row['method']==method]),
                'languages':{language:summarize([row for row in results if row['method']==method and row['language']==language])
                    for language in ('en','ar_msa','ar_egy')}} for method in methods}
            report={'schema':1,'run_id':identity,'created_at':self.store.run(identity)['created_at'],'completed_at':now(),
                'dataset_id':dataset['dataset_id'],'dataset_fingerprint':fingerprint(rows),
                'candidate_pack_fingerprint':dataset['candidate_pack_fingerprint'],
                'review_snapshot':rows,'split':'dev','reviewed_only':reviewed_only,
                'mode':'reviewed-development' if reviewed_only else 'development-diagnostic',
                'corpus_fingerprint':dataset['corpus_fingerprint'],'encoder_generation':folder.name,'encoder_snapshot':manifest,'methods':methods,
                'configurations':configs,'metric_version':'positive-qrels-v1','metric_definition':
                'Positive chunks contain complete labelled quotes. P@5 denominator is always 5. Empty relevance is unscored. nDCG uses exponential graded gain. Macro means use reviewed answerable cases only.',
                'environment':{'python':platform.python_version(),'os':platform.system(),'machine':platform.machine(),'sqlite':sqlite3.sqlite_version},
                'limitations':['Development set; no held-out test run or quality guarantee.','Review status is a recorded personal attestation, not proof of human identity.',
                    'Unlabelled chunks are treated as nonrelevant; incomplete positive labels bias metrics.',
                    'Single pass with no confidence intervals; sample counts and language breakdowns must accompany numbers.',
                    'Latency includes integrity checks and cold embedding startup; other machine activity can affect results.',
                    'Unanswerable questions are excluded from retrieval-quality metrics; retrieval is not an abstention test.',
                    'No generation, LLM judge, reranker, or human-handoff quality evaluation was run.'],
                'summary':summary,'results':results}
            payload=json.dumps(report,ensure_ascii=False,indent=2)
            if len(payload.encode())>16*1024**2: raise IngestionError('Report exceeds 16 MiB.',413)
            path=self.store.report_path(identity)
            if path.exists(): raise IngestionError('Report already exists; refusing to overwrite.',409)
            temporary=path.with_suffix('.json.part'); temporary.write_text(payload,encoding='utf8'); temporary.replace(path)
            with self.store.connect() as connection: connection.execute("UPDATE runs SET status='complete',summary_json=? WHERE id=?",(json.dumps(summary),identity))
        except Exception as error:
            message=str(error) if isinstance(error,IngestionError) else 'Evaluation failed. Check source labels, index integrity, and runtime resources.'
            with self.store.connect() as connection: connection.execute("UPDATE runs SET status='failed',error=? WHERE id=?",(message,identity))
        finally:
            self.guard.release()

    def close(self): self.closed=True


def markdown_report(report):
    lines=['# ALETHIA retrieval evaluation','',f"Run: {report['run_id']}",f"Mode: {report['mode']} · split: dev",
        f"Dataset: {report['dataset_fingerprint']}",f"Chunk corpus: {report['encoder_snapshot']['corpus_hash']}",
        '', '| Method | Queries | Scored | Recall@5 | Precision@5 | MRR@10 | nDCG@5 | Median ms | p95 ms |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for method,value in report['summary'].items():
        metrics=value['metrics'] or {}
        numbers=[f"{metrics[key]:.6f}" if key in metrics else 'Not scored' for key in ('recall_at_5','precision_at_5','mrr_at_10','ndcg_at_5')]
        lines.append(f"| {method} | {value['query_count']} | {value['scored_count']} | "+' | '.join(numbers)+f" | {value['latency_median_ms']:.3f} | {value['latency_p95_ms']:.3f} |")
    lines+=['','## Limitations','']+[f'- {item}' for item in report['limitations']]
    lines+=['','The JSON export contains per-question rankings, language breakdowns, labels, review snapshots, and configuration details.']
    return '\n'.join(lines)
