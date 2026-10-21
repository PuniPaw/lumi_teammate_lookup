"""
이터널 리턴 팀원 전적 오버레이 - 이미지 테스트 모드

저장된 스크린샷 파일을 사용하여 게임을 실행하지 않고
OCR → API 검증 → 오버레이 표시까지 전체 파이프라인을 테스트합니다.

실행: python main_test_image.py
"""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from bserpy import Client

from teammate_ocr import get_teammate_ocr_results_from_image
from resolve_teammates import resolve_teammate_names

# .env 파일에서 API 키 로드
load_dotenv()
API_KEY = os.getenv("ETERNAL_RETURN_API_KEY")

# 스크린샷 파일 경로 (기본값: 프로젝트 루트의 matching_lobby_screen.png)
# 여러 이미지를 테스트하려면 SCREENSHOT_FILES 리스트를 수정하세요.
DEFAULT_SCREENSHOT = "matching_lobby_screen.png"
SCREENSHOT_FILES = [
    "matching_lobby_screen.png",  # 기본 테스트 이미지
    "test2.png",   # 추가로 테스트할 이미지
    "test3.png", 
    "test4.png",
]


def find_screenshot_files():
    """스크린샷 파일을 찾습니다. 존재하는 파일만 리스트로 반환합니다."""
    available_files = []
    
    # 지정된 파일들 확인
    for file_path in SCREENSHOT_FILES:
        if os.path.exists(file_path):
            available_files.append(file_path)
    
    # 만약 지정된 파일이 없으면, png 파일을 자동으로 찾기
    if not available_files:
        print("🔍 지정된 스크린샷 파일을 찾지 못해 .png 파일을 검색합니다...")
        png_files = list(Path(".").glob("*.png"))
        available_files = [str(f) for f in png_files if "debug" not in str(f).lower() and f.stem != "screenshot"]
    
    return available_files


def run_overlay_with_nicknames(nicknames):
    """찾은 닉네임들로 오버레이를 실행합니다."""
    if not nicknames:
        print("❌ 표시할 닉네임이 없습니다.")
        return
    
    print(f"\n🖥️ 오버레이 실행 중... 닉네임: {nicknames}")
    
    # 닉네임을 쉼표로 구분하여 전달
    nicknames_str = ",".join(nicknames)
    
    # overlay_demo.py 실행
    try:
        subprocess.Popen([sys.executable, "overlay_demo.py", nicknames_str])
        print("✅ 오버레이가 실행되었습니다.")
    except Exception as e:
        print(f"❌ 오버레이 실행 실패: {e}")


