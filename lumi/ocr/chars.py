"""문자 종류 판별과 언어팩별로 신뢰하는 문자."""


def is_hangul(ch: str) -> bool:
    return "가" <= ch <= "힣"


def is_kana(ch: str) -> bool:
    return "぀" <= ch <= "ヿ" or "ㇰ" <= ch <= "ㇿ" or "ｦ" <= ch <= "ﾟ"


def is_cjk(ch: str) -> bool:
    return "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿"


def is_latin(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


SEPARATORS = set("|丨_-")  # 닉네임 안의 구분자 ('静戒丨BS')
LINE_LIKE_CHARS = set("一丨|-_ー—−")  # UI의 선을 글자로 읽은 결과에 자주 나옴 ('−'는 PP-OCR)

OCR_LANGS = ["eng", "kor", "jpn", "chi_sim", "chi_tra"]
CJK_LANGS = ["jpn", "chi_sim", "chi_tra"]

# 언어팩마다 담당 문자 체계만 신뢰 (예: kor는 영문을 숫자로 읽음 'sooin' -> '50010')
LANG_CHAR_FILTERS = {
    "eng": lambda ch: is_latin(ch) or ch in SEPARATORS,
    "kor": is_hangul,
    "jpn": lambda ch: is_kana(ch) or is_cjk(ch),
    "chi_sim": is_cjk,
    "chi_tra": is_cjk,
}

# 한자/가나 언어팩은 영문 단어도 잘 읽어서('ya'를 eng는 0~50, jpn은 70~90),
# 단어 전체가 영문/숫자면 신뢰도를 조금 깎아 사용
LATIN_TRUSTED_LANGS = {"jpn", "chi_sim", "chi_tra"}
LATIN_CONF_PENALTY = 0.9
