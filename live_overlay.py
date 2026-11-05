"""
실전 모드: 매칭이 잡히면 팀원 전적 모달을 자동으로 띄우고,
게임이 시작되면 자동으로 닫습니다.

흐름
  1) Player.log를 감시하다가 매칭 완료(MatchingComplete 등) 줄이 나오면
  2) 게임 화면의 닉네임 칸을 캡처+OCR. 닉네임이 아직 안 그려졌을 수 있어서
     모든 칸이 읽힐 때까지 최대 OCR_RETRY_TIMEOUT_SECONDS초 재시도
     (match_flow.wait_for_teammates)
  3) Open API로 닉네임 확정 + 전적 조회 후 모달 표시
  4) 1초마다 닉네임 칸을 캡처해서, 칸이 화면에서 사라진 상태가 몇 초
     이어지면(로딩 화면/인게임 진입) 모달을 자동으로 닫음
     (match_flow.LobbyPresence)
  - 모달이 떠 있는 중에 새 매칭이 잡히면 (닷지 후 재매칭 등) 기존 모달을
    닫고 새로 진행합니다.

실행: python live_overlay.py   (보통은 game_watcher.py가 게임 실행 시 자동 실행)
Windows 전용 (게임 창 위치를 pygetwindow로 찾음).
"""

import os
import queue
import signal
import sys
import threading
import time
import traceback
from typing import Optional

from dotenv import load_dotenv
from bserpy import Client
from bserpy.utils import SeasonHelper
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

import debug_store
import log_watcher
from match_flow import LobbyPresence, slot_ready, wait_for_teammates
from overlay_demo import (
    OverlayWindow,
    _failed_stats,
    _fetch_single_user_stats,
    load_character_names,
)
from resolve_teammates import resolve_teammate_names
from teammate_ocr import (
    capture_crops,
    capture_window_snapshot,
    get_teammate_ocr_results,
    is_game_window_active,
)

load_dotenv()
API_KEY = os.getenv("ETERNAL_RETURN_API_KEY")

# 매칭 완료 로그는 한 번에 여러 줄(MatchingComplete, MatchingPadding, Matched)
# 찍히므로, 이 시간(초) 안에 다시 들어온 신호는 같은 매칭으로 봅니다.
MATCH_DEBOUNCE_SECONDS = 5.0

# 게임 시작 여부를 확인하는 간격(ms)
PRESENCE_CHECK_INTERVAL_MS = 1000

def fetch_team_stats(client: Client, ocr_results: list[dict]) -> list[dict]:
    """OCR 결과 -> 닉네임 확정 -> 전적 조회. 모달에 넘길 stats 목록을 반환.

    API로 확정하지 못한 칸도 OCR이 읽은 글자로 '조회 실패' 카드를 만들어 두어,
    사용자가 모달에서 닉네임을 고쳐 다시 조회할 수 있게 합니다.
    """
    season = SeasonHelper(client).current_season()
    season_id = season["seasonID"] if season else None

    resolved = resolve_teammate_names(client, ocr_results)
    team_stats = []
    for ocr, res in zip(ocr_results, resolved):
        nickname = res["resolved_nickname"]
        if nickname and season_id is not None:
            try:
                team_stats.append(_fetch_single_user_stats(client, nickname, season_id))
                continue
            except Exception as e:
                print(f"  '{nickname}' 전적 조회 실패: {e}")
        fallback = nickname or ocr.get("best") or ""
        if fallback:
            team_stats.append(_failed_stats(fallback))
    return team_stats


