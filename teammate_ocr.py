"""
화면 캡처 -> 팀원별 닉네임 영역 크롭 -> OCR -> 이름 리스트 반환

이 모듈은 다른 코드(오버레이 UI, Open API 조회 등)에서 그대로 가져다
쓸 수 있도록, 캡처/전처리/OCR 로직을 함수로 정리해둔 것입니다.
디버깅용으로 직접 실행하고 싶으면 capture_test.py를 쓰세요.
"""

import os
from concurrent.futures import ThreadPoolExecutor

import mss
import pytesseract
from PIL import Image, ImageOps

# ---------------------------------------------------------------------------
# Windows 기본 설치 경로에 Tesseract가 있으면 그걸 쓰고, 없으면 PATH의
# tesseract를 씁니다 (Linux/macOS 등). 설치 경로가 다르면 수정하세요.
#
# 다국어 닉네임 인식에는 아래 언어팩이 필요합니다:
#   eng, kor, jpn, chi_sim, chi_tra
# Windows 설치 프로그램에서는 'Additional language data'에서 Korean,
# Japanese, Chinese (Simplified/Traditional)을 체크하세요.
_WINDOWS_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(_WINDOWS_TESSERACT):
    pytesseract.pytesseract.tesseract_cmd = _WINDOWS_TESSERACT

# OCR을 여러 개 병렬로 돌리므로, Tesseract 내부 멀티스레딩(OpenMP)은 끕니다.
# (안 끄면 스레드끼리 CPU를 두고 경쟁해서 오히려 몇 배 느려짐)
os.environ.setdefault("OMP_THREAD_LIMIT", "1")
# ---------------------------------------------------------------------------

# 게임 창을 찾을 때 쓰는 제목(부분 일치). 실제 창 제목이 다르면 수정하세요.
GAME_WINDOW_TITLE_KEYWORD = "Eternal Return"

# 팀원별 닉네임 영역을, 절대 픽셀이 아니라 "게임 창 크기 대비 비율(0~1)"로
# 정의합니다. 이러면 모니터가 바뀌거나 해상도가 달라져도(같은 종횡비라면)
# 자동으로 올바른 위치를 계산할 수 있습니다.
# (실제 게임 창 크기 1920x1716 기준으로 측정한 절대좌표를 비율로 환산한 값.
#  주의: 이 게임 창은 16:9(1080)가 아니라 1716 높이임 - 하단에 채팅/번역
#  패널이 포함된 크기로 보임)
CROP_REGIONS_PCT = [
    {"name": "teammate_1", "left": 0.5625, "top": 0.5449, "width": 0.0703, "height": 0.0087},
    {"name": "teammate_2", "left": 0.7109, "top": 0.5449, "width": 0.0703, "height": 0.0087},
    {"name": "teammate_3", "left": 0.8672, "top": 0.5449, "width": 0.0625, "height": 0.0087},
]


def _get_game_window_rect() -> dict:
    """이터널 리턴 창을 찾아서 (left, top, width, height)를 반환합니다.

    창을 못 찾으면 예외를 던집니다 - 게임이 켜져 있지 않거나,
    GAME_WINDOW_TITLE_KEYWORD가 실제 창 제목과 안 맞는 경우입니다.
    """
    # pygetwindow는 Windows 전용이라 실제 캡처할 때만 import 합니다
    # (스크린샷 파일 테스트는 다른 OS에서도 돌 수 있도록).
    import pygetwindow as gw

    windows = gw.getWindowsWithTitle(GAME_WINDOW_TITLE_KEYWORD)
    if not windows:
        raise RuntimeError(
            f"'{GAME_WINDOW_TITLE_KEYWORD}' 제목을 가진 창을 찾을 수 없습니다."
            "\n게임이 켜져 있는지, GAME_WINDOW_TITLE_KEYWORD가 실제 창 제목과"
            "\n맞는지 확인하세요 (작업 관리자 -> 세부 정보에서 확인 가능)."
        )
    # 같은 단어가 들어간 다른 창(브라우저 탭, 폴더 등)이 있을 수 있어서,
    # 최소화되지 않은 창 중 가장 큰 창을 게임 창으로 봅니다.
    visible = [w for w in windows if not getattr(w, "isMinimized", False) and w.width > 0]
    win = max(visible or windows, key=lambda w: w.width * w.height)
    return {
        "left": win.left,
        "top": win.top,
        "width": win.width,
        "height": win.height,
        "title": win.title,
    }


