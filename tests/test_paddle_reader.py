"""PP-OCR 리더 (lumi.ocr.paddle).

- 결과 고르기(combine): 모델 없이 가짜 결과로
- 실제 화면: 저장된 게임 화면으로 닉네임 인식 정확도를 확인하는 회귀 테스트.
  rapidocr가 설치돼 있을 때만 (처음엔 모델 다운로드).
  새 스크린샷을 tests/fixtures/에 넣으면 EXPECTED에 정답도 적어 두세요.

정확도 요약 출력: python tests/test_paddle_reader.py
"""

import pytest
from PIL import Image

from conftest import fixture, name_crops
from lumi.api.resolve import candidates_to_try, lookalike_candidates
from lumi.game.match_flow import slot_ready
from lumi.ocr import paddle

EXPECTED = {
    "matching_lobby_screen.png": ["PuniPaw", "sooin", "ya발견"],
    "normal_matched_lobby.png": ["PuniPaw", "BlackBrave", "HYUHAN"],
    "test2.png": ["PuniPaw", "MirNight", "アンベリィ"],
    "test3.png": ["PuniPaw", "로즈만때리는루크", "마브하라"],
    "test4.png": ["PuniPaw", "静戒丨BS", "레몬데몬"],
    # 16:10 실게임 화면 (2880x1800을 2000x1250으로 축소한 것)
    "lobby_16x10.webp": ["PuniPaw", "12345a", "얼음마녀"],
    "lobby_16x10_chinese.webp": ["PuniPaw", "藤田皮卡丘", "불법체류자엠마"],
    "lobby_16x10_portrait.webp": ["PuniPaw", "라비에오", "124qer123"],
}

# 1순위는 아니어도 API 조회 후보(+ 비슷한 글자 변형) 안에 정답이 있으면 통과
API_RESOLVED = {
    ("test4.png", 1),  # '丨'을 'I'로 읽음 -> 보조 후보 '静戒丨BS'
}


def api_tried(result: dict) -> list[str]:
    tried = candidates_to_try(result)
    return tried + lookalike_candidates(tried)


# ---- 결과 고르기 ----


def test_trusts_korean_model_for_hangul():
    # ch 모델이 한글을 빼고 영문만 더 높은 점수로 읽어도 korean 결과를 씀
    r = paddle.combine(("ya발견", 0.867), ("ya", 0.911))
    assert r["best"] == "ya발견"
    # 다른 모델 결과는 API 조회 범위(1등 - 25점) 밖
    assert r["candidate_scores"]["ya"] < r["candidate_scores"]["ya발견"] - 25


def test_trusts_ch_model_for_kanji_and_kana():
    assert paddle.combine(("", 0.0), ("藤田皮卡丘", 0.955))["best"] == "藤田皮卡丘"
    assert paddle.combine(("PYAT", 0.45), ("アンベリィ", 0.987))["best"] == "アンベリィ"


def test_latin_uses_higher_score_and_agreement_bonus():
    r = paddle.combine(("BlackBrave", 0.993), ("blackbrave", 0.928))
    assert r["candidates"] == ["BlackBrave", "blackbrave"]
    assert paddle.combine(("HYUHAN", 0.99), ("HYUHAN", 0.93))["candidate_scores"]["HYUHAN"] == 101.0


def test_cleans_spaces_and_dots():
    assert paddle.combine(("....PuniPaw", 0.9), ("", 0.0))["best"] == "PuniPaw"
    assert paddle.combine((" 양마장", 0.86), ("", 0.0))["best"] == "양마장"


def test_alternatives_for_stroke_noise():
    assert "얼음마녀" in paddle.combine(("1얼음마녀", 0.873), ("", 0.0))["candidates"]
    assert "静戒丨BS" in paddle.combine(("", 0.0), ("静戒IBS", 0.713))["candidates"]
    # 영문 닉네임의 1/I/l은 건드리지 않음
    assert paddle.combine(("1lIl1abc", 0.9), ("", 0.0))["candidates"] == ["1lIl1abc"]


def test_junk_and_empty():
    assert paddle.combine(("———−", 0.54), ("", 0.0))["best"] == ""
    assert paddle.combine(("", 0.0), ("", 0.0))["candidates"] == []


def test_blank_slots_skip_models():
    calls = []
    fake = {"korean": lambda img: calls.append(1) or ("x", 1.0), "ch": lambda img: calls.append(1) or ("x", 1.0)}
    reader = paddle.PaddleReader(models=fake)
    assert [r["best"] for r in reader.read(name_crops("team_lobby.png"))] == ["", "", ""]
    assert calls == []


def test_blank_slots_are_never_ready(reader):
    """비율 기준을 낮춰 OCR이 도는 빈 칸('main.png' 0.036)도 '읽힌 칸'이 되지 않음"""
    for name in ("team_lobby.png", "main.png"):
        assert not any(slot_ready(r) for r in reader.read(name_crops(name)))


# ---- 실제 모델 ----


@pytest.fixture(scope="module")
def reader():
    pytest.importorskip("rapidocr")
    return paddle.PaddleReader()


def _results(reader):
    for image, names in EXPECTED.items():
        for idx, (expected, result) in enumerate(zip(names, reader.read(name_crops(image)))):
            yield image, idx, expected, result


def test_nicknames(reader):
    failures = []
    for image, idx, expected, result in _results(reader):
        ok = expected in api_tried(result) if (image, idx) in API_RESOLVED else result["best"] == expected
        if not ok:
            failures.append(f"{image}[{idx}] {expected!r}: best={result['best']!r} 후보={result['candidate_scores']}")
    assert not failures, "\n".join(failures)


def test_native_resolution_crop(reader):
    crop = Image.open(fixture("crop_2880x1800_fujita.png")).convert("RGB")
    assert reader.read([crop])[0]["best"] == "藤田皮卡丘"


def test_short_name_is_not_treated_as_blank(reader):
    """2880x1800의 두 글자 닉네임: 흰 글씨 비율 0.046 (예전 기준 0.05면 빈 칸으로 생략됨)"""
    crop = Image.open(fixture("crop_2880x1800_short_hangul.png")).convert("RGB")
    assert reader.read([crop])[0]["best"] == "르채"


if __name__ == "__main__":
    r = paddle.PaddleReader()
    total = best_ok = 0
    for image, idx, expected, result in _results(r):
        total += 1
        best_ok += result["best"] == expected
        mark = "OK " if result["best"] == expected else ("API" if expected in api_tried(result) else "XX ")
        print(f"[{mark}] {image}[{idx}] {expected!r}: best={result['best']!r} ({result['confidence']})")
    print(f"\n1순위 정답: {best_ok}/{total}")
