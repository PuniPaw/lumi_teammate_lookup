"""
게임이 켜지면 앱(lumi.app)을 실행하고, 게임이 꺼지면 함께 종료합니다.
"""

import subprocess
import sys
import time

import psutil

from lumi.config import FROZEN, PROJECT_ROOT, Settings

POLL_INTERVAL_SECONDS = 5


def is_running(process_name: str) -> bool:
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info["name"] or "").lower() == process_name.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def app_command() -> list[str]:
    """앱 실행 명령. exe로 빌드하면 sys.executable이 Python이 아니라 exe 자신이라 -m을 쓸 수 없음."""
    if FROZEN:
        return [sys.executable, "--app"]
    return [sys.executable, "-m", "lumi.app"]


def watch(settings: Settings) -> None:
    name = settings.game_process_name
    print(f"'{name}' 프로세스를 감시합니다. (Ctrl+C로 종료)")
    app = None
    try:
        while True:
            game_running = is_running(name)
            app_running = app is not None and app.poll() is None
            if game_running and not app_running:
                print("게임 감지됨 -> 오버레이 실행")
                app = subprocess.Popen(app_command(), cwd=PROJECT_ROOT)
            elif not game_running and app_running:
                print("게임 종료 감지됨 -> 오버레이 종료")
                app.terminate()
                app = None
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\n감시 종료.")
        if app is not None and app.poll() is None:
            app.terminate()