def capture_window_snapshot() -> tuple[Image.Image, dict]:
    """디버그용: 게임 창 전체를 캡처하고, 닉네임 크롭 영역을 빨간 박스로
    표시한 이미지와 창 정보를 반환합니다. (좌표가 맞는지 눈으로 확인용)"""
    from PIL import ImageDraw

    window = _get_game_window_rect()
    with mss.mss() as sct:
        img = _capture_region(sct, window)
    draw = ImageDraw.Draw(img)
    for region in _resolve_crop_regions_for_image(img.width, img.height):
        draw.rectangle(
            (
                region["left"] - 2,
                region["top"] - 2,
                region["left"] + region["width"] + 2,
                region["top"] + region["height"] + 2,
            ),
            outline=(255, 0, 0),
            width=2,
        )
    return img, window


def _resolve_crop_regions() -> list[dict]:
    """비율(CROP_REGIONS_PCT)을, 지금 실제 게임 창 위치/크기 기준의
    절대 픽셀 좌표로 환산합니다."""
    window = _get_game_window_rect()
    resolved = []
    for region in CROP_REGIONS_PCT:
        resolved.append(
            {
                "name": region["name"],
                "left": window["left"] + int(region["left"] * window["width"]),
                "top": window["top"] + int(region["top"] * window["height"]),
                "width": int(region["width"] * window["width"]),
                "height": int(region["height"] * window["height"]),
            }
        )
    return resolved


def _resolve_crop_regions_for_image(img_width: int, img_height: int) -> list[dict]:
    """이미지 파일 크기를 '창 크기'로 간주하고 비율을 절대좌표로 환산합니다.

    스크린샷 파일이 게임 창(또는 화면) 전체를 담고 있다는 전제입니다.
    """
    resolved = []
    for region in CROP_REGIONS_PCT:
        resolved.append(
            {
                "name": region["name"],
                "left": int(region["left"] * img_width),
                "top": int(region["top"] * img_height),
                "width": int(region["width"] * img_width),
                "height": int(region["height"] * img_height),
            }
        )
    return resolved


def _capture_region(sct, region: dict) -> Image.Image:
    shot = sct.grab(
        {
            "left": region["left"],
            "top": region["top"],
            "width": region["width"],
            "height": region["height"],
        }
    )
    return Image.frombytes("RGB", shot.size, shot.rgb)


# ---------------------------------------------------------------------------
# OCR 핵심 로직 (다국어 지원)
#
# 이터널 리턴 닉네임은 영문/숫자뿐 아니라 한글, 일본어(가나/한자),
# 중국어(간체/번체) 그리고 이들이 섞인 형태(예: 'ya발견', '静戒丨BS')로
# 나올 수 있습니다. Tesseract는 언어팩 하나로 여러 문자 체계를 동시에
# 잘 읽지 못하기 때문에 다음 방식으로 처리합니다.
#
#  1) 크롭 이미지를 여러 배율/전처리로 만든다 (OCR_PASSES).
#  2) 각 이미지에 언어팩별(OCR_LANGS)로 OCR을 돌리고, 단어 단위로
#     텍스트·신뢰도(conf)·위치(x좌표)를 얻는다.
#  3) 언어팩마다 '그 언어팩이 책임지는 문자 체계'만 남긴다.
#     (eng → 영문/숫자, kor → 한글, jpn → 가나/한자, chi_* → 한자)
#     예: kor 언어팩이 'sooin'을 '50010'으로 높은 신뢰도로 읽는 문제를
#     이걸로 막습니다 - 영문/숫자는 eng 결과만 믿습니다.
#  4) 후보를 만든다.
#     - 단일 언어 후보: 한 언어팩 결과만으로 만든 문자열
#     - 병합 후보: 모든 언어팩의 단어를 신뢰도 높은 순으로 고르되 위치가
#       겹치는 단어는 버리고, x좌표 순서로 이어 붙인 문자열
#       ('ya' (eng) + '발견' (kor) → 'ya발견' 처럼 순서가 자동으로 맞음)
#  5) 점수 = 평균 신뢰도 × 커버리지(글자 영역 중 후보가 설명하는 비율).
#     일부 글자만 읽고 나머지를 버린 후보가 높은 점수를 받지 않게 합니다.
# ---------------------------------------------------------------------------