class MatchWorker(QObject):
    """백그라운드 스레드에서 로그 감시 / OCR / API 조회를 담당."""

    match_detected = Signal()  # 새 매칭 감지 (기존 모달 닫기용)
    team_ready = Signal(list, list)  # (team_stats, 기준 크롭 이미지 목록)

    def __init__(self):
        super().__init__()
        self._events: "queue.Queue[int]" = queue.Queue()
        self._match_id = 0
        self._lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._watch_log, daemon=True).start()
        threading.Thread(target=self._process_matches, daemon=True).start()

    # -- 로그 감시 스레드 ------------------------------------------------------
    def _watch_log(self):
        print(f"로그 감시 시작: {log_watcher.LOG_PATH}")
        last_match_at = float("-inf")
        for line in log_watcher.follow(log_watcher.LOG_PATH):
            if log_watcher.is_match_complete(line):
                now = time.monotonic()
                if now - last_match_at < MATCH_DEBOUNCE_SECONDS:
                    continue  # 같은 매칭의 다른 로그 줄
                last_match_at = now
                with self._lock:
                    self._match_id += 1
                    match_id = self._match_id
                print(f"\n🎯 매칭 완료 감지 (#{match_id}): {line.strip()}")
                self.match_detected.emit()
                self._events.put(match_id)

    def _current_match_id(self) -> int:
        with self._lock:
            return self._match_id

    # -- 매칭 처리 스레드 ------------------------------------------------------
    def _process_matches(self):
        while True:
            match_id = self._events.get()
            if match_id != self._current_match_id():
                continue  # 처리 전에 더 새로운 매칭이 들어옴
            try:
                self._handle_match(match_id)
            except Exception:
                traceback.print_exc()

    def _handle_match(self, match_id: int):
        def superseded() -> bool:
            return match_id != self._current_match_id()

        print("  닉네임 인식 중 (재시도)...")
        prefix = debug_store.new_match_prefix()
        screen_saved = False
        attempt = 0

        def read():
            nonlocal attempt
            attempt += 1
            if not is_game_window_active():
                print(f"  시도 {attempt}: ⚠️ 게임 창이 다른 창에 가려져 있음 (게임 창을 맨 앞으로)")
            results = get_teammate_ocr_results()
            summary = ", ".join(f"{r['best']!r}({r['confidence']})" for r in results)
            print(f"  시도 {attempt}: {summary}")
            return results

        results, ready = wait_for_teammates(read, should_stop=superseded)
        if superseded():
            return
        # 디버그 자료: 닉네임 칸은 매 판, 전체 화면은 인식이 덜 된 판만 저장
        debug_store.save_crops(prefix, results or [])
        if not results or ready < len(results):
            screen_saved = bool(debug_store.save_screen(prefix, capture_window_snapshot))
        debug_store.cleanup()
        if not results or ready == 0:
            print("  ❌ 닉네임을 인식하지 못했습니다. (모달 표시 안 함)")
            print(f"     {debug_store.DEBUG_DIR} 폴더의 {prefix}_screen.png 에서 빨간 박스가 닉네임 위치에 있는지 확인하세요.")
            return
        for r in results:
            mark = "✅" if slot_ready(r) else "⚠️"
            print(f"  {mark} {r['name']}: {r['best']!r} (점수 {r['confidence']})")

        with Client(api_key=API_KEY) as client:
            team_stats = fetch_team_stats(client, results)
        if not screen_saved and any(not s.get("user_id") for s in team_stats):
            # 닉네임은 읽었지만 API로 확정 못 한 팀원이 있음 -> 화면도 저장
            debug_store.save_screen(prefix, capture_window_snapshot)
        if superseded() or not team_stats:
            return

        # 게임 시작 감지 기준 이미지: 미세 보정 없이 '항상 같은 위치'를 캡처
        try:
            reference = capture_crops(refine=False)
        except Exception:
            reference = [r["crop_image"] for r in results]
        self.team_ready.emit(team_stats, reference)


class OverlayController(QObject):
    """메인(Qt) 스레드에서 모달 표시/닫기를 담당."""

    def __init__(self):
        super().__init__()
        self.window: Optional[OverlayWindow] = None
        self.presence: Optional[LobbyPresence] = None
        self.timer = QTimer(self)
        self.timer.setInterval(PRESENCE_CHECK_INTERVAL_MS)
        self.timer.timeout.connect(self._check_game_started)

    def close_overlay(self, reason: str = ""):
        self.timer.stop()
        self.presence = None
        if self.window is not None:
            if reason:
                print(f"  모달 닫기: {reason}")
            self.window.close()
            self.window.deleteLater()
            self.window = None

    def on_match_detected(self):
        self.close_overlay("새 매칭 감지")

    def on_team_ready(self, team_stats: list, reference: list):
        self.close_overlay()
        self.window = OverlayWindow(team_stats)
        self.window.show()
        self.window.raise_()
        geo = self.window.frameGeometry()
        print(f"  모달 위치=({geo.x()},{geo.y()}) 크기={geo.width()}x{geo.height()} (Qt 논리 좌표)")
        self.presence = LobbyPresence(reference)
        self.timer.start()
        print("✅ 모달 표시")

    def _check_game_started(self):
        if self.window is None or not self.window.isVisible():
            # 사용자가 닫기 버튼으로 닫은 경우
            self.close_overlay()
            return
        try:
            current = capture_crops(refine=False)
        except Exception:
            current = None  # 게임 창을 못 찾음 -> '사라짐'으로 취급
        if self.presence.update(current):
            self.close_overlay(f"게임 시작 감지 (배경 차이 {self.presence.last_diff})")


def main():
    if not API_KEY:
        print("❌ ETERNAL_RETURN_API_KEY가 설정되지 않았습니다. .env를 확인하세요.")
        sys.exit(1)

    # Qt 이벤트 루프 중에도 Ctrl+C로 바로 종료되도록
    signal.signal(signal.SIGINT, signal.SIG_DFL)
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
