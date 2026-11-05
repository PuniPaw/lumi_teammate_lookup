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

# ---------------------------------------------------------------------------
# 닉네임 영역 좌표
#
# 기준 해상도 1920x1080 화면에서 잰 팀원별 닉네임 영역(픽셀)입니다.
# 이터널 리턴 UI는 해상도에 따라
#   - 배율 = min(가로/1920, 세로/1080) 로 커지고
#   - 화면 '중앙'을 기준으로 배치됩니다.
# (1920x1080과 2880x1800(16:10) 화면을 비교해서 확인: 2880x1800에서는
#  배율 1.5(가로 기준), 닉네임 카드도 중앙 기준 거리 x1.5 위치에 있음)
# 그래서 아래 기준 좌표를 ui_regions()로 변환하면 해상도/화면 비율이 달라도
# 같은 공식으로 위치를 계산할 수 있습니다.
# ---------------------------------------------------------------------------
REFERENCE_WIDTH = 1920
REFERENCE_HEIGHT = 1080
NAME_REGIONS_REF = [
    {"name": "teammate_1", "left": 1080, "top": 935, "width": 134, "height": 14},
    {"name": "teammate_2", "left": 1364, "top": 935, "width": 134, "height": 14},
    {"name": "teammate_3", "left": 1665, "top": 935, "width": 120, "height": 14},
]

# 위치 미세 보정: 계산한 위치에서 위아래로 '영역 높이 x 이 값'만큼 넓게
# 캡처한 뒤, 글자가 가장 잘 들어오는 위치를 고릅니다 (몇 픽셀 어긋나도 보정).
VERTICAL_SEARCH_RATIO = 1.0


def ui_regions(width: int, height: int) -> list[dict]:
    """게임 화면 크기(width x height)에서의 닉네임 영역 좌표를 계산합니다.
    좌표는 게임 화면 왼쪽 위 기준."""
    scale = min(width / REFERENCE_WIDTH, height / REFERENCE_HEIGHT)
    cx, cy = width / 2, height / 2
    regions = []
    for r in NAME_REGIONS_REF:
        regions.append(
            {
                "name": r["name"],
                "left": round(cx + (r["left"] - REFERENCE_WIDTH / 2) * scale),
                "top": round(cy + (r["top"] - REFERENCE_HEIGHT / 2) * scale),
                "width": max(1, round(r["width"] * scale)),
                "height": max(1, round(r["height"] * scale)),
            }
        )
    return regions


def _search_box(region: dict, area_height: int) -> dict:
    """미세 보정용으로 위아래를 넓힌 캡처 영역."""
    pad = round(region["height"] * VERTICAL_SEARCH_RATIO)
    top = max(0, region["top"] - pad)
    bottom = min(area_height, region["top"] + region["height"] + pad)
    return {**region, "top": top, "height": max(region["height"], bottom - top)}


def _best_window(strip: Image.Image, height: int, expected_offset: int) -> Image.Image:
    """위아래로 넓게 캡처한 strip에서, 글자가 가장 많이 들어오는 높이 height의
    구간을 잘라 반환합니다. 글자가 없으면 예상 위치를 그대로 씁니다.

    '글자 양'은 행마다 '옆 픽셀과 밝기 차이가 큰 지점'의 수로 셉니다.
    닉네임 아래의 색깔 진행 막대나 카드 테두리처럼 가로로 균일한 밝은 띠는
    이 값이 거의 0이라 글자로 착각하지 않습니다.
    """
    expected_offset = min(max(0, expected_offset), max(0, strip.height - height))
    gray = strip.convert("L")
    w = gray.width
    px = gray.load()
    row_edges = [
        sum(1 for x in range(1, w) if abs(px[x, y] - px[x - 1, y]) > EDGE_THRESHOLD)
        for y in range(gray.height)
    ]

    best_y, best_count = expected_offset, -1
    for y in range(0, max(1, gray.height - height + 1)):
        count = sum(row_edges[y : y + height])
        # 같은 양이면 예상 위치에 더 가까운 쪽
        if count > best_count or (
            count == best_count and abs(y - expected_offset) < abs(best_y - expected_offset)
        ):
            best_y, best_count = y, count
    if best_count < MIN_EDGES_FOR_TEXT:
        best_y = expected_offset
    # 'y', 'g' 같은 글자의 꼬리가 잘리지 않도록 위아래로 약간 여유를 둠
    margin = max(1, round(height * WINDOW_MARGIN_RATIO))
    top = max(0, best_y - margin)
    bottom = min(gray.height, best_y + height + margin)
    return strip.crop((0, top, strip.width, bottom))


