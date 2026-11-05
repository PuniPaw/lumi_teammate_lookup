"""debug_store: 디버그 이미지 저장/정리 테스트."""

import os

import pytest
from PIL import Image

import debug_store


@pytest.fixture(autouse=True)
def debug_on(tmp_path, monkeypatch):
    monkeypatch.setattr(debug_store, "ENABLED", True)
    monkeypatch.setattr(debug_store, "DEBUG_DIR", str(tmp_path))


def _touch(path):
    Image.new("RGB", (4, 4)).save(path)


def test_cleanup_keeps_recent_matches(tmp_path, monkeypatch):
    # 예전 형식 파일 + 시각 형식 5판 (판마다 크롭 3장, 일부는 화면 캡처 포함)
    _touch(tmp_path / "match1_end.png")
    _touch(tmp_path / "match1_teammate_1.png")
    prefixes = [f"20261105-10{m:02d}00" for m in range(5)]
    for p in prefixes:
        for k in (1, 2, 3):
            _touch(tmp_path / f"{p}_teammate_{k}.png")
    _touch(tmp_path / f"{prefixes[0]}_screen.png")
    _touch(tmp_path / f"{prefixes[4]}_screen.png")
    # 하위 폴더(debug_crops.py 결과)는 건드리지 않음
    (tmp_path / "crops").mkdir()
    _touch(tmp_path / "crops" / "x_teammate_1.png")

    removed = debug_store.cleanup(keep=2)

    left = sorted(os.listdir(tmp_path))
    assert removed == 2 + 3 * 3 + 1  # 예전 형식 2 + 오래된 3판의 크롭 9 + 화면 1
    assert left == sorted(
        ["crops"]
        + [f"{p}_teammate_{k}.png" for p in prefixes[3:] for k in (1, 2, 3)]
        + [f"{prefixes[4]}_screen.png"]
    )
    assert os.path.exists(tmp_path / "crops" / "x_teammate_1.png")


def test_save_crops_and_screen(tmp_path, monkeypatch):
    results = [{"name": "teammate_1", "crop_image": Image.new("RGB", (10, 4))}]
    debug_store.save_crops("20261105-101434", results)
    window = {"left": 0, "top": 0, "width": 8, "height": 8, "title": "Eternal Return"}
    path = debug_store.save_screen("20261105-101434", lambda: (Image.new("RGB", (8, 8)), window))
    assert sorted(os.listdir(tmp_path)) == [
        "20261105-101434_screen.png",
        "20261105-101434_teammate_1.png",
    ]
    assert path.endswith("_screen.png")


def test_save_screen_failure_is_harmless(tmp_path, monkeypatch):

    def boom():
        raise RuntimeError("게임 창 없음")

    assert debug_store.save_screen("p", boom) is None


def test_disabled_by_default_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(debug_store, "ENABLED", False)
    debug_store.save_crops("p", [{"name": "teammate_1", "crop_image": Image.new("RGB", (4, 4))}])
    assert debug_store.save_screen("p", lambda: (Image.new("RGB", (4, 4)), {})) is None
    assert os.listdir(tmp_path) == []
