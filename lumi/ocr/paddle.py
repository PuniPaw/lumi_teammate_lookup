"""
닉네임 칸 이미지들 -> 칸별 OCR 결과 (ports.NicknameReader), PaddleOCR(PP-OCRv5) 인식 모델 사용.

RapidOCR(ONNX)로 인식 모델 두 개를 돌리고 글자 종류로 결과를 고릅니다.
  - v5-korean: 한글 + 영문/숫자 (한자/가나는 빈 문자열이나 엉뚱한 글자)
  - v5-ch-mobile: 한자 + 가나 + 영문/숫자 (한글은 빈 문자열이나 엉뚱한 한자)
점수가 높은 쪽을 고르면 안 됨: 'ya발견'을 ch는 'ya'(0.91), korean은 'ya발견'(0.87)으로 읽음.

처음 실행할 때 모델 파일(합계 약 30MB)을 ModelScope에서 내려받습니다.
측정값과 근거는 docs/DEVELOPMENT_NOTES.md의 'PP-OCR' 절.
"""

import threading
from typing import Callable, Optional

import numpy as np
from PIL import Image

from lumi.capture.screen import NAME_REGIONS_REF
from lumi.ocr import engine
from lumi.ocr.candidates import empty_result, is_junk
from lumi.ocr.chars import is_cjk, is_hangul, is_kana

# (이름, RapidOCR 설정). 담당 문자: korean은 한글, ch는 한자/가나
MODELS = {
    "korean": {"lang": "KOREAN", "version": "PPOCRV5", "type": "MOBILE"},
    "ch": {"lang": "CH", "version": "PPOCRV5", "type": "MOBILE"},
}
REC_HEIGHT = 48  # PP-OCR 인식 모델 입력 높이

# 흰 글씨 픽셀 비율이 이보다 작으면 빈 칸으로 보고 OCR 생략. reader.py(0.05)보다 낮음:
# 2880x1800의 두 글자 닉네임 '르채'가 0.046 (빈 칸 최대 0.036). PP-OCR은 빨라서 생략할 이유가
# 적고, 빈 칸을 읽어도 점수가 35 미만이라 '읽힌 칸'(75점)이나 API 조회(60점)가 되지 않음
MIN_TEXT_PIXEL_RATIO = 0.02

# 담당 문자가 아닌 쪽 모델의 결과는 이만큼 깎아서 API 조회 범위(1등과 25점 이내) 밖으로
# ('ya발견' 칸에서 ch가 읽은 'ya'가 실존 유저와 일치하면 다른 사람이 확정됨)
OFF_SCRIPT_PENALTY = 30
# 보조 후보(잡음 글자 제거, 구분자 치환)는 원래 후보보다 이만큼 낮게
ALT_PENALTY = 10
# 두 모델이 같은 글자를 읽으면 보너스 (Tesseract 쪽 '여러 패스 일치' 보너스와 같은 값)
AGREE_BONUS = 2

# 글자 옆에 붙어 나오는 세로선 잡음 ('1얼음마녀'), 한자 닉네임의 구분자 '丨'를 읽은 글자 ('静戒IBS')
STROKE_LIKE = set("1Il|丨")

RecognizeFn = Callable[[Image.Image], tuple[str, float]]


def _is_wide(ch: str) -> bool:
    return is_hangul(ch) or is_cjk(ch) or is_kana(ch)


def clean(text: str) -> str:
    """닉네임에는 공백이 없음. 앞뒤 공백과 '.' 잡음 제거 (' PuniPaw', '....PuniPaw')."""
    return "".join(text.split()).strip(".·,")


def _alternatives(text: str) -> list[str]:
    """보조 후보: 넓은 글자(한글/한자/가나) 옆 끝의 세로선 잡음 제거, 한자 옆 세로선을 '丨'로."""
    alts = []
    if len(text) >= 3 and text[0] in STROKE_LIKE and _is_wide(text[1]):
        alts.append(text[1:])
    if len(text) >= 3 and text[-1] in STROKE_LIKE and _is_wide(text[-2]):
        alts.append(text[:-1])
    chars = list(text)
    for i in range(1, len(chars) - 1):
        if chars[i] in STROKE_LIKE and chars[i] != "丨" and (is_cjk(chars[i - 1]) or is_cjk(chars[i + 1])):
            chars[i] = "丨"
    if "".join(chars) != text:
        alts.append("".join(chars))
    return alts


