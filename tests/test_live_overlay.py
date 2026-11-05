"""live_overlay 전체 흐름 통합 테스트 (게임/API 없이, Qt offscreen).

가짜 로그에 매칭 완료를 쓰면 -> 닉네임 OCR(저장된 스크린샷) -> 모달 표시 ->
화면이 바뀌면 모달이 닫히는지 확인합니다.
"""

import time

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

import live_overlay  # noqa: E402
import log_watcher  # noqa: E402
from conftest import fixture  # noqa: E402
from overlay import OverlayWindow  # noqa: E402
from player_stats import failed_stats  # noqa: E402
from screen_capture import crops_from_image  # noqa: E402
from teammate_ocr import get_teammate_ocr_results_from_image  # noqa: E402


def _wait_until(app, cond, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.05)
    return False


class DummyClient:
    def __init__(self, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_match_shows_modal_then_closes_when_game_starts(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])

    log_path = tmp_path / "Player.log"
    log_path.write_text("boot\n", encoding="utf-8")
    monkeypatch.setattr(log_watcher, "LOG_PATH", str(log_path))

    # 처음 두 번은 닉네임이 아직 안 그려진 화면, 그다음부터 매칭 화면
    ocr_frames = iter(["team_lobby.png", "team_lobby.png"])
    screen = {"name": "test3.png"}
    monkeypatch.setattr(
        live_overlay,
        "get_teammate_ocr_results",
        lambda: get_teammate_ocr_results_from_image(fixture(next(ocr_frames, "test3.png"))),
    )
    monkeypatch.setattr(
        live_overlay, "capture_crops", lambda refine=True: crops_from_image(fixture(screen["name"]), refine=refine)
    )

    seen = {}

    def fake_fetch(client, results):
        seen["names"] = [r["best"] for r in results]
        return [failed_stats(n) for n in seen["names"]]

    monkeypatch.setattr(live_overlay, "fetch_team_stats", fake_fetch)
    monkeypatch.setattr(live_overlay, "Client", DummyClient)

    controller = live_overlay.OverlayController()
    controller.timer.setInterval(50)
    worker = live_overlay.MatchWorker()
    worker.match_detected.connect(controller.on_match_detected)
    worker.team_ready.connect(controller.on_team_ready)
    worker.start()
    time.sleep(0.5)  # follow()가 파일 끝으로 이동할 시간

    with open(log_path, "a", encoding="utf-8") as f:
        # 실제 로그처럼 매칭 완료가 연달아 두 줄 -> 한 번만 처리돼야 함
        f.write("[OnReceiveMatchingUpdate] MatchingComplete, matchPadding.userCount : 16\n")
        f.write("[OnReceiveMatchingUpdate] matchingNotification : MatchingPadding, Matched\n")

    assert _wait_until(app, lambda: controller.window is not None), "모달이 뜨지 않음"
    assert worker._current_match_id() == 1
    assert seen["names"] == ["PuniPaw", "로즈만때리는루크", "마브하라"]
    assert controller.window.isVisible()

    # 캐릭터 선택 중 (같은 화면) -> 계속 떠 있음
    for _ in range(10):
        app.processEvents()
        time.sleep(0.05)
    assert controller.window is not None

    # 게임 시작 -> 닉네임 칸이 사라진 화면
    screen["name"] = "main.png"
    assert _wait_until(app, lambda: controller.window is None, timeout=5), "모달이 닫히지 않음"


def test_overlay_is_placed_inside_screen():
    """고정 좌표를 쓰면 배율 200% 화면에서 화면 밖에 뜰 수 있음"""
    app = QApplication.instance() or QApplication([])
    window = OverlayWindow([failed_stats(n) for n in ("PuniPaw", "12345a", "얼음마녀")])
    window.show()
    app.processEvents()

    screen = app.primaryScreen().availableGeometry()
    geo = window.frameGeometry()
    assert screen.contains(geo.topLeft()) and screen.contains(geo.topRight())
    assert geo.right() >= screen.right() - 100
    window.close()
