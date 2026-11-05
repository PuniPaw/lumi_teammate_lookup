"""앱 전체 흐름 통합 테스트 (게임/API 없이, Qt offscreen).

외부 연결(ports)에 가짜 구현을 넘깁니다. OCR은 실제 Tesseract로 저장된 화면을 읽습니다.
매칭 신호 -> 닉네임 인식(재시도) -> 모달 표시 -> 화면이 바뀌면 모달 닫기.
"""

import queue
import time

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from conftest import fixture  # noqa: E402
from lumi.api.player_stats import failed_stats  # noqa: E402
from lumi.app import MatchWorker, OverlayController, connect  # noqa: E402
from lumi.capture.screen import ImageScreen  # noqa: E402
from lumi.debug.store import DebugStore  # noqa: E402
from lumi.ocr.reader import TesseractReader  # noqa: E402
from lumi.ui.overlay import OverlayWindow  # noqa: E402


class FakeSignals:
    """send()를 부르면 매칭 신호 하나."""

    def __init__(self):
        self._q = queue.Queue()

    def send(self):
        self._q.put(None)

    def matches(self):
        while True:
            yield self._q.get()


class SequenceScreen(ImageScreen):
    """처음 몇 번은 다른 화면을 보여준 뒤 path로 바뀌는 화면 (refine=True인 OCR용 캡처만 셈)."""

    def __init__(self, path, first_frames):
        super().__init__(path)
        self.first_frames = list(first_frames)

    def name_crops(self, refine=True):
        if refine and self.first_frames:
            return ImageScreen(self.first_frames.pop(0)).name_crops(refine)
        return super().name_crops(refine)


class FakeStats:
    def __init__(self):
        self.seen = []

    def team_stats(self, ocr_results):
        self.seen = [r["best"] for r in ocr_results]
        return [failed_stats(n) for n in self.seen]

    def user_stats(self, nickname):
        return None


def _wait_until(app, cond, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_match_shows_modal_then_closes_when_game_starts(tmp_path):
    app = QApplication.instance() or QApplication([])
    # 닉네임이 아직 안 그려진 화면 2번 -> 매칭 화면
    screen = SequenceScreen(fixture("test3.png"), [fixture("team_lobby.png")] * 2)
    signals, stats = FakeSignals(), FakeStats()
    debug = DebugStore(enabled=False, directory=str(tmp_path))

    worker = MatchWorker(signals, screen, TesseractReader(), stats, debug)
    controller = OverlayController(screen, stats, debug)
    controller.timer.setInterval(50)
    connect(worker, controller)
    worker.start()

    signals.send()
    assert _wait_until(app, lambda: controller.window is not None), "모달이 뜨지 않음"
    assert worker.current_match_id() == 1
    assert stats.seen == ["PuniPaw", "로즈만때리는루크", "마브하라"]
    assert controller.window.isVisible()

    # 캐릭터 선택 중 (같은 화면) -> 계속 떠 있음
    for _ in range(10):
        app.processEvents()
        time.sleep(0.05)
    assert controller.window is not None

    # 게임 시작 -> 닉네임 칸이 사라진 화면
    screen.path = fixture("main.png")
    assert _wait_until(app, lambda: controller.window is None, timeout=5), "모달이 닫히지 않음"


def test_overlay_is_placed_inside_screen():
    """고정 좌표를 쓰면 배율 200% 화면에서 화면 밖에 뜰 수 있음"""
    app = QApplication.instance() or QApplication([])
    window = OverlayWindow([failed_stats(n) for n in ("PuniPaw", "12345a", "얼음마녀")], refetch=lambda n: None)
    window.show()
    app.processEvents()

    screen = app.primaryScreen().availableGeometry()
    geo = window.frameGeometry()
    assert screen.contains(geo.topLeft()) and screen.contains(geo.topRight())
    assert geo.right() >= screen.right() - 100
    window.close()
