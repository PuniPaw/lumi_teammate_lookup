"""
플레이어 전적 조회 (Open API): 티어, 시즌 통계, 최근 게임 통계 (ports.StatsProvider).

모달에 넘기는 전적 dict를 만듭니다. 조회에 실패한 팀원은 failed_stats()로
'조회 실패' dict를 만들어, 모달에서 닉네임을 고쳐 재조회할 수 있게 합니다.
"""

from typing import Callable, Optional

from bserpy import Client
from bserpy.utils import SeasonHelper

from lumi.api.recent_stats import RECENT_GAME_COUNT, empty_recent_stats, format_recent_stats, get_recent_stats
from lumi.api.resolve import resolve_teammate_names

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


def current_season_id(client) -> Optional[int]:
    season = SeasonHelper(client).current_season()
    return season["seasonID"] if season else None


def fetch_user_stats(client, nickname: str, season_id: int, character_names: dict[int, str]) -> dict:
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
                    top_character=character_names.get(most.character_code, f"코드{most.character_code}"),
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


class EternalReturnStats:
    """ports.StatsProvider 구현 (이터널 리턴 Open API)."""

    def __init__(self, api_key: str, client_factory: Callable = Client):
        self._api_key = api_key
        self._client_factory = client_factory
        self.character_names: dict[int, str] = {}

    def _client(self):
        return self._client_factory(api_key=self._api_key)

    def load_character_names(self) -> None:
        """캐릭터 코드 -> 한글 이름(없으면 영문 이름). 실패하면 RuntimeError."""
        try:
            with self._client() as client:
                characters = client.meta.get_data("Character")
                l10n = client.meta.get_l10n_parsed()
        except Exception as e:
            raise RuntimeError(f"캐릭터 이름 로드 실패: {e}") from e
        for char in characters:
            code = char.get("code")
            name = l10n.get_character_name(code) or char.get("name")
            if code and name:
                self.character_names[code] = name
        if not self.character_names:
            raise RuntimeError("캐릭터 이름 데이터가 비어 있습니다.")
        print(f"✅ 캐릭터 이름 {len(self.character_names)}개 로드 완료")

    def team_stats(self, ocr_results: list[dict]) -> list[dict]:
        """확정하지 못한 칸도 OCR이 읽은 글자로 '조회 실패' 카드를 만듭니다."""
        with self._client() as client:
            season_id = current_season_id(client)
            team = []
            for ocr, resolved in zip(ocr_results, resolve_teammate_names(client, ocr_results)):
                nickname = resolved["resolved_nickname"]
                if nickname and season_id is not None:
                    try:
                        team.append(fetch_user_stats(client, nickname, season_id, self.character_names))
                        continue
                    except Exception as e:
                        print(f"  '{nickname}' 전적 조회 실패: {e!r}")
                fallback = nickname or ocr.get("best") or ""
                if fallback:
                    team.append(failed_stats(fallback))
            return team

    def user_stats(self, nickname: str) -> Optional[dict]:
        if not nickname.strip():
            return None
        try:
            with self._client() as client:
                season_id = current_season_id(client)
                return fetch_user_stats(client, nickname, season_id, self.character_names) if season_id else None
        except Exception as e:
            print(f"재조회 실패: {e!r}")
            return None