def combine(korean: tuple[str, float], ch: tuple[str, float]) -> dict:
    """두 모델의 (글자, 0~1 점수)로 candidates.rank_candidates와 같은 형식의 결과를 만듭니다."""
    reads = {"korean": (clean(korean[0]), korean[1] * 100), "ch": (clean(ch[0]), ch[1] * 100)}
    has_hangul = any(is_hangul(c) for c in reads["korean"][0])
    has_cjk = any(is_cjk(c) or is_kana(c) for c in reads["ch"][0])
    # 담당 문자를 읽은 모델만 믿음. 둘 다(또는 둘 다 아님: 영문/숫자)면 점수로
    trusted = {"korean"} if has_hangul and not has_cjk else {"ch"} if has_cjk and not has_hangul else set(reads)

    scores: dict[str, float] = {}
    sources: dict[str, str] = {}
    for model, (text, score) in reads.items():
        if is_junk(text):
            continue
        if model not in trusted:
            score -= OFF_SCRIPT_PENALTY
        if text in scores:
            scores[text] = max(scores[text], score) + AGREE_BONUS
            sources[text] = "pp-both"
        else:
            scores[text], sources[text] = score, f"pp-{model}"

    for text in list(scores):
        for alt in _alternatives(text):
            if alt not in scores and not is_junk(alt):
                scores[alt], sources[alt] = scores[text] - ALT_PENALTY, sources[text] + "+alt"

    ranked = sorted(scores, key=lambda t: scores[t], reverse=True)
    if not ranked:
        return empty_result()
    best = ranked[0]
    return {
        "best": best,
        "best_source": sources[best],
        "confidence": round(max(0.0, min(100.0, scores[best])), 1),
        "candidates": ranked,
        "candidate_scores": {t: round(scores[t], 1) for t in ranked},
    }


def _load_model(cfg: dict) -> RecognizeFn:
    from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

    ocr = RapidOCR(
        params={
            "Global.use_det": False,
            "Global.use_cls": False,
            "Rec.lang_type": LangRec[cfg["lang"]],
            "Rec.ocr_version": OCRVersion[cfg["version"]],
            "Rec.model_type": ModelType[cfg["type"]],
        }
    )

    def recognize(img: Image.Image) -> tuple[str, float]:
        out = ocr(np.array(img), use_det=False, use_cls=False, use_rec=True)
        if not out.txts:
            return "", 0.0
        return out.txts[0], float(out.scores[0])

    # RapidOCR는 첫 호출 때 모델을 로드함 (약 0.6초씩). 매칭 중이 아니라 시작할 때 로드되도록
    recognize(Image.new("RGB", (200, REC_HEIGHT)))
    return recognize


def _prepare(crop: Image.Image) -> Image.Image:
    img = crop.convert("RGB")
    return img.resize((max(1, round(img.width * REC_HEIGHT / img.height)), REC_HEIGHT), Image.LANCZOS)


class PaddleReader:
    """ports.NicknameReader 구현. 모델은 만들 때 한 번 로드합니다 (약 1초, 처음엔 다운로드)."""

    def __init__(self, models: Optional[dict[str, RecognizeFn]] = None):
        self._models = models or {name: _load_model(cfg) for name, cfg in MODELS.items()}
        self._lock = threading.Lock()  # ONNX 세션을 여러 스레드에서 동시에 쓰지 않도록

    def read_crop(self, crop: Image.Image) -> dict:
        crop = engine.trim_edge_columns(crop)
        if engine.text_pixel_ratio(crop) < MIN_TEXT_PIXEL_RATIO:
            return empty_result()
        img = _prepare(crop)
        with self._lock:
            return combine(self._models["korean"](img), self._models["ch"](img))

    def read(self, crops: list[Image.Image]) -> list[dict]:
        return [
            {"name": region["name"], **self.read_crop(crop), "crop_image": crop}
            for region, crop in zip(NAME_REGIONS_REF, crops)
        ]
