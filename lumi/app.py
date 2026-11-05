"""
매칭이 잡히면 팀원 전적 모달을 띄우고, 게임이 시작되면 닫습니다.

  1) 매칭 완료 신호 (MatchSignals)
  2) 닉네임이 다 그려질 때까지 캡처(ScreenSource) + OCR(NicknameReader) 재시도
  3) 닉네임 확정 + 전적 조회 (StatsProvider) -> 모달 표시
  4) 1초마다 닉네임 칸을 확인해 사라진 상태가 이어지면 모달 닫기
  새 매칭이 잡히면(닷지 후 재매칭 등) 기존 모달을 닫고 다시 진행합니다.

외부 연결은 ports.py의 인터페이스로만 다루고, 실제 구현은 build()에서 설정으로 조립합니다.
실행: python -m lumi.app  (보통은 python -m lumi가 게임 실행 시 자동 실행)
"""

import queue
import signal
import sys
import threading
import traceback
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from lumi.config import Settings, load_settings
from lumi.debug.store import DebugStore
from lumi.game.match_flow import LobbyPresence, slot_ready, wait_for_teammates
from lumi.ports import MatchSignals, NicknameReader, ScreenSource, StatsProvider
from lumi.ui.overlay import OverlayWindow

# 게임 시작 여부 확인 간격(ms)
PRESENCE_CHECK_INTERVAL_MS = 1000


def lookup_targets(results: list[dict]) -> list[dict]:
    """확실히 읽힌 칸만 API로 조회하도록, 나머지 칸은 후보를 비웁니다.

    덜 읽힌 칸의 글자('和一', 'fis' 등 잡음)가 우연히 실존 유저와 일치해 엉뚱한 전적이
    뜬 적이 있음. 비운 칸은 읽은 글자 그대로 '조회 실패' 카드가 되어 모달에서 고칠 수 있음.
    """
    return [r if slot_ready(r) else {**r, "candidates": [], "candidate_scores": {}} for r in results]


class MatchWorker(QObject):
    """백그라운드 스레드에서 매칭 신호 대기 / OCR / 전적 조회."""

    match_detected = Signal()  # 새 매칭 (기존 모달 닫기용)
    team_ready = Signal(list, list)  # (팀원 전적 목록, 게임 시작 감지용 기준 크롭)

    def __init__(
        self,
        signals: MatchSignals,
        screen: ScreenSource,
        reader: NicknameReader,
        stats: StatsProvider,
        debug: DebugStore,
    ):
        super().__init__()
        self.signals = signals
        self.screen = screen
        self.reader = reader
        self.stats = stats
        self.debug = debug
        self._events: "queue.Queue[int]" = queue.Queue()
        self._match_id = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._watch_matches, daemon=True).start()
        threading.Thread(target=self._process_matches, daemon=True).start()

    def current_match_id(self) -> int:
        with self._lock:
            return self._match_id

    def _watch_matches(self) -> None:
        for _ in self.signals.matches():
            with self._lock:
                self._match_id += 1
                match_id = self._match_id
            print(f"\n🎯 매칭 완료 감지 (#{match_id})")
            self.match_detected.emit()
            self._events.put(match_id)

    def _process_matches(self) -> None:
        while True:
            match_id = self._events.get()
            if match_id != self.current_match_id():
                continue  # 처리 전에 더 새로운 매칭이 들어옴
            try:
                self._handle_match(match_id)
            except Exception:
                traceback.print_exc()

    def _handle_match(self, match_id: int) -> None:
        def superseded() -> bool:
            return match_id != self.current_match_id()

        print("  닉네임 인식 중...")
        hidden_seen = False
        attempt = 0

        def read() -> list[dict]:
            nonlocal attempt, hidden_seen
            attempt += 1
            # 화면을 보이는 그대로 캡처하므로, 게임 창이 가려져 있으면 다른 창을 읽게 됨.
            # 그 결과가 우연히 실존 유저와 일치할 수 있어 아예 읽지 않고 기다림
            if not self.screen.is_active():
                if not hidden_seen:
                    print("  ⚠️ 게임 창이 다른 창에 가려져 있습니다. 게임 창을 맨 앞에 두세요.")
                hidden_seen = True
                return []
            results = self.reader.read(self.screen.name_crops())
            if self.debug.enabled:
                print(f"  시도 {attempt}: " + ", ".join(f"{r['best']!r}({r['confidence']})" for r in results))
            return results

        results, ready = wait_for_teammates(read, should_stop=superseded)
        if superseded():
            return

        prefix = self.debug.new_match_prefix()
        self.debug.save_crops(prefix, results or [])
        if not results or ready < len(results):
            self.debug.save_screen(prefix, self.screen.snapshot)
        self.debug.cleanup()

        if not results or ready == 0:
            hint = " (게임 창이 가려져 있었음)" if hidden_seen else ""
            print(f"  ❌ 닉네임을 인식하지 못했습니다.{hint}")
            return
        for r in results:
            print(f"  {'✅' if slot_ready(r) else '⚠️'} {r['name']}: {r['best']!r} (점수 {r['confidence']})")

        team_stats = self.stats.team_stats(lookup_targets(results))
        if ready == len(results) and any(not s.get("user_id") for s in team_stats):
            self.debug.save_screen(prefix, self.screen.snapshot)  # 읽었지만 확정 못 한 팀원
        if superseded() or not team_stats:
            return

        try:
            reference = self.screen.name_crops(refine=False)  # 게임 시작 감지는 항상 같은 위치를 비교
        except Exception:
            reference = [r["crop_image"] for r in results]
        self.team_ready.emit(team_stats, reference)


