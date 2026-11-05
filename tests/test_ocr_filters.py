"""OCR 세부 동작: 잡음 필터, 빈 칸 생략, 빠른 단계, 닉네임 위치 계산."""

import screen_capture
import teammate_ocr
from conftest import fixture


def test_is_junk():
    # UI 가로선을 읽은 결과 (이 닉네임의 실제 유저가 있어 오매칭된 적 있음)
    for junk in ("一一一一", "||", "-丨-", ""):
        assert teammate_ocr._is_junk(junk)
    for name in ("sooin", "静戒丨BS", "ya발견"):
        assert not teammate_ocr._is_junk(name)


def _count_ocr_calls(monkeypatch) -> list:
    calls = []
    original = teammate_ocr._ocr_words
    monkeypatch.setattr(teammate_ocr, "_ocr_words", lambda *a: calls.append(1) or original(*a))
    return calls


def test_blank_slots_skip_ocr(monkeypatch):
    calls = _count_ocr_calls(monkeypatch)
    for name in ("team_lobby.png", "main.png"):
        results = teammate_ocr.get_teammate_ocr_results_from_image(fixture(name))
        assert [r["best"] for r in results] == ["", "", ""]
    assert calls == []


def test_easy_names_use_fast_pass_only(monkeypatch):
    calls = _count_ocr_calls(monkeypatch)
    results = teammate_ocr.get_teammate_ocr_results_from_image(fixture("normal_matched_lobby.png"))
    assert [r["best"] for r in results] == ["PuniPaw", "BlackBrave", "HYUHAN"]
    assert len(calls) == 3 * len(teammate_ocr.FAST_LANGS)


def test_ui_regions_scale_from_center():
    assert screen_capture.ui_regions(1920, 1080) == [dict(r) for r in screen_capture.NAME_REGIONS_REF]
    # 16:10 (2880x1800): 배율 min(1.5, 1.667) = 1.5, 화면 중앙 기준
    r = screen_capture.ui_regions(2880, 1800)[0]
    assert (r["left"], r["top"], r["width"], r["height"]) == (1620, 1492, 201, 21)
    # 같은 비율이면 크기에 비례 (3840x2160 = 2배)
    r = screen_capture.ui_regions(3840, 2160)[2]
    assert (r["left"], r["top"], r["width"], r["height"]) == (3330, 1870, 240, 28)
