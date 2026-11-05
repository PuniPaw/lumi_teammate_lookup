"""
플레이어 전적 조회 (Open API): 캐릭터 이름, 티어, 시즌 통계, 최근 게임 통계.

모달(overlay.py)에 넘기는 전적 dict를 만듭니다. 조회에 실패한 팀원은
failed_stats()로 '조회 실패' dict를 만들어 모달에서 닉네임을 고쳐 재조회할 수 있게 합니다.
"""

import os
from typing import Optional

from bserpy import Client
from bserpy.utils import SeasonHelper
from dotenv import load_dotenv

from recent_stats import RECENT_GAME_COUNT, empty_recent_stats, format_recent_stats, get_recent_stats
from resolve_teammates import resolve_teammate_names

load_dotenv()
API_KEY = os.getenv("ETERNAL_RETURN_API_KEY")

# 캐릭터 코드 -> 한글 이름 (load_character_names()로 채움)
CHARACTER_NAMES: dict[int, str] = {}

# (최소 MMR, 티어 이름). 위에서부터 처음 만족하는 티어.
TIERS = [
    (8300, "이터니티"),
    (7600, "미스릴"),
    (7300, "메테오라이트 I"), (7000, "메테오라이트 II"), (6700, "메테오라이트 III"), (6400, "메테오라이트 IV"),
    (6050, "다이아몬드 I"), (5700, "다이아몬드 II"), (5350, "다이아몬드 III"), (5000, "다이아몬드 IV"),
    (4650, "플래티넘 I"), (4300, "플래티넘 II"), (3950, "플래티넘 III"), (3400, "플래티넘 IV"),
    (3300, "골드 I"), (3000, "골드 II"), (2700, "골드 III"), (2400, "골드 IV"),
    (2150, "실버 I"), (1900, "실버 II"), (1650, "실버 III"), (1400, "실버 IV"),
    (1200, "브론즈 I"), (1000, "브론즈 II"), (800, "브론즈 III"), (600, "브론즈 IV"),
    (450, "아이언 I"), (300, "아이언 II"), (150, "아이언 III"), (1, "아이언 IV"),
]


def tier_name(mmr: int) -> str:
    for min_mmr, name in TIERS:
        if mmr >= min_mmr:
            return name
    return "언랭크"


def load_character_names() -> None:
    """캐릭터 코드 -> 한글 이름(없으면 영문 이름)을 CHARACTER_NAMES에 채웁니다."""
    if not API_KEY:
        raise RuntimeError("API 키가 없어 캐릭터 이름을 로드할 수 없습니다.")
    try:
        with Client(api_key=API_KEY) as client:
            characters = client.meta.get_data("Character")
            l10n = client.meta.get_l10n_parsed()
    except Exception as e:
        raise RuntimeError(f"캐릭터 이름 로드 실패: {e}") from e

    for char in characters:
        code = char.get("code")
        name = l10n.get_character_name(code) or char.get("name")
        if code and name:
            CHARACTER_NAMES[code] = name
    if not CHARACTER_NAMES:
        raise RuntimeError("캐릭터 이름 데이터가 비어 있습니다.")
    print(f"✅ 캐릭터 이름 {len(CHARACTER_NAMES)}개 로드 완료")


def _character_name(code: int) -> str:
    return CHARACTER_NAMES.get(code, f"코드{code}")


def current_season_id(client: Client) -> Optional[int]:
    season = SeasonHelper(client).current_season()
    return season["seasonID"] if season else None


def failed_stats(nickname: str) -> dict:
    """조회에 실패한 팀원의 전적 dict (모달에 '조회 실패'로 표시됨)."""
    return {
        "nickname": nickname,
        "tier": "조회 실패",
        "top_character": "?",
        "top_character_games": 0,
        "mmr": 0,
        "games": 0,
        "top1": 0,
        "top2": 0,
        "top3": 0,
        "average_rank": 0,
        "user_id": None,
        "season_id": None,
        **empty_recent_stats(),
    }


def fetch_user_stats(client: Client, nickname: str, season_id: int) -> dict:
    """닉네임 한 명의 전적 dict. 유저가 없으면 예외, 세부 조회 실패는 기본값으로 채움."""
    user_id = client.users.get_uid(nickname).user_id
    stats = failed_stats(nickname)
    stats.update(user_id=str(user_id), season_id=season_id, tier="언랭크")

    try:
        mmr = client.users.get_rank(user_id, season_id=season_id).mmr
        stats.update(mmr=mmr, tier=tier_name(mmr))
    except Exception as e:  # 랭크 기록이 없으면 라이브러리가 KeyError 등을 냄
        print(f"  {nickname}: 랭크 조회 실패 ({e!r}) -> 언랭크")

    try:
        season = next(iter(client.users.get_stats(user_id, season_id=season_id)), None)
        if season is not None:
            stats.update(
                games=season.total_games,
                top1=season.top1 * 100,
                top2=season.top2 * 100,
                top3=season.top3 * 100,
                average_rank=round(season.average_rank, 1),
            )
            if season.character_stats:
                most = max(season.character_stats, key=lambda c: c.total_games)
                stats.update(
                    top_character=_character_name(most.character_code),
                    top_character_games=most.total_games,
                )
    except Exception as e:
        print(f"  {nickname}: 시즌 통계 조회 실패 ({e!r})")

    try:
        stats.update(get_recent_stats(client, user_id, count=RECENT_GAME_COUNT))
    except Exception as e:
        print(f"  {nickname}: 최근 게임 조회 실패 ({e!r})")

    print(
        f"  {nickname}: {stats['tier']}, 승률 {stats['top1']:.0f}% ({stats['games']}판), "
        f"모스트 {stats['top_character']} ({stats['top_character_games']}판), {format_recent_stats(stats)}"
    )
    return stats


def fetch_stats_by_nickname(nickname: str) -> Optional[dict]:
    """모달에서 닉네임을 고쳐 Enter를 눌렀을 때의 재조회. 못 찾으면 None."""
    if not nickname.strip() or not API_KEY:
        return None
    try:
        with Client(api_key=API_KEY) as client:
            season_id = current_season_id(client)
            return fetch_user_stats(client, nickname, season_id) if season_id else None
    except Exception as e:
        print(f"재조회 실패: {e!r}")
        return None


def fetch_team_stats(client: Client, ocr_results: list[dict]) -> list[dict]:
    """OCR 결과 -> API로 닉네임 확정 -> 팀원별 전적 dict 목록.

    확정하지 못한 칸도 OCR이 읽은 글자로 '조회 실패' 카드를 만들어 둡니다.
    """
    season_id = current_season_id(client)
    team_stats = []
    for ocr, resolved in zip(ocr_results, resolve_teammate_names(client, ocr_results)):
        nickname = resolved["resolved_nickname"]
        if nickname and season_id is not None:
            try:
                team_stats.append(fetch_user_stats(client, nickname, season_id))
                continue
            except Exception as e:
                print(f"  '{nickname}' 전적 조회 실패: {e!r}")
        fallback = nickname or ocr.get("best") or ""
        if fallback:
            team_stats.append(failed_stats(fallback))
    return team_stats
