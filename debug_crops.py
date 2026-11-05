"""
게임 화면 캡처(스크린샷 또는 debug/match*_end.png)에서 팀원 닉네임 칸만
원본 해상도로 잘라 저장하고, OCR 결과를 출력하는 디버그 도구.

사용법: python debug_crops.py debug/match1_end.png
결과:  debug/crops/<파일이름>_teammate_1.png ... (원본 크기)
       debug/crops/<파일이름>_teammate_1_x4.png ... (눈으로 보기 쉽게 4배 확대)

채팅 등에 붙여 넣으면 큰 스크린샷은 축소되지만, 이 작은 크롭 이미지는
대부분 원본 그대로 전달되므로 OCR 개선용 자료로 쓰기 좋습니다.
"""

import os
import sys

from PIL import Image

from teammate_ocr import NAME_REGIONS_REF, crops_from_image, ocr_crops


def main():
    if len(sys.argv) < 2:
        print("사용법: python debug_crops.py <스크린샷 경로>")
        return

    image_path = sys.argv[1]
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug", "crops")
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(image_path))[0]

    # debug/match*.png에는 빨간 박스가 영역 바깥에 그려져 있어서, 미세 보정
    # (위아래로 넓게 캡처) 없이 정확히 계산된 위치만 자릅니다.
    crops = crops_from_image(image_path, refine=False)
    for region, crop in zip(NAME_REGIONS_REF, crops):
        base = os.path.join(out_dir, f"{stem}_{region['name']}")
        crop.save(base + ".png")
        crop.resize((crop.width * 4, crop.height * 4), Image.NEAREST).save(base + "_x4.png")
        print(f"저장: {base}.png ({crop.width}x{crop.height})")

    print("\nOCR 결과:")
    for r in ocr_crops(crops):
        print(f"  {r['name']}: {r['best']!r} (점수 {r['confidence']})  후보: {r['candidates'][:6]}")


if __name__ == "__main__":
    main()
