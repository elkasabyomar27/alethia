"""Structural development preflight and review packet. Never approves labels."""

from collections import Counter
import re
from app.evaluation.dataset import Example,corpus_fingerprint,fingerprint,resolve_evidence,read_encoder_corpus
from app.evaluation.store import now
from app.ingestion import IngestionError


def development_audit(store,dense):
    dataset=store.dataset()
    rows=dataset['examples']; chunks=None; generation=None; warning=None
    if dense.status()['state']=='ready':
        folder,_,chunks=read_encoder_corpus(dense)
        generation=folder.name
    else:
        warning='No current encoder snapshot: only document/source labels were checked.'
    results=[]
    for row in rows:
        example=Example.model_validate(row['example'])
        scripts={bool(re.search(r'[\u0600-\u06ff]',label.quote)) for label in example.evidence}
        notes=['Evidence labels cover one script only. Check for equivalent relevant English/Arabic passages; cross-language retrieval itself is valid.'] if example.answerable and len(scripts)==1 else []
        try:
            evidence,relevance=resolve_evidence(example,store.documents,chunks)
            results.append({'example_id':example.id,'status':'resolved' if example.answerable else 'no_positive_labels',
                'label_count':len(evidence),'positive_chunk_count':len(relevance) if chunks is not None else None,'error':None,'review_notes':notes})
        except IngestionError as error:
            results.append({'example_id':example.id,'status':'invalid','label_count':len(example.evidence),
                'positive_chunk_count':None,'error':str(error),'review_notes':notes})
    if corpus_fingerprint(store.documents)!=dataset['corpus_fingerprint']:
        raise IngestionError('Library changed during preflight. Retry against one corpus.',409)
    if generation:
        with dense._artifacts:
            active=dense._active()
            if active is None or active[0].name!=generation:
                raise IngestionError('Encoder changed during preflight. Retry.',409)
    return {'dataset_id':dataset['dataset_id'],'development_fingerprint':fingerprint(rows),
        'candidate_count':dataset['candidate_count'],'candidate_pack_fingerprint':dataset['candidate_pack_fingerprint'],
        'corpus_fingerprint':dataset['corpus_fingerprint'],'encoder_generation':generation,'checked_at':now(),
        'development_count':len(rows),'reserved_test_count':dataset['heldout_count'],
        'groups':len({row['example']['group_id'] for row in rows}),
        'languages':dict(Counter(row['example']['language'] for row in rows)),
        'categories':dict(Counter(row['example']['category'] for row in rows)),
        'reviews':dict(Counter(row['review_status'] for row in rows)),
        'invalid_count':sum(row['status']=='invalid' for row in results),
        'single_script_label_count':sum(bool(row['review_notes']) for row in results),'results':results,'warning':warning,
        'limitations':['Structural checks do not review reference correctness, answerability, or completeness of relevance labels.',
            'Reserved test contents are excluded. This is a candidate split, not a frozen human-reviewed benchmark.',
            'Group, normalized-question, and labelled-quote checks cannot detect all semantic leakage.']}


def review_packet(store):
    dataset=store.dataset()
    return {'schema':1,'kind':'unscored-development-review-packet','exported_at':now(),
        'candidate_count':dataset['candidate_count'],'candidate_pack_fingerprint':dataset['candidate_pack_fingerprint'],
        'dataset_id':dataset['dataset_id'],'development_fingerprint':fingerprint(dataset['examples']),
        'corpus_fingerprint':dataset['corpus_fingerprint'],'reserved_test_count':dataset['heldout_count'],
        'instructions':['Use the application to inspect current evidence and record your own review.',
            'This export does not approve any example. Offline edits are not imported automatically.',
            'Review every relevant passage, reference claim and answerability label, not merely quote existence.',
            'Keep private when using private documents. Reserved test examples are not included.'],
        'examples':dataset['examples']}
