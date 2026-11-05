"""
매칭 완료 ~ 게임 시작 사이의 판단 로직 (Qt/게임 없이 테스트 가능).

- wait_for_teammates(): 닉네임이 다 그려질 때까지 캡처 + OCR 재시도
- LobbyPresence: 닉네임 칸이 화면에서 사라진 상태가 이어지면 '게임 시작'으로 판단
"""

import time
from typing import Callable, Optional

from PIL import Image, ImageChops, ImageStat

# 매칭 완료 후 재시도할 최대 시간(초)과 간격(초)
OCR_RETRY_TIMEOUT_SECONDS = 15.0
OCR_RETRY_INTERVAL_SECONDS = 0.5
# 한 칸이 '읽혔다'고 볼 OCR 점수 (실제 닉네임은 대부분 80~100, 잡음은 70 미만)
SLOT_READY_SCORE = 75
MIN_NICKNAME_LENGTH = 2

# 기준 이미지와 닉네임 칸 '배경'의 차이가 이 값을 넘으면 칸이 사라진 것으로 봄
# (측정값: 같은 매칭 화면 0, 닉네임만 다른 매칭 화면 3~14, 로비가 아닌 화면 50~85)
LOBBY_GONE_DIFF = 30
# 연속 몇 번 사라져야 게임 시작으로 볼지 (1초 간격이면 약 3초)
LOBBY_GONE_CONSECUTIVE = 3


def slot_ready(result: dict, ready_score: float = SLOT_READY_SCORE) -> bool:
    """OCR 결과 한 칸이 닉네임을 확실히 읽은 상태인지."""
    best = result.get("best") or ""
    score = (result.get("candidate_scores") or {}).get(best, result.get("confidence", 0))
    return len(best) >= MIN_NICKNAME_LENGTH and score >= ready_score


def wait_for_teammates(
    read_fn: Callable[[], list[dict]],
    timeout: float = OCR_RETRY_TIMEOUT_SECONDS,
    interval: float = OCR_RETRY_INTERVAL_SECONDS,
    ready_score: float = SLOT_READY_SCORE,
    should_stop: Callable[[], bool] = lambda: False,
    now: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Optional[list[dict]], int]:
    """read_fn()을 반복해 모든 칸이 읽힌 결과를 반환합니다.

    시간 안에 다 읽히지 않으면 읽힌 칸이 가장 많았던 결과, 하나도 못 읽었거나
    should_stop()이 True가 되면 None. 반환: (결과 또는 None, 읽힌 칸 수)
    """
    deadline = now() + timeout
    best_results: Optional[list[dict]] = None
    best_ready = 0
    while True:
        if should_stop():
            return None, 0
        try:
            results = read_fn()
        except Exception as e:  # 게임 창을 못 찾는 등 일시적 오류는 재시도
            print(f"  캡처/OCR 실패 (재시도): {e}")
            results = []

        ready = sum(slot_ready(r, ready_score) for r in results)
        if ready > best_ready:
            best_results, best_ready = results, ready
        if results and ready == len(results):
            return results, ready
        if now() >= deadline:
            return best_results, best_ready
        sleep(interval)


def background_difference(reference: list[Image.Image], current: list[Image.Image]) -> float:
    """닉네임 칸들의 맨 윗줄/아랫줄(배경)만 비교한 평균 차이 (0~255).
    글자와 무관하게 닉네임 칸 UI가 그 자리에 있는지만 봅니다."""
    diffs = []
    for ref, cur in zip(reference, current):
        ref, cur = ref.convert("L"), cur.convert("L")
        if cur.size != ref.size:
            cur = cur.resize(ref.size)
        w, h = ref.size
        for y in (0, h - 1):
            row = (0, y, w, y + 1)
            diffs.append(ImageStat.Stat(ImageChops.difference(ref.crop(row), cur.crop(row))).mean[0])
    return sum(diffs) / len(diffs) if diffs else 255.0


class LobbyPresence:
    """닉네임 칸이 아직 화면에 있는지 추적합니다."""

    def __init__(
        self,
        reference: list[Image.Image],
        threshold: float = LOBBY_GONE_DIFF,
        consecutive: int = LOBBY_GONE_CONSECUTIVE,
    ):
        self.reference = reference
        self.threshold = threshold
        self.consecutive = consecutive
        self.misses = 0
        self.last_diff: Optional[float] = None

    def update(self, current: Optional[list[Image.Image]]) -> bool:
        """현재 크롭을 넣으면 게임이 시작됐다고 판단될 때 True. None(창 없음)은 '사라짐'."""
        if current is None:
            self.last_diff, gone = None, True
        else:
            self.last_diff = background_difference(self.reference, current)
            gone = self.last_diff > self.threshold
        self.misses = self.misses + 1 if gone else 0
        return self.misses >= self.consecutive
