"""Rank-only fusion over identical chunk identities; no ML dependencies.

Formula: Cormack, Clarke & Buettcher, SIGIR 2009,
https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf
These defaults are configuration choices, not tuned ALETHIA quality results.
"""

RRF_RANK_CONSTANT = 60
RRF_CANDIDATE_DEPTH = 20
RRF_VERSION = "equal-rrf-60-depth20-v1"


def reciprocal_rank_fusion(bm25: list[dict], dense: list[dict], top_k: int) -> list[dict]:
    """Fuse one-based candidate ranks. Missing candidates contribute zero.

    Each input must contain unique chunk IDs in rank order. Raw scores are
    retained for inspection but never mixed into the fused score. Chunk ID
    breaks exact ties; distinct chunks of one parent remain distinct.
    """
    candidates = {}
    for name, ranking in (("bm25", bm25), ("dense", dense)):
        seen = set()
        for rank, match in enumerate(ranking, 1):
            identity = match["id"]
            if identity in seen:
                raise ValueError("A retriever returned duplicate chunk identities.")
            seen.add(identity)
            if identity not in candidates:
                candidates[identity] = {**match, "score": 0.0, "retrievers": {"bm25": None, "dense": None}}
            row = candidates[identity]
            if any(row[key] != match[key] for key in ("parent_id", "start", "end", "token_count")):
                raise ValueError("Retriever chunk provenance does not agree.")
            contribution = 1.0 / (RRF_RANK_CONSTANT + rank)
            row["score"] += contribution
            row["retrievers"][name] = {"rank": rank, "score": match["score"], "contribution": contribution}
    return sorted(candidates.values(), key=lambda row: (-row["score"], row["id"]))[:top_k]
