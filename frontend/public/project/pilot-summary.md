# Provisional reviewed-development retrieval pilot

Run: c7b2ad2ed2ef4c4b88eb3135d3d32d55

18 reviewed questions / 10 intent groups: 8 English, 5 Modern Standard Arabic, 5 Egyptian Arabic. 15 answerable cases scored per method; 3 unanswerable cases contribute latency only. These counts are frozen for this run and do not describe subsequent review progress.

| Method | Recall@5 | Precision@5 | MRR@10 | nDCG@5 | Median ms | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| bm25 | 0.7333 | 0.1600 | 0.6111 | 0.6147 | 8.50 | 15.20 |
| dense | 0.7333 | 0.1600 | 0.7157 | 0.7087 | 2306.11 | 3073.02 |
| hybrid | 0.7333 | 0.1600 | 0.7037 | 0.6807 | 2353.58 | 3245.08 |

## Interpretation

Recall@5 was equal across methods in this selected subset. Dense had higher MRR and nDCG in this run, but this small correlated sample does not establish a general improvement. Precision@5 divides by five even where only a few passages are labelled relevant. Missing positive labels can make correctly related passages appear nonrelevant.

Dense and hybrid latency includes cold worker startup, integrity checks, and local machine activity. The unchanged 1 GiB admission guard was used; no model stayed loaded between operations.

## Language breakdowns

- bm25 / en: 8 queries, 7 scored; Recall@5 0.7143; median 8.41 ms.
- bm25 / ar_msa: 5 queries, 4 scored; Recall@5 0.7500; median 8.54 ms.
- bm25 / ar_egy: 5 queries, 4 scored; Recall@5 0.7500; median 8.94 ms.
- dense / en: 8 queries, 7 scored; Recall@5 0.7143; median 2323.29 ms.
- dense / ar_msa: 5 queries, 4 scored; Recall@5 0.7500; median 2307.96 ms.
- dense / ar_egy: 5 queries, 4 scored; Recall@5 0.7500; median 2253.36 ms.
- hybrid / en: 8 queries, 7 scored; Recall@5 0.7143; median 2333.08 ms.
- hybrid / ar_msa: 5 queries, 4 scored; Recall@5 0.7500; median 2279.97 ms.
- hybrid / ar_egy: 5 queries, 4 scored; Recall@5 0.7500; median 2411.17 ms.

## Failure analysis

- bm25: 4 of 15 scored cases had incomplete Recall@5; 4 had zero Recall@5.
  - Anonymized ar_msa / paraphrase case: Recall@5 0.0000, MRR@10 0.0000. Inspect the private full report for rankings; benchmark question text is omitted here.
  - Anonymized ar_egy / paraphrase case: Recall@5 0.0000, MRR@10 0.0000. Inspect the private full report for rankings; benchmark question text is omitted here.
- dense: 4 of 15 scored cases had incomplete Recall@5; 4 had zero Recall@5.
  - Anonymized ar_msa / paraphrase case: Recall@5 0.0000, MRR@10 0.1250. Inspect the private full report for rankings; benchmark question text is omitted here.
  - Anonymized ar_egy / paraphrase case: Recall@5 0.0000, MRR@10 0.1111. Inspect the private full report for rankings; benchmark question text is omitted here.
- hybrid: 4 of 15 scored cases had incomplete Recall@5; 4 had zero Recall@5.
  - Anonymized ar_msa / paraphrase case: Recall@5 0.0000, MRR@10 0.1111. Inspect the private full report for rankings; benchmark question text is omitted here.
  - Anonymized ar_egy / paraphrase case: Recall@5 0.0000, MRR@10 0.1111. Inspect the private full report for rankings; benchmark question text is omitted here.

## Reproducibility

Corpus: `2cb1edc2e8ad1e3ee4b3c2b84875a794924676d34a5ccea056524b82a17b67b5`

Dataset snapshot: `fd21f403c053c08fbcb14b039e783f545066a7f2e384506bf76dbd21fe13a6bd`

Frozen snapshot SHA-256: `80c3fa7a89453bc95d165809527d415aa80f6ed35218cba4e0c1318ff6434a73`

Same 29 encoder chunks, model revision and normalized vectors for all methods. E5-small INT8 CPU, 384 dimensions; up to 20 candidates per component and RRF constant 60. Retrieved top 10; recall/precision/nDCG measured at 5. Raw review identities and question-level snapshots remain local.

## Limitations

- Development set; no held-out test run or quality guarantee.
- Review status is a recorded personal attestation, not proof of human identity.
- Unlabelled chunks are treated as nonrelevant; incomplete positive labels bias metrics.
- Single pass with no confidence intervals; sample counts and language breakdowns must accompany numbers.
- Latency includes integrity checks and cold embedding startup; other machine activity can affect results.
- Unanswerable questions are excluded from retrieval-quality metrics; retrieval is not an abstention test.
- No generation, LLM judge, reranker, or human-handoff quality evaluation was run.