# _best_window에서 '글자 경계'로 볼 이웃 픽셀 밝기 차이, 글자가 있다고 볼 최소 경계 수
EDGE_THRESHOLD = 60
MIN_EDGES_FOR_TEXT = 20
# 고른 구간 위아래에 더하는 여유 (영역 높이 대비)
WINDOW_MARGIN_RATIO = 0.08


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
    left, top, width, height = win.left, win.top, win.width, win.height

    # 창 모드에서는 창 크기에 제목 표시줄/테두리가 포함되므로, 실제 게임이
    # 그려지는 '클라이언트 영역'을 씁니다. (pywin32가 없으면 창 크기 그대로)
    try:
        import win32gui

        hwnd = win._hWnd
        _, _, client_w, client_h = win32gui.GetClientRect(hwnd)
        client_left, client_top = win32gui.ClientToScreen(hwnd, (0, 0))
        if client_w > 0 and client_h > 0:
            left, top, width, height = client_left, client_top, client_w, client_h
    except Exception:
        pass

    return {
        "left": left,
        "top": top,
        "width": width,
        "height": height,
        "title": win.title,
        # 화면을 '보이는 그대로' 캡처하므로, 다른 창이 게임을 가리면 그 창을 읽게 됨
        "active": bool(getattr(win, "isActive", True)),
    }


def is_game_window_active() -> bool:
    """게임 창이 맨 앞(활성 창)인지. 확인할 수 없으면 True."""
    try:
        return _get_game_window_rect()["active"]
    except Exception:
        return True


def capture_window_snapshot() -> tuple[Image.Image, dict]:
    """디버그용: 게임 화면 전체를 캡처하고, 닉네임 영역(계산된 위치)을 빨간
    박스로 표시한 이미지와 창 정보를 반환합니다. (좌표가 맞는지 확인용)"""
    from PIL import ImageDraw

    window = _get_game_window_rect()
    with mss.mss() as sct:
        img = _capture_region(sct, window)
    draw = ImageDraw.Draw(img)
    for region in ui_regions(img.width, img.height):
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


def _game_area(img: Image.Image) -> Image.Image:
    """스크린샷 아래쪽에 붙은 흰 여백을 잘라 게임 화면만 남깁니다.
    (저장소의 테스트 스크린샷은 1920x1080 게임 화면 아래에 흰 여백이 붙은
     1920x1716 이미지라서 필요함)"""
    gray = img.convert("L")
    w, h = gray.size
    bottom = h
    while bottom > 1:
        row = gray.crop((0, bottom - 1, w, bottom))
        lo, _ = row.getextrema()
        if lo < 240:
            break
        bottom -= 1
    return img if bottom == h else img.crop((0, 0, w, bottom))


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

# 1단계(빠른 OCR): 이 패스/언어팩만 먼저 돌려서 점수가 FAST_ACCEPT_SCORE
# 이상이면 바로 확정합니다. (Windows는 Tesseract 실행 1회 비용이 커서,
# 전체 15회를 매번 돌리면 한 칸에 수 초가 걸림)
FAST_PASS = (3, "soft")
FAST_LANGS = ["eng", "kor", "jpn"]
FAST_ACCEPT_SCORE = 90

# 크롭에서 '배경보다 확실히 밝은 픽셀(글자)'의 비율이 이보다 작으면 빈 칸으로
# 보고 OCR을 건너뜁니다. (저장된 스크린샷 기준: 닉네임 칸 0.10~0.33, 빈 칸 0~0.03)
MIN_TEXT_PIXEL_RATIO = 0.05

