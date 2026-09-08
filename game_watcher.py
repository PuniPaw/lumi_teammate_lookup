"""
이터널 리턴 프로세스를 감시하다가, 게임이 켜지면 오버레이를 자동 실행하고
게임이 꺼지면 오버레이도 같이 종료하는 런처.

사용법:
  1) 아래 GAME_PROCESS_NAME을 실제 프로세스 이름으로 맞춰야 합니다.
     (작업 관리자 -> 세부 정보 탭에서 이터널 리턴 켠 상태로 확인)
  2) pip install psutil (requirements.txt에 이미 추가돼 있음)
  3) python game_watcher.py 로 실행해두면, 이후로는 게임만 켜고 끄면
     알아서 오버레이가 따라 켜지고 꺼집니다.

지금은 overlay_demo.py(가짜 데이터)를 띄우도록 되어 있습니다.
실제 파이프라인(OCR + Open API 조회)이 완성되면 오버레이 진입점을
그쪽으로 바꾸면 됩니다.
"""

import subprocess
import sys
import time

import psutil

# TODO: 작업 관리자에서 확인한 실제 프로세스 이름으로 바꾸세요.
GAME_PROCESS_NAME = "EternalReturn-Win64-Shipping.exe"

# 지금 띄울 오버레이 스크립트 (나중에 실전 파이프라인으로 교체)
OVERLAY_SCRIPT = "overlay_demo.py"

# 몇 초 간격으로 게임 실행 여부를 확인할지
POLL_INTERVAL_SECONDS = 5


def is_game_running() -> bool:
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == GAME_PROCESS_NAME.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def main():
    print(f"'{GAME_PROCESS_NAME}' 프로세스를 감시합니다. (Ctrl+C로 종료)")
    overlay_process = None

    try:
        while True:
            game_running = is_game_running()
            overlay_running = overlay_process is not None and overlay_process.poll() is None

            if game_running and not overlay_running:
                print("게임 감지됨 -> 오버레이 실행")
                overlay_process = subprocess.Popen([sys.executable, OVERLAY_SCRIPT])

            elif not game_running and overlay_running:
                print("게임 종료 감지됨 -> 오버레이 종료")
                overlay_process.terminate()
                overlay_process = None

            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n감시 종료.")
        if overlay_process is not None and overlay_process.poll() is None:
            overlay_process.terminate()


if __name__ == "__main__":
    main()