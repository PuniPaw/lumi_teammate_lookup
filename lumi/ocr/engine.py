"""Tesseract 실행과 전처리: 닉네임 칸 이미지 -> 단어 목록."""

import os
from typing import Optional

import pytesseract
from PIL import Image, ImageOps

from lumi.ocr.chars import LANG_CHAR_FILTERS, LATIN_CONF_PENALTY, LATIN_TRUSTED_LANGS, is_latin

# OCR을 병렬로 돌리므로 Tesseract 내부 멀티스레딩은 끔 (켜 두면 CPU 경쟁으로 크게 느려짐)
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

PAD = 30  # 전처리 시 붙이는 흰 여백(px)


def set_tesseract_cmd(cmd: Optional[str]) -> None:
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def trim_edge_columns(img: Image.Image) -> Image.Image:
    """좌우 끝의 밝은 세로 테두리 제거 ('|' 잡음 방지).

    닉네임 배경은 어두워 글자가 있는 열도 위/아래 끝은 어둡지만, 테두리는 열 전체가 밝음.
    """
    gray = img.convert("L")
    w, h = gray.size
    px = gray.load()

    def is_border(x: int) -> bool:
        return min(px[x, y] for y in range(h)) > 70

    left, right = 0, w
    while right - left > 1 and is_border(right - 1):
        right -= 1
    while right - left > 1 and is_border(left):
        left += 1
    return img if (left, right) == (0, w) else img.crop((left, 0, right, h))


def text_pixel_ratio(img: Image.Image) -> float:
    """배경(중앙값)보다 80 이상 밝은 픽셀 비율 = 흰 글씨가 차지하는 비율."""
    hist = img.convert("L").histogram()
    total = sum(hist)
    if total == 0:
        return 0.0
    acc = median = 0
    for value, count in enumerate(hist):
        acc += count
        if acc * 2 >= total:
            median = value
            break
    return sum(hist[median + 81 :]) / total


def preprocess(img: Image.Image, scale: float, mode: str) -> Image.Image:
    """흰 글씨/어두운 배경 -> 검은 글씨/흰 배경, 확대, 흰 여백 추가.

    soft: 부드러운 반전 + 자동 대비 (얇은 한글 획 보존), binary: 이진화.
    """
    gray = img.convert("L")
    gray = gray.resize((max(1, round(gray.width * scale)), max(1, round(gray.height * scale))), Image.LANCZOS)
    gray = ImageOps.autocontrast(ImageOps.invert(gray), cutoff=1)
    if mode == "binary":
        gray = gray.point(lambda v: 255 if v > 140 else 0)
    return ImageOps.expand(gray, border=PAD, fill=255)


def ocr_words(img: Image.Image, lang: str, scale: float) -> list[dict]:
    """한 이미지 x 한 언어팩의 단어 목록.

    단어: {"raw", "text"(언어팩이 신뢰하는 글자만), "conf", "x0", "x1"(원본 크롭 기준 px), "lang"}
    """
    data = pytesseract.image_to_data(img, lang=lang, config="--psm 7", output_type=pytesseract.Output.DICT)
    char_ok = LANG_CHAR_FILTERS[lang]
    words = []
    for raw, conf, left, width in zip(data["text"], data["conf"], data["left"], data["width"]):
        raw, conf = raw.strip(), float(conf)
        if not raw or conf < 0:
            continue
        text = "".join(ch for ch in raw if char_ok(ch))
        if lang in LATIN_TRUSTED_LANGS and all(is_latin(ch) for ch in raw):
            text, conf = raw, conf * LATIN_CONF_PENALTY
        words.append(
            {
                "raw": raw,
                "text": text,
                "conf": conf,
                "x0": (left - PAD) / scale,
                "x1": (left + width - PAD) / scale,
                "lang": lang,
            }
        )

    # Tesseract가 첫 단어 박스를 줄 끝까지 잡는 경우가 있어 다음 단어 시작에서 자름
    words.sort(key=lambda w: w["x0"])
    for cur, nxt in zip(words, words[1:]):
        cur["x1"] = max(cur["x0"], min(cur["x1"], nxt["x0"]))
    return words
