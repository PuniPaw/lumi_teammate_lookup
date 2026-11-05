"""
닉네임 칸 이미지 -> OCR -> 점수순 닉네임 후보.

닉네임에는 영문/숫자, 한글, 일본어(가나/한자), 중국어(간체/번체)와 이들이 섞인
형태('ya발견', '静戒丨BS')가 나옵니다. Tesseract는 언어팩 하나로 여러 문자 체계를
잘 읽지 못하므로:

  1) 크롭을 여러 배율/전처리(OCR_PASSES)로 만들고 언어팩별(OCR_LANGS)로 OCR
  2) 언어팩마다 담당 문자 체계만 신뢰 (eng: 영문/숫자, kor: 한글, jpn: 가나/한자,
     chi_*: 한자)
  3) 후보 만들기
     - 단일 언어 후보
     - 병합 후보: 신뢰도 높은 단어부터 위치가 겹치지 않게 골라 x 순서로 연결.
       한글과 한자/가나는 한 후보에 섞지 않음
     - 한자 위치별 투표 후보: 신뢰도가 낮은 한자도 위치마다 가장 많이 나온 글자로
  4) 점수 = 평균 신뢰도 x 커버리지(글자 영역 중 후보가 설명하는 비율)
"""

import os
from concurrent.futures import ThreadPoolExecutor

import pytesseract
from PIL import Image, ImageOps

from screen_capture import NAME_REGIONS_REF, capture_crops, crops_from_image

# Windows 기본 설치 경로에 있으면 사용, 없으면 PATH의 tesseract.
# 필요한 언어팩: eng, kor, jpn, chi_sim, chi_tra
_WINDOWS_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(_WINDOWS_TESSERACT):
    pytesseract.pytesseract.tesseract_cmd = _WINDOWS_TESSERACT

# OCR을 병렬로 돌리므로 Tesseract 내부 멀티스레딩은 끔 (켜 두면 CPU 경쟁으로 몇 배 느려짐)
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

OCR_LANGS = ["eng", "kor", "jpn", "chi_sim", "chi_tra"]

# (확대 배율, 전처리). 글자마다 잘 읽히는 배율이 달라 여러 개를 씀
# (예: 'ya발견'의 한글은 3배, 영문은 6배에서 잘 읽힘)
OCR_PASSES = [(3, "soft"), (6, "soft"), (6, "binary")]
# 위 배율의 기준 칸 높이(px): 1920x1080의 칸 14px + 미세 보정 여유 위아래 1px.
# 칸이 더 크면(고해상도) 같은 글자 크기가 되도록 배율을 줄임.
OCR_REFERENCE_CROP_HEIGHT = 16

# 1단계: 이 조합만 먼저 돌려 FAST_ACCEPT_SCORE 이상이면 바로 확정
# (Windows는 Tesseract 1회 실행 비용이 커서 전체 15회를 매번 돌리면 느림)
FAST_PASS = (3, "soft")
FAST_LANGS = ["eng", "kor", "jpn"]
FAST_ACCEPT_SCORE = 90

# 흰 글씨 픽셀 비율이 이보다 작으면 빈 칸으로 보고 OCR 생략
# (측정값: 닉네임 칸 0.10~0.33, 빈 칸 0~0.03)
MIN_TEXT_PIXEL_RATIO = 0.05

# 후보 조립에 쓸 단어의 최소 신뢰도 (0~100)
MIN_WORD_CONF = 45

# 한자/가나 언어팩은 영문 단어도 잘 읽어서('ya'를 eng는 0~50, jpn은 70~90),
# 단어 전체가 영문/숫자면 신뢰도를 조금 깎아 사용. kor는 영문을 숫자로 읽는
# 경향('sooin' -> '50010')이 강해 제외.
_LATIN_TRUSTED_LANGS = {"jpn", "chi_sim", "chi_tra"}
_LATIN_CONF_PENALTY = 0.9

# 병합 후보에는 한자 언어팩을 하나씩만 섞음 (섞으면 가나 자리에 엉뚱한 한자가 끼어듦)
_CJK_LANGS = ["jpn", "chi_sim", "chi_tra"]

_SEPARATORS = set("|丨_-")  # 닉네임 안의 구분자 ('静戒丨BS')
_LINE_LIKE_CHARS = set("一丨|-_ー—")  # UI의 선을 글자로 읽은 결과에 자주 나옴
_PAD = 30  # 전처리 시 붙이는 흰 여백(px)

