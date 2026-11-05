"""
매칭이 잡히면 팀원 전적 모달을 띄우고, 게임이 시작되면 닫습니다.

  1) Player.log에서 매칭 완료 감지
  2) 닉네임이 다 그려질 때까지 캡처 + OCR 재시도 (match_flow.wait_for_teammates)
  3) Open API로 닉네임 확정 + 전적 조회 -> 모달 표시
  4) 1초마다 닉네임 칸을 확인해 사라진 상태가 이어지면 모달 닫기 (match_flow.LobbyPresence)
  새 매칭이 잡히면(닷지 후 재매칭 등) 기존 모달을 닫고 다시 진행합니다.

실행: python live_overlay.py  (보통은 game_watcher.py가 게임 실행 시 자동 실행, Windows 전용)
"""

import queue
import signal
import sys
import threading
import time
import traceback
from typing import Optional

from bserpy import Client
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

import debug_store
import log_watcher
from match_flow import LobbyPresence, slot_ready, wait_for_teammates
from overlay import OverlayWindow
from player_stats import API_KEY, fetch_team_stats, load_character_names
from screen_capture import capture_crops, capture_window_snapshot, is_game_window_active
from teammate_ocr import get_teammate_ocr_results

# 매칭 완료 로그는 한 번에 여러 줄 찍히므로 이 시간(초) 안의 신호는 같은 매칭으로 봄
MATCH_DEBOUNCE_SECONDS = 5.0
# 게임 시작 여부 확인 간격(ms)
PRESENCE_CHECK_INTERVAL_MS = 1000


class MatchWorker(QObject):
    """백그라운드 스레드에서 로그 감시 / OCR / API 조회."""

    match_detected = Signal()  # 새 매칭 (기존 모달 닫기용)
    team_ready = Signal(list, list)  # (팀원 전적 목록, 게임 시작 감지용 기준 크롭)

    def __init__(self):
        super().__init__()
        self._events: "queue.Queue[int]" = queue.Queue()
        self._match_id = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._watch_log, daemon=True).start()
        threading.Thread(target=self._process_matches, daemon=True).start()

    def _current_match_id(self) -> int:
        with self._lock:
            return self._match_id

    def _watch_log(self) -> None:
        print(f"로그 감시 시작: {log_watcher.LOG_PATH}")
        last_match_at = float("-inf")
        for line in log_watcher.follow(log_watcher.LOG_PATH):
            if not log_watcher.is_match_complete(line):
                continue
            now = time.monotonic()
            if now - last_match_at < MATCH_DEBOUNCE_SECONDS:
                continue
            last_match_at = now
            with self._lock:
                self._match_id += 1
                match_id = self._match_id
            print(f"\n🎯 매칭 완료 감지 (#{match_id})")
            self.match_detected.emit()
            self._events.put(match_id)

    def _process_matches(self) -> None:
        while True:
            match_id = self._events.get()
            if match_id != self._current_match_id():
                continue  # 처리 전에 더 새로운 매칭이 들어옴
            try:
                self._handle_match(match_id)
            except Exception:
                traceback.print_exc()

    def _handle_match(self, match_id: int) -> None:
        def superseded() -> bool:
            return match_id != self._current_match_id()

        print("  닉네임 인식 중...")
        warned_hidden = False
        attempt = 0

        def read() -> list[dict]:
            nonlocal attempt, warned_hidden
            attempt += 1
            if not warned_hidden and not is_game_window_active():
                warned_hidden = True
                print("  ⚠️ 게임 창이 다른 창에 가려져 있습니다. 게임 창을 맨 앞에 두세요.")
            results = get_teammate_ocr_results()
            if debug_store.ENABLED:
                print(f"  시도 {attempt}: " + ", ".join(f"{r['best']!r}({r['confidence']})" for r in results))
            return results

        results, ready = wait_for_teammates(read, should_stop=superseded)
        if superseded():
            return

        prefix = debug_store.new_match_prefix()
        debug_store.save_crops(prefix, results or [])
        if not results or ready < len(results):
            debug_store.save_screen(prefix, capture_window_snapshot)
        debug_store.cleanup()

        if not results or ready == 0:
            print("  ❌ 닉네임을 인식하지 못했습니다.")
            return
        for r in results:
            print(f"  {'✅' if slot_ready(r) else '⚠️'} {r['name']}: {r['best']!r} (점수 {r['confidence']})")

        with Client(api_key=API_KEY) as client:
            team_stats = fetch_team_stats(client, results)
        if ready == len(results) and any(not s.get("user_id") for s in team_stats):
            debug_store.save_screen(prefix, capture_window_snapshot)  # 읽었지만 확정 못 한 팀원
        if superseded() or not team_stats:
            return

        try:
            reference = capture_crops(refine=False)  # 게임 시작 감지는 항상 같은 위치를 비교
        except Exception:
            reference = [r["crop_image"] for r in results]
        self.team_ready.emit(team_stats, reference)


class OverlayController(QObject):
    """메인(Qt) 스레드에서 모달 표시/닫기."""

    def __init__(self):
        super().__init__()
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
        self.window = OverlayWindow(team_stats)
        self.window.show()
        self.window.raise_()
        if debug_store.ENABLED:
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
            current = capture_crops(refine=False)
        except Exception:
            current = None  # 게임 창을 못 찾으면 '사라짐'으로 취급
        if self.presence.update(current):
            self.close_overlay("게임 시작")


def main() -> None:
    if not API_KEY:
        print("❌ ETERNAL_RETURN_API_KEY가 설정되지 않았습니다. .env를 확인하세요.")
        sys.exit(1)

    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Qt 이벤트 루프 중에도 Ctrl+C로 종료
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 모달을 닫아도 감시는 계속

    try:
        load_character_names()
    except RuntimeError as e:
        print(f"⚠️ {e} (캐릭터 이름 대신 코드로 표시됩니다)")

    controller = OverlayController()
    worker = MatchWorker()
    worker.match_detected.connect(controller.on_match_detected)
    worker.team_ready.connect(controller.on_team_ready)
    worker.start()

    print("매칭을 기다리는 중... (Ctrl+C 또는 게임 종료 시 함께 종료)")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
