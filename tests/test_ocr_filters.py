"""OCR 세부 동작: 잡음 필터, 닉네임 위치 계산."""

from lumi.capture import screen
from lumi.ocr.candidates import is_junk


def test_is_junk():
    # UI 가로선을 읽은 결과 (이 닉네임의 실제 유저가 있어 오매칭된 적 있음)
    for junk in ("一一一一", "||", "-丨-", ""):
        assert is_junk(junk)
    for name in ("sooin", "静戒丨BS", "ya발견"):
        assert not is_junk(name)


def test_ui_regions_scale_from_center():
    assert screen.ui_regions(1920, 1080) == [dict(r) for r in screen.NAME_REGIONS_REF]
    # 16:10 (2880x1800): 배율 min(1.5, 1.667) = 1.5, 화면 중앙 기준
    r = screen.ui_regions(2880, 1800)[0]
    assert (r["left"], r["top"], r["width"], r["height"]) == (1620, 1492, 201, 21)
    # 같은 비율이면 크기에 비례 (3840x2160 = 2배)
    r = screen.ui_regions(3840, 2160)[2]
    assert (r["left"], r["top"], r["width"], r["height"]) == (3330, 1870, 240, 28)
