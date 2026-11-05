"""
매칭별 디버그 이미지 저장/정리 (닉네임 인식 개선용 자료).

- 닉네임 칸 이미지(작음): 매 판 저장  -> debug/<시각>_teammate_<k>.png
- 게임 화면 전체 캡처(큼, 수 MB): 인식/확정에 실패한 판에서만 저장
                                   -> debug/<시각>_screen.png
- 최근 KEEP_MATCHES판 것만 남기고 오래된 파일은 자동 삭제
  (debug/ 아래 하위 폴더, 예: debug_crops.py가 쓰는 debug/crops/는 건드리지 않음)
"""

import os
import time
from typing import Optional

DEBUG_DIR: Optional[str] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")

# 최근 몇 판의 디버그 이미지를 남길지
KEEP_MATCHES = 20


def new_match_prefix() -> str:
    """매칭 하나를 구분하는 파일 이름 앞부분 (예: '20261105-101434').
    실행할 때마다 1부터 세는 번호와 달리, 이전 실행의 파일을 덮어쓰지 않음."""
    return time.strftime("%Y%m%d-%H%M%S")


def save_crops(prefix: str, results: list[dict]) -> None:
    """OCR에 쓴 닉네임 칸 이미지를 원본 크기로 저장합니다."""
    if not DEBUG_DIR or not results:
        return
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        for r in results:
            crop = r.get("crop_image")
            if crop is not None:
                crop.save(os.path.join(DEBUG_DIR, f"{prefix}_{r['name']}.png"))
    except Exception as e:
        print(f"  [디버그] 닉네임 칸 저장 실패: {e}")


def save_screen(prefix: str, capture_fn) -> Optional[str]:
    """게임 화면 전체 캡처(닉네임 영역 빨간 박스 표시)를 저장합니다.
    capture_fn() -> (이미지, 창 정보). 저장한 경로를 반환."""
    if not DEBUG_DIR:
        return None
    try:
        img, window = capture_fn()
        os.makedirs(DEBUG_DIR, exist_ok=True)
        path = os.path.join(DEBUG_DIR, f"{prefix}_screen.png")
        img.save(path)
        print(
            f"  [디버그] 창 '{window.get('title', '')}' 위치=({window['left']},{window['top']}) "
            f"크기={window['width']}x{window['height']} -> {path}"
        )
        if not window.get("active", True):
            print("  ⚠️ 게임 창이 맨 앞에 있지 않습니다. 다른 창이 게임을 가리면 그 창을 읽게 됩니다.")
        return path
    except Exception as e:
        print(f"  [디버그] 화면 캡처 실패: {e}")
        return None


def cleanup(keep: int = KEEP_MATCHES) -> int:
    """최근 keep판의 파일만 남기고 지웁니다. 지운 파일 수를 반환."""
    if not DEBUG_DIR or not os.path.isdir(DEBUG_DIR):
        return 0
    groups: dict[str, list[str]] = {}
    for name in os.listdir(DEBUG_DIR):
        path = os.path.join(DEBUG_DIR, name)
        if not os.path.isfile(path) or not name.endswith(".png"):
            continue
        groups.setdefault(name.split("_", 1)[0], []).append(path)

    removed = 0
    # 파일 이름 앞부분이 시각(YYYYmmdd-HHMMSS)이라 문자열 정렬 = 시간순.
    # 예전 형식(match1_...)은 시각보다 앞으로 정렬되어 먼저 지워짐.
    for prefix in sorted(groups, key=lambda p: (p[:1].isdigit(), p))[:-keep or None]:
        for path in groups[prefix]:
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    return removed
