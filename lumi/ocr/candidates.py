"""
OCR 단어들 -> 점수순 닉네임 후보.

  - 단일 언어 후보
  - 병합 후보: 신뢰도 높은 단어부터 위치가 겹치지 않게 골라 x 순서로 연결.
    한글과 한자/가나는 한 후보에 섞지 않음
  - 한자 위치별 투표 후보: 신뢰도가 낮은 한자도 위치마다 가장 많이 나온 글자로
  점수 = 평균 신뢰도 x 커버리지(글자 영역 중 후보가 설명하는 비율)
"""

from lumi.ocr.chars import CJK_LANGS, LINE_LIKE_CHARS, OCR_LANGS, SEPARATORS, is_cjk, is_kana, is_latin

# 후보 조립에 쓸 단어의 최소 신뢰도 (0~100)
MIN_WORD_CONF = 45

# 한자 위치별 투표: 한 위치로 인정할 최소 득표 수, 투표 후보의 최소 점수
MIN_POSITION_VOTES = 2
MIN_CONSENSUS_SCORE = 60

# 작은 화면에서 서로 헷갈리는 글자 묶음 (관찰된 것만). 일반 후보로 유저를 못 찾았을
# 때 이 안에서 글자를 바꿔 다시 조회함 (api.resolve)
CONFUSABLE_GROUPS = [
    "藤騰滕腾朋",
    "静靜",  # 간체/신자체 vs 번체
    "丨|",
]
_CONFUSABLE = {ch: group for group in CONFUSABLE_GROUPS for ch in group}


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
    return text.strip("".join(SEPARATORS))


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

    for lang in OCR_LANGS:
        lang_words = [w for w in usable if w["lang"] == lang]
        if lang_words:
            add(lang_words, lang)

    # 한글 후보(eng + kor + 한자 언어팩이 읽은 영문 단어)와 한자 후보(eng + 한자 언어팩 하나)를
    # 따로 만듦. jpn과 chi를 섞으면 가나 자리에 엉뚱한 한자가 끼어듦
    pools = {}
    for cjk_lang in CJK_LANGS:
        cjk_latin = [w for w in usable if w["lang"] == cjk_lang and all(is_latin(ch) for ch in w["text"])]
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
            if w["lang"] not in CJK_LANGS:
                continue
            glyphs = [ch for ch in w["raw"] if is_cjk(ch) or is_kana(ch)]
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


def is_junk(text: str) -> bool:
    """UI 선/테두리를 읽은 듯한 후보 ('一一一一', '||'). 이런 닉네임의 실제 유저가
    있어 다른 사람이 확정될 수 있으므로 후보에서 뺌."""
    if not text:
        return True
    if len(text) >= 2 and len(set(text)) == 1:
        return True
    return all(ch in LINE_LIKE_CHARS for ch in text)


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


def empty_result() -> dict:
    return {"best": "", "best_source": "", "confidence": 0.0, "candidates": [], "candidate_scores": {}}


def rank_candidates(words_by_pass: dict) -> dict:
    """패스별 단어들로 후보를 만들어 점수순으로 정리.

    반환: {"best", "best_source", "confidence"(0~100), "candidates"(점수순), "candidate_scores"}
    """
    scores: dict[str, float] = {}
    sources: dict[str, str] = {}
    hits: dict[str, int] = {}
    for p, words in words_by_pass.items():
        text_width = _span([w for w in words if w["conf"] >= MIN_WORD_CONF]) or _span(words)
        for text, score, src in _build_candidates(words, text_width):
            if is_junk(text):
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
            if alt and alt not in scores and not is_junk(alt):
                scores[alt] = scores[text] - 10
                sources[alt] = sources[text] + "+alt"

    # 한자 위치별 투표 후보: 1등보다 약간 낮게, 단 API 조회 대상이 되는 점수 이상
    consensus = _cjk_consensus(words_by_pass)
    if len(consensus) >= 2 and not is_junk(consensus) and consensus not in scores:
        scores[consensus] = max(MIN_CONSENSUS_SCORE, max(scores.values(), default=0) - 5)
        sources[consensus] = "cjk-consensus"

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