OCR_LANGS = ["eng", "kor", "jpn", "chi_sim", "chi_tra"]

# (확대 배율, 전처리 모드). 배율에 따라 잘 읽히는 글자가 달라서
# (예: 'ya발견'의 한글은 3배에서, 영문은 6배에서 잘 읽힘) 여러 개를 씁니다.
OCR_PASSES = [(3, "soft"), (6, "soft"), (6, "binary")]

# 전처리 시 상하좌우에 붙이는 흰 여백(px). 좌표 환산에 사용.
_PAD = 30

# 이 신뢰도 미만인 단어는 후보 조립에 쓰지 않음 (0~100)
MIN_WORD_CONF = 45

# 닉네임 안에서 구분자로 쓰일 수 있는 기호 ('静戒丨BS' 같은 경우)
_SEPARATORS = set("|丨_-")


def _is_hangul(ch: str) -> bool:
    return "가" <= ch <= "힣"


def _is_kana(ch: str) -> bool:
    return (
        "぀" <= ch <= "ヿ"  # 히라가나 + 가타카나 (장음 'ー' 포함)
        or "ㇰ" <= ch <= "ㇿ"  # 가타카나 음성 확장
        or "ｦ" <= ch <= "ﾟ"  # 반각 가타카나
    )


def _is_cjk(ch: str) -> bool:
    return "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿"


