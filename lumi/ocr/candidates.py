"""OCR 후보 공통 처리: 잡음 후보 판별, 빈 결과, 헷갈리는 글자 변형."""

from lumi.ocr.chars import LINE_LIKE_CHARS

# 작은 화면에서 서로 헷갈리는 글자 묶음 (관찰된 것만). 일반 후보로 유저를 못 찾았을
# 때 이 안에서 글자를 바꿔 다시 조회함 (api.resolve)
CONFUSABLE_GROUPS = [
    "藤騰滕腾朋县",
    "静靜",  # 간체/신자체 vs 번체
    "丨|",
]
_CONFUSABLE = {ch: group for group in CONFUSABLE_GROUPS for ch in group}


def is_junk(text: str) -> bool:
    """UI 선/테두리를 읽은 듯한 후보 ('一一一一', '||'). 이런 닉네임의 실제 유저가
    있어 다른 사람이 확정될 수 있으므로 후보에서 뺌."""
    if not text:
        return True
    if len(text) >= 2 and len(set(text)) == 1:
        return True
    return all(ch in LINE_LIKE_CHARS for ch in text)


def lookalike_variants(text: str, limit: int = 8) -> list[str]:
    """CONFUSABLE_GROUPS 안에서 글자를 바꾼 변형들 (원문 제외, 최대 limit개)."""
    variants = [text]
    for i in (i for i, ch in enumerate(text) if ch in _CONFUSABLE):
        expanded = [v[:i] + alt + v[i + 1 :] for v in variants for alt in _CONFUSABLE[v[i]]]
        variants = list(dict.fromkeys(expanded))[: limit + 1]
    return [v for v in variants if v != text][:limit]


def empty_result() -> dict:
    """OCR 결과 형식: {"best", "best_source", "confidence"(0~100), "candidates"(점수순), "candidate_scores"}"""
    return {"best": "", "best_source": "", "confidence": 0.0, "candidates": [], "candidate_scores": {}}
