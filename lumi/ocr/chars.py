"""문자 종류 판별."""


def is_hangul(ch: str) -> bool:
    return "가" <= ch <= "힣"


def is_kana(ch: str) -> bool:
    return "぀" <= ch <= "ヿ" or "ㇰ" <= ch <= "ㇿ" or "ｦ" <= ch <= "ﾟ"


def is_cjk(ch: str) -> bool:
    return "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿"


LINE_LIKE_CHARS = set("一丨|-_ー—−")  # UI의 선을 글자로 읽은 결과에 자주 나옴 ('−'는 PP-OCR)