class OverlayController(QObject):
    """메인(Qt) 스레드에서 모달 표시/닫기."""

    def __init__(self, screen: ScreenSource, stats: StatsProvider, debug: DebugStore):
        super().__init__()
        self.screen = screen
        self.stats = stats
        self.debug = debug
        self.window: Optional[OverlayWindow] = None
        self.presence: Optional[LobbyPresence] = None
        self.timer = QTimer(self)
        self.timer.setInterval(PRESENCE_CHECK_INTERVAL_MS)
        self.timer.timeout.connect(self._check_game_started)

    def close_overlay(self, reason: str = "") -> None:
        self.timer.stop()
        self.presence = None
        if self.window is not None:
            if reason:
                print(f"  모달 닫기: {reason}")
            self.window.close()
            self.window.deleteLater()
            self.window = None

    def on_match_detected(self) -> None:
        self.close_overlay("새 매칭")

    def on_team_ready(self, team_stats: list, reference: list) -> None:
        self.close_overlay()
        self.window = OverlayWindow(team_stats, refetch=self.stats.user_stats)
        self.window.show()
        self.window.raise_()
        if self.debug.enabled:
            geo = self.window.frameGeometry()
            print(f"  모달 위치=({geo.x()},{geo.y()}) 크기={geo.width()}x{geo.height()} (Qt 논리 좌표)")
        self.presence = LobbyPresence(reference)
        self.timer.start()
        print("✅ 모달 표시")

    def _check_game_started(self) -> None:
        if self.window is None or not self.window.isVisible():  # 닫기 버튼으로 닫음
            self.close_overlay()
            return
        try:
            current = self.screen.name_crops(refine=False)
        except Exception:
            current = None  # 게임 창을 못 찾으면 '사라짐'으로 취급
        if self.presence.update(current):
            self.close_overlay("게임 시작")


def connect(worker: MatchWorker, controller: OverlayController) -> None:
    worker.match_detected.connect(controller.on_match_detected)
    worker.team_ready.connect(controller.on_team_ready)


def build(settings: Settings) -> tuple[MatchWorker, OverlayController]:
    """설정으로 실제 구현(어댑터)을 만들어 조립합니다."""
    from lumi.api.player_stats import EternalReturnStats
    from lumi.capture.screen import LiveScreen
    from lumi.game.log import PlayerLog
    from lumi.ocr import make_reader

    screen = LiveScreen(settings.game_window_title)
    stats = EternalReturnStats(settings.api_key)
    try:
        stats.load_character_names()
    except RuntimeError as e:
        print(f"⚠️ {e} (캐릭터 이름 대신 코드로 표시됩니다)")
    debug = DebugStore(settings.debug, settings.debug_dir)

    worker = MatchWorker(PlayerLog(settings.log_path), screen, make_reader(settings), stats, debug)
    controller = OverlayController(screen, stats, debug)
    connect(worker, controller)
    return worker, controller


def main() -> None:
    settings = load_settings()
    if not settings.api_key:
        print("❌ ETERNAL_RETURN_API_KEY가 설정되지 않았습니다. .env를 확인하세요.")
        sys.exit(1)

    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Qt 이벤트 루프 중에도 Ctrl+C로 종료
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 모달을 닫아도 감시는 계속

    worker, _controller = build(settings)
    worker.start()
    print("매칭을 기다리는 중... (Ctrl+C 또는 게임 종료 시 함께 종료)")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
