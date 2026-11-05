"""OCR 잡음 필터 / 빈 칸 감지 테스트."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import teammate_ocr as t  # noqa: E402


def test_is_junk():
    # UI 가로선을 읽은 결과 (실제로 이 닉네임의 유저가 존재해 오매칭된 적 있음)
    assert t._is_junk("一一一一")
    assert t._is_junk("||")
    assert t._is_junk("-丨-")
    assert t._is_junk("")
    assert not t._is_junk("sooin")
    assert not t._is_junk("静戒丨BS")
    assert not t._is_junk("ya발견")


def test_blank_slots_skip_ocr(monkeypatch):
    calls = []
    orig = t._ocr_words
    monkeypatch.setattr(t, "_ocr_words", lambda *a: calls.append(1) or orig(*a))

    for name in ("team_lobby.png", "main.png"):
        results = t.get_teammate_ocr_results_from_image(os.path.join(ROOT, name))
        assert [r["best"] for r in results] == ["", "", ""]
    assert calls == []


def test_easy_names_use_fast_pass_only(monkeypatch):
    calls = []
    orig = t._ocr_words
    monkeypatch.setattr(t, "_ocr_words", lambda *a: calls.append(1) or orig(*a))

    results = t.get_teammate_ocr_results_from_image(os.path.join(ROOT, "normal_matched_lobby.png"))
    assert [r["best"] for r in results] == ["PuniPaw", "BlackBrave", "HYUHAN"]
    assert len(calls) == 3 * len(t.FAST_LANGS)
