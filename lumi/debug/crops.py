"""
스크린샷에서 닉네임 칸을 원본 해상도로 잘라 저장하고 OCR 결과를 출력합니다.

사용법: python -m lumi.debug.crops <스크린샷>
결과:  debug/crops/<파일명>_teammate_<k>.png (원본), ..._x4.png (4배 확대)
"""

import os
import sys

from PIL import Image

from lumi.capture.screen import NAME_REGIONS_REF, ImageScreen
from lumi.config import load_settings
from lumi.ocr import make_reader


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python -m lumi.debug.crops <스크린샷>")
        return

    settings = load_settings()
    image_path = sys.argv[1]
    out_dir = os.path.join(settings.debug_dir, "crops")
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(image_path))[0]

    # 디버그 화면 캡처에는 빨간 박스가 칸 바깥에 그려져 있어 미세 보정 없이 자름
    crops = ImageScreen(image_path).name_crops(refine=False)
    for region, crop in zip(NAME_REGIONS_REF, crops):
        base = os.path.join(out_dir, f"{stem}_{region['name']}")
        crop.save(base + ".png")
        crop.resize((crop.width * 4, crop.height * 4), Image.NEAREST).save(base + "_x4.png")
        print(f"저장: {base}.png ({crop.width}x{crop.height})")

    print("\nOCR 결과:")
    for r in make_reader(settings).read(crops):
        print(f"  {r['name']}: {r['best']!r} (점수 {r['confidence']})  후보: {r['candidates'][:6]}")


if __name__ == "__main__":
    main()
