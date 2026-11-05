"""
이터널 리턴이 켜지면 live_overlay.py를 실행하고, 게임이 꺼지면 함께 종료합니다.

실행: python game_watcher.py
"""

import os
import subprocess
import sys
import time

import psutil

# 작업 관리자 -> 세부 정보 탭의 '이름'
GAME_PROCESS_NAME = "EternalReturn.exe"
OVERLAY_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_overlay.py")
POLL_INTERVAL_SECONDS = 5


def is_game_running() -> bool:
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info["name"] or "").lower() == GAME_PROCESS_NAME.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def main() -> None:
    print(f"'{GAME_PROCESS_NAME}' 프로세스를 감시합니다. (Ctrl+C로 종료)")
    overlay = None
    try:
        while True:
            game_running = is_game_running()
            overlay_running = overlay is not None and overlay.poll() is None
            if game_running and not overlay_running:
                print("게임 감지됨 -> 오버레이 실행")
                overlay = subprocess.Popen([sys.executable, OVERLAY_SCRIPT])
            elif not game_running and overlay_running:
                print("게임 종료 감지됨 -> 오버레이 종료")
                overlay.terminate()
                overlay = None
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\n감시 종료.")
        if overlay is not None and overlay.poll() is None:
            overlay.terminate()


if __name__ == "__main__":
    main()
