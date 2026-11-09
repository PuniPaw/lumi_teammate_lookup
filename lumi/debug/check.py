"""
스크린샷(또는 지금 게임 화면)으로 OCR + API 닉네임 확정까지 확인합니다.

사용법: python -m lumi.debug.check <스크린샷>     (생략하면 지금 게임 화면)
"""

import sys

from lumi.api.client import MISSING_API_MESSAGE, client_factory
from lumi.api.resolve import resolve_teammate_names
from lumi.capture.screen import ImageScreen, LiveScreen
from lumi.config import load_settings
from lumi.ocr.paddle import PaddleReader


def main() -> None:
    settings = load_settings()
    make_client = client_factory(settings)
    if make_client is None:
        print(MISSING_API_MESSAGE)
        return

    screen = ImageScreen(sys.argv[1]) if len(sys.argv) > 1 else LiveScreen(settings.game_window_title)
    ocr_results = PaddleReader().read(screen.name_crops())

    print("--- OCR 결과 ---")
    for r in ocr_results:
        print(f"{r['name']}: {r['best']!r} (점수 {r['confidence']})  후보: {r['candidates'][:6]}")

    with make_client() as client:
        resolved = resolve_teammate_names(client, ocr_results)

    print("\n--- 확정 결과 ---")
    for r in resolved:
        name = repr(r["resolved_nickname"]) if r["resolved_nickname"] else "못 찾음"
        print(f"{r['region_name']}: {name}  [조회한 후보: {r['tried_candidates']}]")


if __name__ == "__main__":
    main()