def _is_latin(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


# 한자/가나 언어팩(jpn, chi_*)은 영문 단어도 꽤 정확히 읽습니다 (예: eng가
# 신뢰도 0~50으로 읽는 'ya'를 jpn은 70~90으로 읽음). 그래서 '단어 전체가
# 영문/숫자'인 경우에 한해 이 언어팩들의 영문도 쓰되, 신뢰도를 살짝 깎습니다.
# kor 언어팩은 영문을 숫자로 잘못 읽는 경향('sooin' -> '50010')이 강해서 제외.
_LATIN_TRUSTED_LANGS = {"jpn", "chi_sim", "chi_tra"}
_LATIN_CONF_PENALTY = 0.9

# 한자를 읽는 언어팩들. 병합 후보를 만들 때 이 중 '하나'만 섞습니다
# (jpn과 chi를 섞으면 가나 자리에 엉뚱한 한자가 끼어드는 문제가 있음).
_CJK_LANGS = ["jpn", "chi_sim", "chi_tra"]

# 언어팩별로 '믿고 쓸' 문자 판별 함수
_LANG_CHAR_FILTERS = {
    "eng": lambda ch: _is_latin(ch) or ch in _SEPARATORS,
    "kor": _is_hangul,
    "jpn": lambda ch: _is_kana(ch) or _is_cjk(ch),
    "chi_sim": _is_cjk,
    "chi_tra": _is_cjk,
}


def _trim_edge_columns(img: Image.Image) -> Image.Image:
    """크롭 좌우 끝에 걸친 밝은 세로 경계선(UI 테두리)을 잘라냅니다.

    닉네임 배경은 어두운 색이라 글자가 있는 열이라도 위/아래 끝은
    항상 어둡습니다. 반면 UI 테두리는 열 전체가 밝습니다. 그래서
    '열 전체의 최솟값이 밝은' 열만 가장자리에서부터 제거합니다.
    (이 테두리가 OCR에서 '|' 잡음으로 읽히는 문제를 막기 위함)
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
    if (left, right) == (0, w):
        return img
    return img.crop((left, 0, right, h))


def _preprocess(img: Image.Image, scale: int = 6, mode: str = "soft") -> Image.Image:
    """OCR 정확도를 올리기 위한 전처리.

    닉네임이 '어두운 반투명 배경 + 흰 글씨'라서 반전이 필요합니다.
    - soft: 부드러운 반전 + 자동 대비 보정 (얇은 한글 획 보존에 유리)
    - binary: 반전 후 이진화 (가나처럼 획이 단순한 글자에 유리할 때가 있음)
    글자가 이미지 가장자리에 딱 붙어 있으면 Tesseract가 줄 경계를
    못 잡는 경우가 있어, 상하좌우에 흰 여백을 추가합니다.
    """
    gray = img.convert("L")
    scaled = gray.resize((gray.width * scale, gray.height * scale), Image.LANCZOS)
    inverted = ImageOps.invert(scaled)
    contrasted = ImageOps.autocontrast(inverted, cutoff=1)
    if mode == "binary":
        contrasted = contrasted.point(lambda v: 255 if v > 140 else 0)
    return ImageOps.expand(contrasted, border=_PAD, fill=255)


def _ocr_words(img: Image.Image, lang: str, scale: int) -> list[dict]:
    """한 이미지 + 한 언어팩으로 OCR을 돌려 단어 목록을 반환합니다.

    각 단어: {"raw": 원문, "text": 언어팩 필터를 통과한 글자,
             "conf": 0~100, "x0": .., "x1": .., "lang": ..}
    좌표는 전처리 전 '원본 크롭' 기준 픽셀로 환산합니다 (배율이 다른
    결과끼리 비교할 수 있도록).
    """
    data = pytesseract.image_to_data(
        img, lang=lang, config="--psm 7", output_type=pytesseract.Output.DICT
    )
    char_ok = _LANG_CHAR_FILTERS[lang]
    words = []
    for raw, conf, left, width in zip(
        data["text"], data["conf"], data["left"], data["width"]
    ):
        raw = raw.strip()
        conf = float(conf)
        if not raw or conf < 0:
            continue
        text = "".join(ch for ch in raw if char_ok(ch))
        if lang in _LATIN_TRUSTED_LANGS and all(_is_latin(ch) for ch in raw):
            text = raw
            conf *= _LATIN_CONF_PENALTY
        words.append(
            {
                "raw": raw,
                "text": text,
                "conf": conf,
                "x0": (left - _PAD) / scale,
                "x1": (left + width - _PAD) / scale,
                "lang": lang,
            }
        )

    # Tesseract가 줄의 첫 단어 박스를 줄 끝까지 넓게 잡는 경우가 있어서,
    # 각 단어의 오른쪽 끝을 다음 단어의 시작 위치로 잘라 줍니다.
    words.sort(key=lambda w: w["x0"])
    for cur, nxt in zip(words, words[1:]):
        cur["x1"] = max(cur["x0"], min(cur["x1"], nxt["x0"]))
    return words


def _span(words: list[dict]) -> float:
    """단어들이 덮는 가로 길이(겹치는 부분은 한 번만)를 계산합니다."""
    total, cur_start, cur_end = 0.0, None, None
    for w in sorted(words, key=lambda w: w["x0"]):
        if cur_end is None or w["x0"] > cur_end:
            if cur_end is not None:
                total += cur_end - cur_start
            cur_start, cur_end = w["x0"], w["x1"]
        else:
            cur_end = max(cur_end, w["x1"])
    if cur_end is not None:
        total += cur_end - cur_start
    return total


def _overlap_ratio(a: dict, b: dict) -> float:
    inter = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
    shorter = min(a["x1"] - a["x0"], b["x1"] - b["x0"])
    return inter / shorter if shorter > 0 and inter > 0 else 0.0


def _strip_separators(text: str) -> str:
    """앞뒤에 붙은 구분자 잡음('|' 등)을 제거합니다."""
    return text.strip("".join(_SEPARATORS))


def _build_candidates(words: list[dict], text_width: float) -> list[tuple[str, float, str]]:
    """한 전처리 패스의 모든 언어팩 단어로 (후보, 점수, 출처) 목록을 만듭니다."""
    if text_width <= 0:
        return []

    usable = [w for w in words if w["text"] and w["conf"] >= MIN_WORD_CONF]
    candidates = []

    # (1) 단일 언어 후보
    for lang in OCR_LANGS:
        lang_words = [w for w in usable if w["lang"] == lang]
        if not lang_words:
            continue
        text = _strip_separators("".join(w["text"] for w in lang_words))
        if not text:
            continue
        conf = sum(w["conf"] for w in lang_words) / len(lang_words)
        coverage = min(1.0, _span(lang_words) / text_width)
        candidates.append((text, conf * coverage, lang))

    # (2) 병합 후보: 신뢰도 높은 단어부터 위치가 겹치지 않게 채택.
    #     한자 언어팩은 하나씩만 섞어서 언어팩별로 후보를 따로 만듭니다.
    for cjk_lang in _CJK_LANGS:
        pool = [w for w in usable if w["lang"] in ("eng", "kor", cjk_lang)]
        chosen: list[dict] = []
        for w in sorted(pool, key=lambda w: w["conf"], reverse=True):
            if all(_overlap_ratio(w, c) < 0.3 for c in chosen):
                chosen.append(w)
        if not chosen or len({w["lang"] for w in chosen}) < 2:
            continue
        chosen.sort(key=lambda w: w["x0"])
        text = _strip_separators("".join(w["text"] for w in chosen))
        if text:
            conf = sum(w["conf"] for w in chosen) / len(chosen)
            coverage = min(1.0, _span(chosen) / text_width)
            candidates.append((text, conf * coverage, f"merged-{cjk_lang}"))

    return candidates


def _dedupe_consecutive(s: str) -> str:
    """연속으로 겹치는 글자를 하나로 줄입니다 ('yaa' -> 'ya').

    OCR이 폰트 특성상 글자를 겹쳐 읽는 경우를 보정하기 위한 마지막
    수단(fallback)입니다. 'sooin'처럼 진짜로 중복 글자가 있는 닉네임을
    망가뜨릴 수 있어서, 원래 후보를 대체하지 않고 점수를 낮춰서
    맨 뒤쪽 후보로만 덧붙입니다."""
    result = []
    for ch in s:
        if not result or result[-1] != ch:
            result.append(ch)
    return "".join(result)


def _separator_alternatives(s: str) -> list[str]:
    """'|'와 '丨'(한자 부수)은 화면상 거의 구분이 안 되므로 서로 바꾼 후보도 만듭니다."""
    alts = []
    if "|" in s:
        alts.append(s.replace("|", "丨"))
    if "丨" in s:
        alts.append(s.replace("丨", "|"))
    return alts


def _run_ocr(crop: Image.Image) -> dict:
    """크롭 이미지 하나에 대해 여러 전처리 × 여러 언어팩으로 OCR을 돌려
    후보 전체와 가장 그럴듯한 결과(best)를 반환합니다.

    반환: {"best": str, "best_source": str, "confidence": float(0~100),
           "candidates": [점수 높은 순 후보 문자열],
           "variants": {출처: 후보}  # 하위 호환용, 점수 높은 순}
    """
    crop = _trim_edge_columns(crop)
    jobs = []
    images = {p: _preprocess(crop, *p) for p in OCR_PASSES}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for p, img in images.items():
            for lang in OCR_LANGS:
                jobs.append((p, pool.submit(_ocr_words, img, lang, p[0])))
        words_by_pass: dict = {p: [] for p in OCR_PASSES}
        for p, fut in jobs:
            words_by_pass[p].extend(fut.result())

    # 같은 후보가 여러 패스/언어에서 나오면 최고 점수 + 일치 보너스
    scores: dict[str, float] = {}
    sources: dict[str, str] = {}
    hits: dict[str, int] = {}
    for p, words in words_by_pass.items():
        # 글자 영역 폭: 어떤 언어팩이든 '무언가'를 읽어낸 영역 전체
        text_width = _span([w for w in words if w["conf"] >= MIN_WORD_CONF]) or _span(words)
        for text, score, src in _build_candidates(words, text_width):
            hits[text] = hits.get(text, 0) + 1
            if score > scores.get(text, -1):
                scores[text] = score
                sources[text] = f"{src}@x{p[0]}{'' if p[1] == 'soft' else '-' + p[1]}"
    for text in scores:
        scores[text] += min(hits[text] - 1, 5) * 2

    # 보조 후보: 중복 글자 축소 / 구분자 치환 (원래 후보보다 낮은 점수)
    for text in list(scores):
        for alt in [_dedupe_consecutive(text), *_separator_alternatives(text)]:
            if alt and alt not in scores:
                scores[alt] = scores[text] - 10
                sources[alt] = sources[text] + "+alt"

    ranked = sorted(scores, key=lambda t: scores[t], reverse=True)
    if not ranked:
        return {"best": "", "best_source": "", "confidence": 0.0,
                "candidates": [], "candidate_scores": {}, "variants": {}}

    best = ranked[0]
    return {
        "best": best,
        "best_source": sources[best],
        "confidence": round(max(0.0, min(100.0, scores[best])), 1),
        "candidates": ranked,
        "candidate_scores": {t: round(scores[t], 1) for t in ranked},
        "variants": {sources[t]: t for t in ranked},
    }


def capture_crops() -> list[Image.Image]:
    """지금 게임 화면에서 팀원별 닉네임 영역을 캡처해 CROP_REGIONS_PCT 순서대로
    반환합니다 (OCR은 하지 않음 - 화면 상태 비교 등 가벼운 용도)."""
    # 매번 실행 시점의 실제 게임 창 위치/크기를 기준으로 좌표를 다시 계산
    # (모니터가 바뀌거나 창이 이동해도 항상 정확한 위치를 계산함)
    crop_regions = _resolve_crop_regions()
    with mss.mss() as sct:
        return [_capture_region(sct, region) for region in crop_regions]


def crops_from_image(image_path: str) -> list[Image.Image]:
    """저장된 스크린샷에서 capture_crops()와 같은 크롭을 만듭니다 (테스트용)."""
    full_img = Image.open(image_path).convert("RGB")
    crops = []
    for region in _resolve_crop_regions_for_image(full_img.width, full_img.height):
        crops.append(
            full_img.crop(
                (
                    region["left"],
                    region["top"],
                    region["left"] + region["width"],
                    region["top"] + region["height"],
                )
            )
        )
    return crops


def ocr_crops(crops: list[Image.Image], save_debug_images: bool = False) -> list[dict]:
    """크롭 이미지 목록에 OCR을 돌려 팀원별 결과를 반환합니다.
    각 결과에는 원본 크롭("crop_image")도 같이 담습니다."""
    results = []
    for region, crop_img in zip(CROP_REGIONS_PCT, crops):
        name = region["name"]
        if save_debug_images:
            crop_img.save(f"debug_crop_{name}.png")
            _preprocess(_trim_edge_columns(crop_img)).save(f"debug_processed_{name}.png")
        results.append({"name": name, **_run_ocr(crop_img), "crop_image": crop_img})
    return results


def get_teammate_ocr_results(save_debug_images: bool = False) -> list[dict]:
    """팀원별 OCR 결과(후보 전체 포함)를 CROP_REGIONS_PCT 순서대로 반환합니다.

    각 원소: {"name": "teammate_1", "best": "PuniPaw",
              "best_source": "eng@x6", "confidence": 91.0,
              "candidates": ["PuniPaw", ...],  # 점수 높은 순
              "candidate_scores": {"PuniPaw": 101.0, ...},
              "variants": {...},
              "crop_image": PIL.Image}  # OCR에 쓴 원본 크롭

    save_debug_images=True로 두면 debug_crop_*.png / debug_processed_*.png
    파일을 같이 저장합니다 (좌표/전처리 확인용, 평소엔 필요 없음).
    """
    return ocr_crops(capture_crops(), save_debug_images=save_debug_images)


def get_teammate_names() -> list[str]:
    """팀원 닉네임만 간단히 리스트로 받고 싶을 때 쓰는 함수.

    예: ["PuniPaw", "sooin", "ya발견", "アンベリィ"]
    """
    results = get_teammate_ocr_results(save_debug_images=False)
    return [r["best"] for r in results]


def get_teammate_ocr_results_from_image(
    image_path: str, save_debug_images: bool = False
) -> list[dict]:
    """실시간 화면 캡처 대신, 저장해둔 스크린샷 파일로 같은 파이프라인을
    테스트할 때 쓰는 함수.

    게임을 매번 실행하지 않고도 크롭 좌표/전처리/OCR을 반복 테스트할 수
    있어서 개발 중에 유용합니다. 이미지 전체가 게임 창(또는 전체화면)을
    담고 있다는 전제로, 이미지 크기를 기준으로 CROP_REGIONS_PCT를
    절대좌표로 환산합니다.

    반환 형식은 get_teammate_ocr_results()와 동일합니다.
    """
    return ocr_crops(crops_from_image(image_path), save_debug_images=save_debug_images)


if __name__ == "__main__":
    # 모듈만 단독으로 실행했을 때 간단히 확인해볼 수 있도록
    print(get_teammate_names())