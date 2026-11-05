"""
게임 로그(Player.log)에서 매칭 완료를 감지합니다 (ports.MatchSignals).

로그에는 매칭 상태만 기록되고 플레이어 닉네임은 없어서, 팀원은 화면 OCR로 읽습니다.
매칭 관련 로그 줄 확인: python -m lumi.game.log
"""

import os
import time
from typing import Callable, Iterator

# 매칭 완료 신호. 한 번의 매칭에 몇 ms 간격으로 연달아 찍힘
MATCH_COMPLETE_KEYWORDS = ["MatchingComplete", "MatchingPadding, Matched"]
# 이 시간(초) 안에 다시 온 신호는 같은 매칭으로 봄
MATCH_DEBOUNCE_SECONDS = 5.0


def is_match_complete(line: str) -> bool:
    return any(kw in line for kw in MATCH_COMPLETE_KEYWORDS)


def follow(path: str) -> Iterator[str]:
    """새로 추가되는 줄만 계속 읽습니다 (tail -f).
    게임을 재시작해 로그가 처음부터 다시 쓰이면 파일 처음으로 돌아갑니다."""
    while not os.path.exists(path):
        print(f"[대기] 로그 파일이 아직 없습니다: {path}")
        time.sleep(2)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if line:
                yield line
                continue
            try:
                if os.path.getsize(path) < f.tell():
                    f.seek(0)
                    continue
            except OSError:
                pass
            time.sleep(0.3)


class PlayerLog:
    """ports.MatchSignals 구현."""

    def __init__(self, path: str, clock: Callable[[], float] = time.monotonic):
        self.path = path
        self._clock = clock

    def matches(self) -> Iterator[None]:
        print(f"로그 감시 시작: {self.path}")
        last = float("-inf")
        for line in follow(self.path):
            if not is_match_complete(line):
                continue
            now = self._clock()
            if now - last >= MATCH_DEBOUNCE_SECONDS:
                last = now
                yield None


def main() -> None:
    from lumi.config import load_settings

    path = load_settings().log_path
    print(f"감시 시작: {path}\n큐를 잡으면 매칭 관련 로그가 출력됩니다.\n")
    for line in follow(path):
        if "Matching" in line:
            print(f"{'🎯' if is_match_complete(line) else '  '} {line.strip()}")


if __name__ == "__main__":
    main()
