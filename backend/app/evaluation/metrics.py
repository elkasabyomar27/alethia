"""Positive-label retrieval metrics. No relevant labels => undefined, not zero."""

import math
import statistics


def retrieval_metrics(ranking, relevance):
    if len(ranking) != len(set(ranking)):
        raise ValueError('Ranked chunk IDs must be unique.')
    if any(not isinstance(grade,int) or isinstance(grade,bool) or grade<0 or grade>3 for grade in relevance.values()):
        raise ValueError('Relevance grades must be integers from 0 through 3.')
    positives={identity:grade for identity,grade in relevance.items() if grade>0}
    if not positives: return None
    found=sum(identity in positives for identity in ranking[:5])
    reciprocal=next((1/rank for rank,identity in enumerate(ranking[:10],1) if identity in positives),0.0)
    dcg=sum((2**positives.get(identity,0)-1)/math.log2(rank+1) for rank,identity in enumerate(ranking[:5],1))
    ideal=sum((2**grade-1)/math.log2(rank+1) for rank,grade in enumerate(sorted(positives.values(),reverse=True)[:5],1))
    return {'recall_at_5':found/len(positives),'precision_at_5':found/5,
            'mrr_at_10':reciprocal,'ndcg_at_5':dcg/ideal}


def summarize(rows):
    scored=[row['metrics'] for row in rows if row['metrics'] is not None]
    times=sorted(row['latency_ms'] for row in rows)
    return {'query_count':len(rows),'scored_count':len(scored),
        'metrics':{key:statistics.mean(item[key] for item in scored) for key in scored[0]} if scored else None,
        'latency_median_ms':statistics.median(times) if times else None,
        'latency_p95_ms':times[max(0,math.ceil(.95*len(times))-1)] if times else None}
