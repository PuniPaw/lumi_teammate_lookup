"""
디버그 이미지 저장 (닉네임 인식 문제 분석용). 기본은 꺼져 있습니다.

켜기: .env에 LUMI_DEBUG=1
- 매 판 닉네임 칸 이미지:              debug/<시각>_teammate_<k>.png
- 인식/확정에 실패한 판의 게임 화면:   debug/<시각>_screen.png  (수 MB)
- 최근 KEEP_MATCHES판만 남기고 자동 삭제 (debug/ 하위 폴더는 건드리지 않음)
"""

import os
import time
from typing import Callable, Optional

from dotenv import load_dotenv

load_dotenv()
ENABLED = os.getenv("LUMI_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
KEEP_MATCHES = 20


def new_match_prefix() -> str:
    """매칭 하나의 파일 이름 앞부분 (예: '20261105-101434')."""
    return time.strftime("%Y%m%d-%H%M%S")


def save_crops(prefix: str, results: list[dict]) -> None:
    if not ENABLED or not results:
        return
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        for r in results:
            if r.get("crop_image") is not None:
                r["crop_image"].save(os.path.join(DEBUG_DIR, f"{prefix}_{r['name']}.png"))
    except Exception as e:
        print(f"  [디버그] 닉네임 칸 저장 실패: {e}")


def save_screen(prefix: str, capture_fn: Callable) -> Optional[str]:
    """capture_fn() -> (이미지, 창 정보)로 게임 화면을 저장. 저장 경로 반환."""
    if not ENABLED:
        return None
    try:
        img, window = capture_fn()
        os.makedirs(DEBUG_DIR, exist_ok=True)
        path = os.path.join(DEBUG_DIR, f"{prefix}_screen.png")
        img.save(path)
        print(f"  [디버그] 게임 화면 {window['width']}x{window['height']} -> {path}")
        return path
    except Exception as e:
        print(f"  [디버그] 화면 캡처 실패: {e}")
        return None


def cleanup(keep: int = KEEP_MATCHES) -> int:
    """최근 keep판의 파일만 남기고 삭제. 지운 파일 수 반환."""
    if not ENABLED or not os.path.isdir(DEBUG_DIR):
        return 0
    groups: dict[str, list[str]] = {}
    for name in os.listdir(DEBUG_DIR):
        path = os.path.join(DEBUG_DIR, name)
        if os.path.isfile(path) and name.endswith(".png"):
            groups.setdefault(name.split("_", 1)[0], []).append(path)

    removed = 0
    # 앞부분이 시각이라 문자열 정렬 = 시간순. 시각 형식이 아닌 예전 파일은 먼저 지워짐
    for prefix in sorted(groups, key=lambda p: (p[:1].isdigit(), p))[: -keep or None]:
        for path in groups[prefix]:
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    return removed
