"""Independent rank-arithmetic checks; no model or quality benchmark."""

from fractions import Fraction

import pytest

from app.rag.fusion import reciprocal_rank_fusion


def candidate(identity, score=1, parent="same-parent"):
    return {"id": identity, "parent_id": parent, "start": ord(identity[0]),
            "end": ord(identity[0]) + 5, "token_count": 3, "score": score}


def test_rank_fusion_matches_fraction_reference_and_retains_missing_provenance():
    lexical = [candidate("a", 800), candidate("b", .001), candidate("c", 0)]
    semantic = [candidate("c", .9), candidate("b", .8), candidate("d", -.1)]
    result = reciprocal_rank_fusion(lexical, semantic, 10)
    expected = {"a": Fraction(1, 61), "b": Fraction(2, 62),
                "c": Fraction(1, 63) + Fraction(1, 61), "d": Fraction(1, 63)}
    assert [row["id"] for row in result] == sorted(expected, key=lambda key: (-expected[key], key))
    for row in result:
        assert row["score"] == pytest.approx(float(expected[row["id"]]), abs=1e-15)
        assert row["score"] == sum(item["contribution"] for item in row["retrievers"].values() if item)
    by_id = {row["id"]: row for row in result}
    assert by_id["a"]["retrievers"] == {"bm25": {"rank": 1, "score": 800, "contribution": 1/61}, "dense": None}
    assert by_id["d"]["retrievers"]["bm25"] is None
    assert lexical[0]["score"] == 800 and "retrievers" not in lexical[0]


def test_raw_score_scale_does_not_affect_fusion_and_ties_use_chunk_id():
    first, second = [candidate("b"), candidate("a")], [candidate("a"), candidate("b")]
    original = reciprocal_rank_fusion(first, second, 10)
    first[0]["score"] = -999999
    second[1]["score"] = 999999
    scaled = reciprocal_rank_fusion(first, second, 10)
    assert [(row["id"], row["score"]) for row in scaled] == [(row["id"], row["score"]) for row in original]
    assert [row["id"] for row in original] == ["a", "b"]
    assert len(original) == 2  # Distinct chunks of one parent must not collapse.
    assert reciprocal_rank_fusion(first, second, 1) == scaled[:1]


@pytest.mark.parametrize("lexical,semantic", [([], []), ([candidate("a")], []), ([], [candidate("b")])])
def test_empty_rankings_contribute_zero(lexical, semantic):
    result = reciprocal_rank_fusion(lexical, semantic, 10)
    assert len(result) == len(lexical) + len(semantic)
    if result:
        assert result[0]["score"] == 1/61


def test_duplicate_or_conflicting_chunk_identity_is_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        reciprocal_rank_fusion([candidate("a"), candidate("a")], [], 10)
    conflicting = {**candidate("a"), "parent_id": "different-parent"}
    with pytest.raises(ValueError, match="provenance"):
        reciprocal_rank_fusion([candidate("a")], [conflicting], 10)