# 작은 화면에서 서로 헷갈리는 글자 묶음 (관찰된 것만). 일반 후보로 유저를 못 찾았을
# 때 이 안에서 글자를 바꿔 다시 조회함 (resolve_teammates)
CONFUSABLE_GROUPS = [
    "藤騰滕腾朋",
    "静靜",  # 간체/신자체 vs 번체
    "丨|",
]
_CONFUSABLE = {ch: group for group in CONFUSABLE_GROUPS for ch in group}

# 한자 위치별 투표: 한 위치로 인정할 최소 득표 수, 투표 후보의 최소 점수
MIN_POSITION_VOTES = 2
MIN_CONSENSUS_SCORE = 60


def _is_hangul(ch: str) -> bool:
    return "\uac00" <= ch <= "\ud7a3"


def _is_kana(ch: str) -> bool:
    return "\u3040" <= ch <= "\u30ff" or "\u31f0" <= ch <= "\u31ff" or "\uff66" <= ch <= "\uff9f"


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf"


def _is_latin(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


# 언어팩별로 신뢰하는 문자
_LANG_CHAR_FILTERS = {
    "eng": lambda ch: _is_latin(ch) or ch in _SEPARATORS,
    "kor": _is_hangul,
    "jpn": lambda ch: _is_kana(ch) or _is_cjk(ch),
    "chi_sim": _is_cjk,
    "chi_tra": _is_cjk,
}


# --- 전처리 ------------------------------------------------------------------


def _trim_edge_columns(img: Image.Image) -> Image.Image:
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


def _text_pixel_ratio(img: Image.Image) -> float:
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


def _preprocess(img: Image.Image, scale: float, mode: str) -> Image.Image:
    """흰 글씨/어두운 배경 -> 검은 글씨/흰 배경, 확대, 흰 여백 추가.

    soft: 부드러운 반전 + 자동 대비 (얇은 한글 획 보존), binary: 이진화.
    """
    gray = img.convert("L")
    gray = gray.resize((max(1, round(gray.width * scale)), max(1, round(gray.height * scale))), Image.LANCZOS)
    gray = ImageOps.autocontrast(ImageOps.invert(gray), cutoff=1)
    if mode == "binary":
        gray = gray.point(lambda v: 255 if v > 140 else 0)
    return ImageOps.expand(gray, border=_PAD, fill=255)


# --- OCR -----------------------------------------------------------------------


def _ocr_words(img: Image.Image, lang: str, scale: float) -> list[dict]:
    """한 이미지 x 한 언어팩의 단어 목록.

    단어: {"raw", "text"(언어팩이 신뢰하는 글자만), "conf", "x0", "x1"(원본 크롭 기준 px), "lang"}
    """
    data = pytesseract.image_to_data(img, lang=lang, config="--psm 7", output_type=pytesseract.Output.DICT)
    char_ok = _LANG_CHAR_FILTERS[lang]
    words = []
    for raw, conf, left, width in zip(data["text"], data["conf"], data["left"], data["width"]):
        raw, conf = raw.strip(), float(conf)
        if not raw or conf < 0:
            continue
        text = "".join(ch for ch in raw if char_ok(ch))
        if lang in _LATIN_TRUSTED_LANGS and all(_is_latin(ch) for ch in raw):
            text, conf = raw, conf * _LATIN_CONF_PENALTY
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

    # Tesseract가 첫 단어 박스를 줄 끝까지 잡는 경우가 있어 다음 단어 시작에서 자름
    words.sort(key=lambda w: w["x0"])
    for cur, nxt in zip(words, words[1:]):
        cur["x1"] = max(cur["x0"], min(cur["x1"], nxt["x0"]))
    return words


# --- 후보 만들기 ---------------------------------------------------------------


def _span(words: list[dict]) -> float:
    """단어들이 덮는 가로 길이 (겹치는 부분은 한 번만)."""
    total, start, end = 0.0, None, None
    for w in sorted(words, key=lambda w: w["x0"]):
        if end is None or w["x0"] > end:
            if end is not None:
                total += end - start
            start, end = w["x0"], w["x1"]
        else:
            end = max(end, w["x1"])
    if end is not None:
        total += end - start
    return total


def _overlap_ratio(a: dict, b: dict) -> float:
    inter = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
    shorter = min(a["x1"] - a["x0"], b["x1"] - b["x0"])
    return inter / shorter if shorter > 0 and inter > 0 else 0.0


def _strip_separators(text: str) -> str:
    return text.strip("".join(_SEPARATORS))


def _build_candidates(words: list[dict], text_width: float) -> list[tuple[str, float, str]]:
    """한 전처리 패스의 단어들로 (후보, 점수, 출처) 목록."""
    if text_width <= 0:
        return []
    usable = [w for w in words if w["text"] and w["conf"] >= MIN_WORD_CONF]
    candidates = []

    def add(chosen: list[dict], source: str) -> None:
        text = _strip_separators("".join(w["text"] for w in chosen))
        if text:
            conf = sum(w["conf"] for w in chosen) / len(chosen)
            coverage = min(1.0, _span(chosen) / text_width)
            candidates.append((text, conf * coverage, source))

    # 단일 언어 후보
    for lang in OCR_LANGS:
        lang_words = [w for w in usable if w["lang"] == lang]
        if lang_words:
            add(lang_words, lang)

    # 병합 후보. 한글 후보(eng + kor + 한자 언어팩이 읽은 영문 단어)와
    # 한자 후보(eng + 한자 언어팩 하나)를 따로 만듦
    pools = {}
    for cjk_lang in _CJK_LANGS:
        cjk_latin = [w for w in usable if w["lang"] == cjk_lang and all(_is_latin(ch) for ch in w["text"])]
        pools[f"hangul-{cjk_lang}"] = [w for w in usable if w["lang"] in ("eng", "kor")] + cjk_latin
        pools[cjk_lang] = [w for w in usable if w["lang"] in ("eng", cjk_lang)]
    for pool_name, pool in pools.items():
        chosen: list[dict] = []
        for w in sorted(pool, key=lambda w: w["conf"], reverse=True):
            if all(_overlap_ratio(w, c) < 0.3 for c in chosen):
                chosen.append(w)
        if chosen and len({w["lang"] for w in chosen}) >= 2:
            add(sorted(chosen, key=lambda w: w["x0"]), f"merged-{pool_name}")

    return candidates


def _cjk_consensus(words_by_pass: dict) -> str:
    """한자/가나 언어팩이 읽은 글자를 x 위치로 묶어, 위치마다 가장 많이 나온 글자로
    만든 문자열. 획 많은 한자는 매번 다른 비슷한 글자로, 낮은 신뢰도로 읽혀 일반
    후보에서는 통째로 빠지기 쉬움 ('藤田皮卡丘' -> '田皮卡丘')."""
    chars = []  # (x 중심, 글자 폭, 글자, 가중치)
    for words in words_by_pass.values():
        for w in words:
            if w["lang"] not in _CJK_LANGS:
                continue
            glyphs = [ch for ch in w["raw"] if _is_cjk(ch) or _is_kana(ch)]
            if not glyphs or len(glyphs) != len(w["raw"]):
                continue  # 영문이 섞인 단어는 글자 위치를 나눌 수 없음
            step = (w["x1"] - w["x0"]) / len(glyphs)
            if step <= 0:
                continue
            for i, ch in enumerate(glyphs):
                chars.append((w["x0"] + step * (i + 0.5), step, ch, w["conf"] + 10))

    clusters: list[dict] = []
    for x, width, ch, weight in sorted(chars):
        if clusters and x - clusters[-1]["x"] < width * 0.5:
            c = clusters[-1]
            c["n"] += 1
            c["x"] += (x - c["x"]) / c["n"]
        else:
            c = {"x": x, "n": 1, "votes": {}}
            clusters.append(c)
        c["votes"][ch] = c["votes"].get(ch, 0) + weight

    return "".join(max(c["votes"], key=c["votes"].get) for c in clusters if c["n"] >= MIN_POSITION_VOTES)


def _is_junk(text: str) -> bool:
    """UI 선/테두리를 읽은 듯한 후보 ('一一一一', '||'). 이런 닉네임의 실제 유저가
    있어 다른 사람이 확정될 수 있으므로 후보에서 뺌."""
    if not text:
        return True
    if len(text) >= 2 and len(set(text)) == 1:
        return True
    return all(ch in _LINE_LIKE_CHARS for ch in text)


def _dedupe_consecutive(s: str) -> str:
    """연속 중복 글자 축소 ('yaa' -> 'ya'). 진짜 중복('sooin')을 망칠 수 있어 보조 후보로만 씀."""
    out = []
    for ch in s:
        if not out or out[-1] != ch:
            out.append(ch)
    return "".join(out)


def _separator_alternatives(s: str) -> list[str]:
    """'|'와 '丨'은 화면에서 구분이 안 되므로 서로 바꾼 후보."""
    alts = []
    if "|" in s:
        alts.append(s.replace("|", "丨"))
    if "丨" in s:
        alts.append(s.replace("丨", "|"))
    return alts


def lookalike_variants(text: str, limit: int = 8) -> list[str]:
    """CONFUSABLE_GROUPS 안에서 글자를 바꾼 변형들 (원문 제외, 최대 limit개)."""
    variants = [text]
    for i in (i for i, ch in enumerate(text) if ch in _CONFUSABLE):
        expanded = [v[:i] + alt + v[i + 1 :] for v in variants for alt in _CONFUSABLE[v[i]]]
        variants = list(dict.fromkeys(expanded))[: limit + 1]
    return [v for v in variants if v != text][:limit]


def _empty_result() -> dict:
    return {"best": "", "best_source": "", "confidence": 0.0, "candidates": [], "candidate_scores": {}}


def _rank_candidates(words_by_pass: dict) -> dict:
    """패스별 단어들로 후보를 만들어 점수순으로 정리."""
    scores: dict[str, float] = {}
    sources: dict[str, str] = {}
    hits: dict[str, int] = {}
    for p, words in words_by_pass.items():
        text_width = _span([w for w in words if w["conf"] >= MIN_WORD_CONF]) or _span(words)
        for text, score, src in _build_candidates(words, text_width):
            if _is_junk(text):
                continue
            hits[text] = hits.get(text, 0) + 1
            if score > scores.get(text, -1):
                scores[text] = score
                sources[text] = f"{src}@x{p[0]}{'' if p[1] == 'soft' else '-' + p[1]}"
    # 여러 패스/언어에서 같은 결과가 나오면 보너스
    for text in scores:
        scores[text] += min(hits[text] - 1, 5) * 2

    # 보조 후보 (원래 후보보다 낮은 점수)
    for text in list(scores):
        for alt in [_dedupe_consecutive(text), *_separator_alternatives(text)]:
            if alt and alt not in scores and not _is_junk(alt):
                scores[alt] = scores[text] - 10
                sources[alt] = sources[text] + "+alt"

    # 한자 위치별 투표 후보: 1등보다 약간 낮게, 단 API 조회 대상이 되는 점수 이상
    consensus = _cjk_consensus(words_by_pass)
    if len(consensus) >= 2 and not _is_junk(consensus) and consensus not in scores:
        scores[consensus] = max(MIN_CONSENSUS_SCORE, max(scores.values(), default=0) - 5)
        sources[consensus] = "cjk-consensus"

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
    }


