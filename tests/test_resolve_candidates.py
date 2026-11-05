"""resolve_teammates._candidates_to_try 단위 테스트 (API 호출 없음)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from resolve_teammates import _candidates_to_try  # noqa: E402


def _result(scores: dict) -> dict:
    ranked = sorted(scores, key=scores.get, reverse=True)
    return {"candidates": ranked, "candidate_scores": scores, "variants": {}}


def test_drops_low_score_partial_reads():
    # '静戒丨BS'의 일부만 읽은 '1BS'가 실존 유저와 일치했던 사례
    result = _result({"BR|BS": 76.3, "BR丨BS": 66.3, "EA|BS": 66.0, "戒|BS": 44.8, "1BS": 34.0})
    assert _candidates_to_try(result) == ["BR|BS", "BR丨BS", "EA|BS"]


def test_margin_from_best():
    result = _result({"Va발견": 98.9, "ya발견": 84.3, "Ya발견": 78.9, "발견": 60.3})
    assert _candidates_to_try(result) == ["Va발견", "ya발견", "Ya발견"]


def test_drops_single_character_noise():
    assert _candidates_to_try(_result({"1": 78.5})) == []


def test_legacy_result_without_scores():
    legacy = {"variants": {"kor+eng": "PuniPaw", "eng": "PuniPaw", "kor": ""}}
    assert _candidates_to_try(legacy) == ["PuniPaw"]