# 가로선/세로선 같은 UI 요소를 글자로 잘못 읽은 결과에 자주 나오는 문자
_LINE_LIKE_CHARS = set("一丨|-_ー—")

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
    #     한글(kor)과 한자/가나(jpn, chi_*)는 한 후보에 섞지 않습니다. 실제로
    #     섞인 닉네임은 드물고, 섞으면 한자를 한글로 잘못 읽은 글자가 끼어듦
    #     (예: '藤田皮卡丘' -> 'ie田皮卡드', '불법체류자엠마' -> '量법체류자엠마').
    #     한자 언어팩이 읽은 '영문 단어'는 한글 후보에도 씁니다 ('ya발견').
    pools = {}
    for cjk_lang in _CJK_LANGS:
        cjk_latin = [
            w for w in usable if w["lang"] == cjk_lang and all(_is_latin(ch) for ch in w["text"])
        ]
        pools[f"hangul-{cjk_lang}"] = [w for w in usable if w["lang"] in ("eng", "kor")] + cjk_latin
        pools[cjk_lang] = [w for w in usable if w["lang"] in ("eng", cjk_lang)]
    for pool_name, pool in pools.items():
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
            candidates.append((text, conf * coverage, f"merged-{pool_name}"))

    return candidates


def _text_pixel_ratio(img: Image.Image) -> float:
    """배경(중앙값)보다 80 이상 밝은 픽셀의 비율 = 흰 글씨가 차지하는 비율."""
    gray = img.convert("L")
    hist = gray.histogram()
    total = sum(hist)
    if total == 0:
        return 0.0
    acc, median = 0, 0
    for value, count in enumerate(hist):
        acc += count
        if acc * 2 >= total:
            median = value
            break
    return sum(hist[median + 81:]) / total


def _is_junk(text: str) -> bool:
    """UI의 선/테두리를 글자로 읽은 듯한 후보인지.

    예: '一一一一' (가로선), '||'. 실제로 이런 닉네임의 유저가 존재해서
    엉뚱한 사람의 전적이 뜬 적이 있어서 후보에서 아예 뺍니다.
    """
    if not text:
        return True
    if len(text) >= 2 and len(set(text)) == 1:
        return True
    return all(ch in _LINE_LIKE_CHARS for ch in text)


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
    if _text_pixel_ratio(crop) < MIN_TEXT_PIXEL_RATIO:
        return _empty_result()  # 빈 칸 (아직 닉네임이 안 그려졌거나 다른 화면)

    images = {p: _preprocess(crop, *p) for p in OCR_PASSES}

    def run(jobs_spec):
        words_by_pass: dict = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [(p, pool.submit(_ocr_words, images[p], lang, p[0])) for p, lang in jobs_spec]
            for p, fut in futures:
                words_by_pass.setdefault(p, []).extend(fut.result())
        return words_by_pass

    # 1단계: 빠른 OCR로 충분히 확실하면 바로 확정
    fast_spec = [(FAST_PASS, lang) for lang in FAST_LANGS]
    fast_words = run(fast_spec)
    fast = _rank_candidates(fast_words)
    if fast["best"] and fast["candidate_scores"][fast["best"]] >= FAST_ACCEPT_SCORE:
        return fast

    # 2단계: 나머지 패스/언어팩까지 전부
    rest_spec = [(p, lang) for p in OCR_PASSES for lang in OCR_LANGS if (p, lang) not in fast_spec]
    words_by_pass = run(rest_spec)
    for p, words in fast_words.items():
        words_by_pass.setdefault(p, []).extend(words)
    return _rank_candidates(words_by_pass)


def _empty_result() -> dict:
    return {"best": "", "best_source": "", "confidence": 0.0,
            "candidates": [], "candidate_scores": {}, "variants": {}}


