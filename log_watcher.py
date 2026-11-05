"""
Eternal Return Player.log 실시간 감시 스크립트
매칭 완료(MatchingComplete) 시점을 감지해서 팀원 공개 트리거로 사용.
"""

import os
import time

LOG_PATH = os.path.expandvars(
    r"%USERPROFILE%\AppData\LocalLow\NimbleNeuron\Eternal Return\Player.log"
)

# 매칭 완료를 알리는 신호들. 둘 중 하나만 잡아도 충분하지만
# 안정성을 위해 여러 키워드를 후보로 둔다.
MATCH_COMPLETE_KEYWORDS = [
    "MatchingComplete",
    "MatchingPadding, Matched",
]

# 참고용으로 같이 로깅해둘 큐 상태 키워드 (디버깅/로그 확인용)
QUEUE_KEYWORDS = [
    "WaitForStartMatching",
    "StartMatching",
    "MatchingCycleComplete",
]


def is_match_complete(line: str) -> bool:
    """로그 한 줄이 매칭 완료 신호인지."""
    return any(kw in line for kw in MATCH_COMPLETE_KEYWORDS)


def follow(path: str):
    """새로 추가되는 줄만 계속 읽어오는 tail -f 스타일 제너레이터.

    게임을 재시작하면 Player.log가 처음부터 다시 쓰이므로(파일 크기가
    줄어듦), 그 경우 파일 처음부터 다시 읽습니다."""
    # 파일이 생성되기 전일 수도 있으니 대기
    while not os.path.exists(path):
        print(f"[대기] 로그 파일이 아직 없습니다: {path}")
        time.sleep(2)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        # 지금 켜져 있는 게임 기준으로만 보고 싶으면 끝으로 이동
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                try:
                    if os.path.getsize(path) < f.tell():
                        f.seek(0)  # 로그 파일이 새로 쓰이기 시작함
                        continue
                except OSError:
                    pass
                time.sleep(0.3)  # 너무 자주 폴링하지 않도록
                continue
            yield line


def main():
    print(f"감시 시작: {LOG_PATH}")
    print("큐를 잡고 매칭을 기다려주세요...\n")

    for line in follow(LOG_PATH):
        stripped = line.strip()

        if is_match_complete(stripped):
            print(f"\n🎯 매칭 완료 감지! -> {stripped}")
            print("(실제 모달 표시는 live_overlay.py가 담당합니다)\n")
        else:
            for kw in QUEUE_KEYWORDS:
                if kw in stripped:
                    print(f"[상태] {stripped}")
                    break


if __name__ == "__main__":
    main()