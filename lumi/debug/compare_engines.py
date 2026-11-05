"""
OCR 엔진 비교 실험: 현재 Tesseract 방식 vs PaddleOCR(PP-OCR) 인식 모델 (RapidOCR/ONNX).

준비 (프로젝트 가상환경에서):
  pip install rapidocr onnxruntime

실행:
  python -m lumi.debug.compare_engines              # 테스트 이미지(정답 있음)로 비교
  python -m lumi.debug.compare_engines debug        # + debug/ 폴더의 실게임 닉네임 칸도 읽기

처음 실행할 때 모델 파일(각 수~수십 MB)을 ModelScope에서 내려받습니다.
"""

import glob
import os
import sys
import time

import numpy as np
import psutil
from PIL import Image

from lumi.config import PROJECT_ROOT, load_settings
from lumi.ocr.reader import TesseractReader

sys.path.insert(0, os.path.join(PROJECT_ROOT, "tests"))
from conftest import fixture, name_crops  # noqa: E402
from test_ocr_images import EXPECTED  # noqa: E402

# (표시 이름, RapidOCR 설정)
PP_ENGINES = [
    ("v5-ch-server", {"lang": "CH", "version": "PPOCRV5", "type": "SERVER"}),  # 중국어+일본어+영문
    ("v5-ch-mobile", {"lang": "CH", "version": "PPOCRV5", "type": "MOBILE"}),
    ("v5-korean", {"lang": "KOREAN", "version": "PPOCRV5", "type": "MOBILE"}),
    ("v4-japan", {"lang": "JAPAN", "version": "PPOCRV4", "type": "MOBILE"}),
]
REC_HEIGHT = 48  # PP-OCR 인식 모델 입력 높이


def _mem_mb() -> float:
    return psutil.Process().memory_info().rss / 1024 / 1024


class PPEngine:
    def __init__(self, name: str, cfg: dict):
        from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

        self.name = name
        self.ocr = RapidOCR(
            params={
                "Global.use_det": False,
                "Global.use_cls": False,
                "Rec.lang_type": LangRec[cfg["lang"]],
                "Rec.ocr_version": OCRVersion[cfg["version"]],
                "Rec.model_type": ModelType[cfg["type"]],
            }
        )
        self.times: list[float] = []
        # 첫 호출 때 모델을 받고 로드하므로 여기서 미리 한 번 실행해 로딩 시간을 잼
        start = time.time()
        self.read(Image.new("RGB", (200, 20)))
        self.load_seconds = time.time() - start
        self.times.clear()

    def read(self, crop: Image.Image) -> tuple[str, float]:
        img = crop.convert("RGB")
        img = img.resize((max(1, round(img.width * REC_HEIGHT / img.height)), REC_HEIGHT), Image.LANCZOS)
        start = time.time()
        out = self.ocr(np.array(img), use_det=False, use_cls=False, use_rec=True)
        self.times.append(time.time() - start)
        if not out.txts:
            return "", 0.0
        return out.txts[0], round(float(out.scores[0]), 3)


def _samples():
    """(라벨, 정답 또는 None, 크롭 이미지)"""
    for image, names in EXPECTED.items():
        for idx, (expected, crop) in enumerate(zip(names, name_crops(image))):
            yield f"{image}[{idx}]", expected, crop
    yield "crop_2880x1800_fujita.png", "藤田皮卡丘", Image.open(fixture("crop_2880x1800_fujita.png")).convert("RGB")
    if len(sys.argv) > 1:
        for path in sorted(glob.glob(os.path.join(sys.argv[1], "*_teammate_*.png"))):
            yield os.path.basename(path), None, Image.open(path).convert("RGB")


def main() -> None:
    settings = load_settings()
    mem_start = _mem_mb()

    tess = TesseractReader(settings.tesseract_cmd)
    engines = []
    for name, cfg in PP_ENGINES:
        try:
            engines.append(PPEngine(name, cfg))
            print(f"[로드] {name}: {engines[-1].load_seconds:.1f}초 (다운로드 포함될 수 있음)")
        except Exception as e:
            print(f"[실패] {name}: {e!r}")
    mem_loaded = _mem_mb()

    names = ["tesseract"] + [e.name for e in engines] + ["pp-best"]
    correct = {n: 0 for n in names}
    labeled = 0
    tess_times = []

    for label, expected, crop in _samples():
        start = time.time()
        t = tess.read([crop])[0]
        tess_times.append(time.time() - start)
        row = {"tesseract": (t["best"], round(t["confidence"] / 100, 3))}
        for e in engines:
            row[e.name] = e.read(crop)
        pp = [row[e.name] for e in engines if row[e.name][0]]
        row["pp-best"] = max(pp, key=lambda r: r[1]) if pp else ("", 0.0)

        mark = ""
        if expected is not None:
            labeled += 1
            for n in names:
                correct[n] += row[n][0] == expected
            mark = f"정답={expected!r}"
        print(f"\n{label}  {mark}")
        for n in names:
            ok = "" if expected is None else (" ✅" if row[n][0] == expected else " ❌")
            print(f"    {n:14s} {row[n][0]!r:24} {row[n][1]:.3f}{ok}")

    def ms(ts):
        return sorted(ts)[len(ts) // 2] * 1000 if ts else 0

    print("\n===== 요약 (정답 있는 칸 %d개) =====" % labeled)
    for n in names:
        print(f"  {n:14s} 정답 {correct[n]:2d}/{labeled}")
    print("\n속도 (칸 1개, 중앙값)")
    print(f"  tesseract      {ms(tess_times):.0f} ms")
    for e in engines:
        print(f"  {e.name:14s} {ms(e.times):.0f} ms  (로드 {e.load_seconds:.1f}초)")
    print(f"\n메모리: 시작 {mem_start:.0f} MB -> PP 모델 {len(engines)}개 로드 후 {mem_loaded:.0f} MB -> 끝 {_mem_mb():.0f} MB")
    print("\n※ tesseract 점수는 0~100 점수를 100으로 나눈 값이라 PP-OCR 점수와 직접 비교할 수 없습니다.")


if __name__ == "__main__":
    main()