def _run_ocr(crop: Image.Image) -> dict:
    """닉네임 칸 하나의 OCR 결과.

    반환: {"best", "best_source", "confidence"(0~100), "candidates"(점수순), "candidate_scores"}
    """
    crop = _trim_edge_columns(crop)
    if _text_pixel_ratio(crop) < MIN_TEXT_PIXEL_RATIO:
        return _empty_result()

    size_factor = OCR_REFERENCE_CROP_HEIGHT / max(1, crop.height)
    effective = {p: p[0] * size_factor for p in OCR_PASSES}
    images = {p: _preprocess(crop, effective[p], p[1]) for p in OCR_PASSES}

    def run(jobs: list[tuple]) -> dict:
        words_by_pass: dict = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [(p, pool.submit(_ocr_words, images[p], lang, effective[p])) for p, lang in jobs]
            for p, fut in futures:
                words_by_pass.setdefault(p, []).extend(fut.result())
        return words_by_pass

    fast_jobs = [(FAST_PASS, lang) for lang in FAST_LANGS]
    fast_words = run(fast_jobs)
    fast = _rank_candidates(fast_words)
    if fast["best"] and fast["candidate_scores"][fast["best"]] >= FAST_ACCEPT_SCORE:
        return fast

    words_by_pass = run([(p, lang) for p in OCR_PASSES for lang in OCR_LANGS if (p, lang) not in fast_jobs])
    for p, words in fast_words.items():
        words_by_pass.setdefault(p, []).extend(words)
    return _rank_candidates(words_by_pass)


# --- 공개 함수 -----------------------------------------------------------------


def ocr_crops(crops: list[Image.Image]) -> list[dict]:
    """닉네임 칸 이미지들의 OCR 결과. 각 결과에 "name"과 원본 "crop_image"를 포함."""
    return [
        {"name": region["name"], **_run_ocr(crop), "crop_image": crop}
        for region, crop in zip(NAME_REGIONS_REF, crops)
    ]


def get_teammate_ocr_results() -> list[dict]:
    """지금 게임 화면의 팀원 닉네임 OCR 결과 (NAME_REGIONS_REF 순서)."""
    return ocr_crops(capture_crops())


def get_teammate_ocr_results_from_image(image_path: str) -> list[dict]:
    """저장된 스크린샷으로 get_teammate_ocr_results()와 같은 결과를 만듭니다."""
    return ocr_crops(crops_from_image(image_path))
