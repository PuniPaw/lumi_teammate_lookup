"""
디버그 이미지 저장 (닉네임 인식 문제 분석용). 설정 LUMI_DEBUG=1일 때만 동작.

- 매 판 닉네임 칸 이미지:              debug/<시각>_teammate_<k>.png
- 인식/확정에 실패한 판의 게임 화면:   debug/<시각>_screen.png  (수 MB)
- 최근 keep판만 남기고 자동 삭제 (debug/ 하위 폴더는 건드리지 않음)
"""

import os
import time
from typing import Callable, Optional

KEEP_MATCHES = 20


class DebugStore:
    def __init__(self, enabled: bool, directory: str, keep: int = KEEP_MATCHES):
        self.enabled = enabled
        self.directory = directory
        self.keep = keep

    @staticmethod
    def new_match_prefix() -> str:
        """매칭 하나의 파일 이름 앞부분 (예: '20261105-101434')."""
        return time.strftime("%Y%m%d-%H%M%S")

    def save_crops(self, prefix: str, results: list[dict]) -> None:
        if not self.enabled or not results:
            return
        try:
            os.makedirs(self.directory, exist_ok=True)
            for r in results:
                if r.get("crop_image") is not None:
                    r["crop_image"].save(os.path.join(self.directory, f"{prefix}_{r['name']}.png"))
        except Exception as e:
            print(f"  [디버그] 닉네임 칸 저장 실패: {e}")

    def save_screen(self, prefix: str, capture_fn: Callable) -> Optional[str]:
        """capture_fn() -> (이미지, 창 정보)로 게임 화면을 저장. 저장 경로 반환."""
        if not self.enabled:
            return None
        try:
            img, window = capture_fn()
            os.makedirs(self.directory, exist_ok=True)
            path = os.path.join(self.directory, f"{prefix}_screen.png")
            img.save(path)
            print(f"  [디버그] 게임 화면 {window['width']}x{window['height']} -> {path}")
            return path
        except Exception as e:
            print(f"  [디버그] 화면 캡처 실패: {e}")
            return None

    def cleanup(self) -> int:
        """최근 keep판의 파일만 남기고 삭제. 지운 파일 수 반환."""
        if not self.enabled or not os.path.isdir(self.directory):
            return 0
        groups: dict[str, list[str]] = {}
        for name in os.listdir(self.directory):
            path = os.path.join(self.directory, name)
            if os.path.isfile(path) and name.endswith(".png"):
                groups.setdefault(name.split("_", 1)[0], []).append(path)

        removed = 0
        # 앞부분이 시각이라 문자열 정렬 = 시간순. 시각 형식이 아닌 예전 파일은 먼저 지워짐
        for prefix in sorted(groups, key=lambda p: (p[:1].isdigit(), p))[: -self.keep or None]:
            for path in groups[prefix]:
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass
        return removed
