"""
닉네임 칸 이미지들 -> 칸별 OCR 결과 (ports.NicknameReader).

여러 배율/전처리(OCR_PASSES) x 언어팩(OCR_LANGS)으로 OCR하되, 빠른 1단계에서
확실하면 바로 확정하고 빈 칸은 OCR을 생략합니다.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from PIL import Image

from lumi.capture.screen import NAME_REGIONS_REF
from lumi.ocr import engine
from lumi.ocr.candidates import empty_result, rank_candidates
from lumi.ocr.chars import OCR_LANGS

# (확대 배율, 전처리). 글자마다 잘 읽히는 배율이 달라 여러 개를 씀
OCR_PASSES = [(3, "soft"), (6, "soft"), (6, "binary")]
# 위 배율의 기준 칸 높이(px): 1920x1080의 칸 14px + 미세 보정 여유 위아래 1px.
# 칸이 더 크면(고해상도) 같은 글자 크기가 되도록 배율을 줄임.
OCR_REFERENCE_CROP_HEIGHT = 16

# 1단계: 이 조합만 먼저 돌려 FAST_ACCEPT_SCORE 이상이면 바로 확정
FAST_PASS = (3, "soft")
FAST_LANGS = ["eng", "kor", "jpn"]
FAST_ACCEPT_SCORE = 90

# 흰 글씨 픽셀 비율이 이보다 작으면 빈 칸으로 보고 OCR 생략 (닉네임 칸 0.10~0.33, 빈 칸 0~0.03)
MIN_TEXT_PIXEL_RATIO = 0.05


def read_crop(crop: Image.Image) -> dict:
    """닉네임 칸 하나의 OCR 결과 (candidates.rank_candidates 형식)."""
    crop = engine.trim_edge_columns(crop)
    if engine.text_pixel_ratio(crop) < MIN_TEXT_PIXEL_RATIO:
        return empty_result()

    size_factor = OCR_REFERENCE_CROP_HEIGHT / max(1, crop.height)
    effective = {p: p[0] * size_factor for p in OCR_PASSES}
    images = {p: engine.preprocess(crop, effective[p], p[1]) for p in OCR_PASSES}

    def run(jobs: list[tuple]) -> dict:
        words_by_pass: dict = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [(p, pool.submit(engine.ocr_words, images[p], lang, effective[p])) for p, lang in jobs]
            for p, fut in futures:
                words_by_pass.setdefault(p, []).extend(fut.result())
        return words_by_pass

    fast_jobs = [(FAST_PASS, lang) for lang in FAST_LANGS]
    fast_words = run(fast_jobs)
    fast = rank_candidates(fast_words)
    if fast["best"] and fast["candidate_scores"][fast["best"]] >= FAST_ACCEPT_SCORE:
        return fast

    words_by_pass = run([(p, lang) for p in OCR_PASSES for lang in OCR_LANGS if (p, lang) not in fast_jobs])
    for p, words in fast_words.items():
        words_by_pass.setdefault(p, []).extend(words)
    return rank_candidates(words_by_pass)


class TesseractReader:
    """ports.NicknameReader 구현."""

    def __init__(self, tesseract_cmd: Optional[str] = None):
        engine.set_tesseract_cmd(tesseract_cmd)

    def read(self, crops: list[Image.Image]) -> list[dict]:
        return [
            {"name": region["name"], **read_crop(crop), "crop_image": crop}
            for region, crop in zip(NAME_REGIONS_REF, crops)
        ]
