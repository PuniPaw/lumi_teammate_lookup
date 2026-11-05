"""
매칭 완료 ~ 게임 시작 사이의 흐름 판단 로직 (Qt/게임 없이 테스트 가능하도록 분리).

1) wait_for_teammates(): 매칭 완료 직후엔 닉네임이 아직 화면에 안 그려졌을
   수 있어서, 일정 시간 동안 캡처+OCR을 반복하다가 모든 칸이 충분히
   '읽힌' 상태가 되면 결과를 확정합니다.
2) LobbyPresence: 확정 당시의 닉네임 칸 이미지를 기준으로 기억해 두고,
   이후 같은 위치를 주기적으로 캡처해 비교합니다. 닉네임 칸이 사라진
   상태(로딩 화면/인게임)가 일정 횟수 연속되면 '게임 시작'으로 판단합니다.
"""

import time
from typing import Callable, Optional

from PIL import Image, ImageChops, ImageStat

# ---------------------------------------------------------------------------
# 1) 닉네임 확정 (재시도)
# ---------------------------------------------------------------------------

# 매칭 완료 후 닉네임이 다 읽힐 때까지 최대 몇 초 재시도할지
OCR_RETRY_TIMEOUT_SECONDS = 15.0

# 재시도 간격(초). OCR 한 번에 1~2초 걸리므로 실제 간격은 이보다 깁니다.
OCR_RETRY_INTERVAL_SECONDS = 0.5

# 한 칸이 '읽혔다'고 볼 OCR 점수 (실제 닉네임은 대부분 80~100,
# 빈 칸/잡음은 대부분 70 미만)
SLOT_READY_SCORE = 75

# 닉네임 최소 길이 (한 글자는 대부분 잡음)
MIN_NICKNAME_LENGTH = 2


def slot_ready(result: dict, ready_score: float = SLOT_READY_SCORE) -> bool:
    """OCR 결과 한 칸이 닉네임을 확실히 읽은 상태인지."""
    scores = result.get("candidate_scores") or {}
    best = result.get("best") or ""
    return (
        len(best) >= MIN_NICKNAME_LENGTH
        and scores.get(best, result.get("confidence", 0)) >= ready_score
    )


def wait_for_teammates(
    read_fn: Callable[[], list[dict]],
    timeout: float = OCR_RETRY_TIMEOUT_SECONDS,
    interval: float = OCR_RETRY_INTERVAL_SECONDS,
    ready_score: float = SLOT_READY_SCORE,
    should_stop: Callable[[], bool] = lambda: False,
    now: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Optional[list[dict]], int]:
    """read_fn(캡처+OCR)을 반복 호출해서 닉네임이 다 읽힌 결과를 반환합니다.

    - 모든 칸이 준비되면 즉시 반환
    - timeout까지 안 되면, 그동안 '준비된 칸이 가장 많았던' 결과를 반환
      (일부라도 읽혔으면 그 칸만이라도 보여주기 위함)
    - 한 칸도 못 읽었으면 None
    - should_stop()이 True가 되면 (예: 새 매칭 감지) 바로 중단하고 None

    반환: (결과 또는 None, 준비된 칸 수)
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


# ---------------------------------------------------------------------------
# 2) 게임 시작 감지 (닉네임 칸이 화면에서 사라졌는지)
# ---------------------------------------------------------------------------

# 기준 이미지와 현재 화면의 '배경' 차이가 이 값을 넘으면 닉네임 칸이 사라진
# 것으로 봅니다. 저장된 스크린샷으로 측정한 값:
#   같은 매칭 화면 0, 다른 매칭 화면(닉네임 다름) 3~14,
#   로비가 아닌 화면 50~85
LOBBY_GONE_DIFF = 30

# 몇 번 연속으로 '사라짐'이 나와야 게임 시작으로 볼지 (일시적 화면 효과로
# 잘못 닫히는 것 방지). 1초 간격 확인이면 약 3초.
LOBBY_GONE_CONSECUTIVE = 3


def background_difference(reference: list[Image.Image], current: list[Image.Image]) -> float:
    """닉네임 칸들의 '배경'(맨 윗줄/아랫줄 픽셀)만 비교한 평균 차이(0~255).

    글자가 있는 가운데 줄은 비교하지 않아서, 닉네임 글자와 무관하게
    '닉네임 칸 UI가 그 자리에 그대로 있는지'만 봅니다.
    """
    diffs = []
    for ref, cur in zip(reference, current):
        ref = ref.convert("L")
        cur = cur.convert("L")
        if cur.size != ref.size:
            cur = cur.resize(ref.size)
        w, h = ref.size
        for y in (0, h - 1):
            row_ref = ref.crop((0, y, w, y + 1))
            row_cur = cur.crop((0, y, w, y + 1))
            diffs.append(ImageStat.Stat(ImageChops.difference(row_ref, row_cur)).mean[0])
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
        """현재 화면 크롭을 넣으면, 게임이 시작됐다고 판단될 때 True.

        current가 None이면 (게임 창을 못 찾는 등) '사라짐'으로 취급합니다.
        """
        if current is None:
            self.last_diff = None
            gone = True
        else:
            self.last_diff = background_difference(self.reference, current)
            gone = self.last_diff > self.threshold
        self.misses = self.misses + 1 if gone else 0
        return self.misses >= self.consecutive
