"""resolve_teammates.candidates_to_try 단위 테스트 (API 호출 없음)."""

from lumi.api.resolve import candidates_to_try, lookalike_candidates
from lumi.ocr.candidates import lookalike_variants


def _result(scores: dict) -> dict:
    ranked = sorted(scores, key=scores.get, reverse=True)
    return {"candidates": ranked, "candidate_scores": scores}


def test_drops_low_score_partial_reads():
    # '静戒丨BS'의 일부만 읽은 '1BS'가 실존 유저와 일치했던 사례
    result = _result({"BR|BS": 76.3, "BR丨BS": 66.3, "EA|BS": 66.0, "戒|BS": 44.8, "1BS": 34.0})
    assert candidates_to_try(result) == ["BR|BS", "BR丨BS", "EA|BS"]


def test_margin_from_best():
    result = _result({"Va발견": 98.9, "ya발견": 84.3, "Ya발견": 78.9, "발견": 60.3})
    assert candidates_to_try(result) == ["Va발견", "ya발견", "Ya발견"]


def test_drops_single_character_noise():
    assert candidates_to_try(_result({"1": 78.5})) == []


def test_lookalike_variants():
    assert lookalike_variants("滕田皮卡丘")[0] == "藤田皮卡丘"
    assert "静戒丨BS" in lookalike_variants("靜戒|BS")
    assert lookalike_variants("PuniPaw") == []


def test_lookalike_candidates_limits():
    # 짧은 후보(2글자 이하)는 변형하지 않음 - 다른 유저와 우연히 일치할 위험
    assert lookalike_candidates(["滕田"]) == []
    out = lookalike_candidates(["滕田皮卡丘", "靜戒|BS"])
    assert out[0] == "藤田皮卡丘"
    assert len(out) <= 6
    assert "滕田皮卡丘" not in out  # 이미 시도한 후보는 제외
