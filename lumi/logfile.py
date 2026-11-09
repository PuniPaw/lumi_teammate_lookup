"""
exe로 실행할 때 print와 오류 출력을 파일에도 남깁니다 (%APPDATA%\\lumi\\logs).
테스터에게 문제가 생기면 이 파일을 받아 원인을 봅니다. 닉네임은 남지만 API 키는 앱에 없습니다.
"""

import os
import sys
from typing import Optional, TextIO


class _Tee:
    """콘솔과 파일에 같이 씁니다. 콘솔이 없거나 쓰기에 실패해도 앱은 계속 돕니다."""

    def __init__(self, console: Optional[TextIO], log: TextIO):
        self._console = console
        self._log = log

    def write(self, text: str) -> int:
        for stream in (self._console, self._log):
            if stream is None:
                continue
            try:
                stream.write(text)
                stream.flush()
            except (OSError, ValueError):  # 콘솔 창이 닫힘 등
                pass
        return len(text)

    def flush(self) -> None:
        for stream in (self._console, self._log):
            if stream is None:
                continue
            try:
                stream.flush()
            except (OSError, ValueError):
                pass

    def isatty(self) -> bool:
        return False


def setup_log(directory: str, name: str) -> str:
    """stdout/stderr를 {directory}/{name}.log에도 남깁니다. 이전 실행 기록은 .old.log로 하나만 보관."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{name}.log")
    if os.path.exists(path):
        os.replace(path, os.path.join(directory, f"{name}.old.log"))
    log = open(path, "w", encoding="utf-8", errors="replace", buffering=1)
    for console in (sys.stdout, sys.stderr):
        # 한국어 Windows 콘솔(cp949)은 이모지를 못 써서 print가 예외를 냄
        if console is not None and hasattr(console, "reconfigure"):
            console.reconfigure(errors="replace")
    sys.stdout = _Tee(sys.stdout, log)
    sys.stderr = _Tee(sys.stderr, log)
    return path