def _rank_candidates(words_by_pass: dict) -> dict:
    """패스별 단어 목록으로 후보를 만들고 점수순으로 정렬한 결과를 반환합니다."""
    # 같은 후보가 여러 패스/언어에서 나오면 최고 점수 + 일치 보너스
    scores: dict[str, float] = {}
    sources: dict[str, str] = {}
    hits: dict[str, int] = {}
    for p, words in words_by_pass.items():
        # 글자 영역 폭: 어떤 언어팩이든 '무언가'를 읽어낸 영역 전체
        text_width = _span([w for w in words if w["conf"] >= MIN_WORD_CONF]) or _span(words)
        for text, score, src in _build_candidates(words, text_width):
            if _is_junk(text):
                continue
            hits[text] = hits.get(text, 0) + 1
            if score > scores.get(text, -1):
                scores[text] = score
                sources[text] = f"{src}@x{p[0]}{'' if p[1] == 'soft' else '-' + p[1]}"
    for text in scores:
        scores[text] += min(hits[text] - 1, 5) * 2

    # 보조 후보: 중복 글자 축소 / 구분자 치환 (원래 후보보다 낮은 점수)
    for text in list(scores):
        for alt in [_dedupe_consecutive(text), *_separator_alternatives(text)]:
            if alt and alt not in scores and not _is_junk(alt):
                scores[alt] = scores[text] - 10
                sources[alt] = sources[text] + "+alt"

    ranked = sorted(scores, key=lambda t: scores[t], reverse=True)
    if not ranked:
        return _empty_result()

    best = ranked[0]
    return {
        "best": best,
        "best_source": sources[best],
        "confidence": round(max(0.0, min(100.0, scores[best])), 1),
        "candidates": ranked,
        "candidate_scores": {t: round(scores[t], 1) for t in ranked},
        "variants": {sources[t]: t for t in ranked},
    }


def capture_crops(refine: bool = True) -> list[Image.Image]:
    """지금 게임 화면에서 팀원별 닉네임 영역을 캡처해 NAME_REGIONS_REF 순서대로
    반환합니다 (OCR은 하지 않음).

    refine=True면 위아래를 넓게 캡처해서 글자가 가장 잘 들어오는 위치로
    미세 보정합니다. 화면 상태 비교(게임 시작 감지)처럼 항상 같은 위치를
    봐야 하는 용도에는 refine=False를 씁니다.
    """
    # 매번 실행 시점의 실제 게임 창 위치/크기를 기준으로 좌표를 다시 계산
    # (모니터가 바뀌거나 창이 이동해도 항상 정확한 위치를 계산함)
    window = _get_game_window_rect()
    crops = []
    with mss.mss() as sct:
        for region in ui_regions(window["width"], window["height"]):
            box = _search_box(region, window["height"]) if refine else region
            shot = _capture_region(
                sct,
                {
                    "left": window["left"] + box["left"],
                    "top": window["top"] + box["top"],
                    "width": box["width"],
                    "height": box["height"],
                },
            )
            if refine:
                shot = _best_window(shot, region["height"], region["top"] - box["top"])
            crops.append(shot)
    return crops


def crops_from_image(image_path: str, refine: bool = True) -> list[Image.Image]:
    """저장된 스크린샷에서 capture_crops()와 같은 크롭을 만듭니다 (테스트용)."""
    full_img = _game_area(Image.open(image_path).convert("RGB"))
    crops = []
    for region in ui_regions(full_img.width, full_img.height):
        box = _search_box(region, full_img.height) if refine else region
        strip = full_img.crop(
            (box["left"], box["top"], box["left"] + box["width"], box["top"] + box["height"])
        )
        if refine:
            strip = _best_window(strip, region["height"], region["top"] - box["top"])
        crops.append(strip)
    return crops


def ocr_crops(crops: list[Image.Image], save_debug_images: bool = False) -> list[dict]:
    """크롭 이미지 목록에 OCR을 돌려 팀원별 결과를 반환합니다.
    각 결과에는 원본 크롭("crop_image")도 같이 담습니다."""
    results = []
    for region, crop_img in zip(NAME_REGIONS_REF, crops):
        name = region["name"]
        if save_debug_images:
            crop_img.save(f"debug_crop_{name}.png")
            _preprocess(_trim_edge_columns(crop_img)).save(f"debug_processed_{name}.png")
        results.append({"name": name, **_run_ocr(crop_img), "crop_image": crop_img})
    return results


def get_teammate_ocr_results(save_debug_images: bool = False) -> list[dict]:
    """팀원별 OCR 결과(후보 전체 포함)를 NAME_REGIONS_REF 순서대로 반환합니다.

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
    담고 있다는 전제로, 이미지 크기를 기준으로 ui_regions()로 위치를
    계산합니다 (아래쪽 흰 여백은 자동으로 잘라냄).

    반환 형식은 get_teammate_ocr_results()와 동일합니다.
    """
    return ocr_crops(crops_from_image(image_path), save_debug_images=save_debug_images)


if __name__ == "__main__":
    # 모듈만 단독으로 실행했을 때 간단히 확인해볼 수 있도록
    print(get_teammate_names())