"""Independent mathematical fixtures, never ALETHIA quality results."""

import math
import pytest
from app.evaluation.metrics import retrieval_metrics,summarize


def test_cutoffs_and_graded_ndcg_match_explicit_reference():
    result=retrieval_metrics(['x','b','a'],{'a':2,'b':1,'c':1})
    assert result['recall_at_5']==pytest.approx(2/3)
    assert result['precision_at_5']==pytest.approx(2/5)
    assert result['mrr_at_10']==.5
    expected=(1/math.log2(3)+3/math.log2(4))/(3+1/math.log2(3)+1/math.log2(4))
    assert result['ndcg_at_5']==pytest.approx(expected)


def test_short_rankings_do_not_inflate_precision_and_empty_labels_are_undefined():
    assert retrieval_metrics(['a'],{'a':1})['precision_at_5']==.2
    assert retrieval_metrics(['a'],{}) is None
    assert retrieval_metrics(['a'],{'a':0}) is None
    assert retrieval_metrics([],{'a':1})=={'recall_at_5':0,'precision_at_5':0,'mrr_at_10':0,'ndcg_at_5':0}


def test_rank_ten_is_included_but_rank_eleven_is_not():
    ranking=[str(i) for i in range(1,12)]
    assert retrieval_metrics(ranking,{'10':1})['mrr_at_10']==.1
    assert retrieval_metrics(ranking,{'11':1})['mrr_at_10']==0
    assert retrieval_metrics(ranking,{'6':1})['recall_at_5']==0


def test_invalid_duplicate_ids_or_grades_fail_instead_of_double_counting():
    with pytest.raises(ValueError): retrieval_metrics(['a','a'],{'a':1})
    for grade in (-1,4,True,1.5):
        with pytest.raises(ValueError): retrieval_metrics(['a'],{'a':grade})


def test_macro_means_exclude_unscored_cases_and_p95_is_nearest_rank():
    one=retrieval_metrics(['a'],{'a':1})
    zero=retrieval_metrics([],{'a':1})
    rows=[{'latency_ms':i,'metrics':one if i==1 else zero if i==2 else None} for i in range(1,21)]
    result=summarize(rows)
    assert result['scored_count']==2 and result['query_count']==20
    assert result['metrics']['recall_at_5']==.5
    assert result['latency_median_ms']==10.5 and result['latency_p95_ms']==19
    assert summarize([])['metrics'] is None and summarize([])['latency_p95_ms'] is None