def process_image_screenshot(screenshot_path: str, show_overlay: bool = True):
    """이미지 파일 하나에 대해 전체 파이프라인을 실행합니다."""
    print(f"\n{'='*60}")
    print(f"📸 이미지 테스트: {screenshot_path}")
    print(f"{'='*60}")
    
    # 파일 존재 확인
    if not os.path.exists(screenshot_path):
        print(f"❌ 파일을 찾을 수 없습니다: {screenshot_path}")
        return None
    
    # 1. OCR 실행
    print("\n🔍 OCR 처리 중...")
    try:
        ocr_results = get_teammate_ocr_results_from_image(
            screenshot_path, 
            save_debug_images=True  # 디버그 이미지 저장
        )
    except Exception as e:
        print(f"❌ OCR 처리 실패: {e}")
        return None
    
    print("\n📊 OCR 결과:")
    for r in ocr_results:
        print(f"  {r['name']}: best={r['best']!r}")
        if len(r['variants']) > 1:
            print(f"    후보들: {r['variants']}")
    
    # 2. API 검증 (API 키가 있는 경우)
    resolved_results = None
    if API_KEY:
        print("\n🌐 API로 닉네임 검증 중...")
        try:
            with Client(api_key=API_KEY) as client:
                resolved_results = resolve_teammate_names(client, ocr_results)
            
            print("✅ 확정된 팀원 정보:")
            resolved_nicknames = []
            for r in resolved_results:
                if r["resolved_nickname"]:
                    print(f"  {r['region_name']}: '{r['resolved_nickname']}' (user_id={r['user_id']})")
                    resolved_nicknames.append(r["resolved_nickname"])
                else:
                    print(f"  {r['region_name']}: ❌ 인식 실패")
                    print(f"    시도한 후보: {r['tried_candidates']}")
            
            # 오버레이 실행 (찾은 닉네임 전달)
            if show_overlay and resolved_nicknames:
                run_overlay_with_nicknames(resolved_nicknames)
            
        except Exception as e:
            print(f"⚠️ API 검증 실패: {e}")
            print("  OCR 결과만 사용합니다.")
            
            # API 검증 실패 시에도 OCR 결과로 오버레이 실행
            if show_overlay:
                ocr_nicknames = [r["best"] for r in ocr_results if r["best"]]
                if ocr_nicknames:
                    run_overlay_with_nicknames(ocr_nicknames)
    else:
        print("\n⚠️ API 키가 없으므로 OCR 결과만 사용합니다.")
        print("  .env 파일에 ETERNAL_RETURN_API_KEY를 설정하면 닉네임 검증이 가능합니다.")
        
        # API 키가 없어도 OCR 결과로 오버레이 실행
        if show_overlay:
            ocr_nicknames = [r["best"] for r in ocr_results if r["best"]]
            if ocr_nicknames:
                run_overlay_with_nicknames(ocr_nicknames)
    
    return {
        "ocr_results": ocr_results,
        "resolved_results": resolved_results,
        "screenshot_path": screenshot_path
    }


def main():
    print("=" * 60)
    print("이터널 리턴 팀원 전적 오버레이 - 이미지 테스트 모드")
    print("=" * 60)
    
    # API 키 확인
    if not API_KEY:
        print("⚠️ ETERNAL_RETURN_API_KEY가 설정되지 않았습니다.")
        print("  .env 파일을 확인하세요. (닉네임 검증이 비활성화됩니다)")
    
    # 사용 가능한 스크린샷 파일 찾기
    screenshot_files = find_screenshot_files()
    
    if not screenshot_files:
        print("❌ 테스트할 스크린샷 파일을 찾을 수 없습니다.")
        print("  다음과 같이 이미지를 준비하세요:")
        print("  1. 게임 로비 화면을 캡처하여 저장")
        print("  2. 파일명을 'matching_lobby_screen.png'로 변경")
        print("  3. 이 스크립트와 같은 폴더에 배치")
        return
    
    print(f"\n찾은 스크린샷 파일 ({len(screenshot_files)}개):")
    for i, f in enumerate(screenshot_files):
        print(f"  [{i+1}] {f}")
    
    # 사용자 선택
    while True:
        print("\n테스트할 이미지를 선택하세요:")
        print("  - 이미지 번호 입력 (예: 1)")
        print("  - 'all' 입력 (모든 이미지 테스트)")
        print("  - 'quit' 입력 (종료)")
        
        choice = input("선택: ").strip().lower()
        
        if choice == "quit":
            break
        elif choice == "all":
            print("\n🔄 모든 이미지 테스트를 시작합니다...")
            for screenshot_path in screenshot_files:
                process_image_screenshot(screenshot_path)
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(screenshot_files):
                screenshot_path = screenshot_files[idx]
                process_image_screenshot(screenshot_path)
            else:
                print(f"❌ {choice}번 이미지는 존재하지 않습니다.")
        else:
            print("❌ 올바른 입력이 아닙니다. '1', 'all', 'quit' 중에서 입력하세요.")
    
    print("\n✅ 테스트 완료!")
    print("디버그 이미지(debug_crop_*.png, debug_processed_*.png)를 확인해보세요.")


if __name__ == "__main__":
    main()