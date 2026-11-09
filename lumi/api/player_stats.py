"""
플레이어 전적 조회 (Open API): 티어, 시즌 통계, 최근 게임 통계 (ports.StatsProvider).

모달에 넘기는 전적 dict를 만듭니다. 조회에 실패한 팀원은 failed_stats()로
'조회 실패' dict를 만들어, 모달에서 닉네임을 고쳐 재조회할 수 있게 합니다.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from bserpy import AuthenticationError, RateLimitError, ServerError, TransportError
from bserpy.utils import SeasonHelper

from lumi.api.client import ClientFactory
from lumi.api.recent_stats import RECENT_GAME_COUNT, empty_recent_stats, format_recent_stats, get_recent_stats
from lumi.api.resolve import resolve_teammate_names

FAILED_TIER = "조회 실패"
# 모달을 먼저 띄우고 단계별로 채움: 'stage'가 없으면 다 받은 전적
STAGE_LOOKUP = "lookup"  # 닉네임만 있음 (유저/랭크/시즌 조회 중)
STAGE_RECENT = "recent"  # 랭크와 시즌 통계까지 받음 (최근 게임 조회 중)
# (팀원 위치, 그때까지의 전적 dict). 조회 스레드에서 불림
TeamUpdate = Callable[[int, dict], None]
_API_FAILURES = (AuthenticationError, RateLimitError, ServerError, TransportError)

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
        "tier": FAILED_TIER,
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


def pending_stats(nickname: str) -> dict:
    """아직 조회하지 않은 팀원 (모달에 닉네임과 '조회 중'만 표시)."""
    return dict(failed_stats(nickname), stage=STAGE_LOOKUP)


def current_season_id(client) -> Optional[int]:
    season = SeasonHelper(client).current_season()
    return season["seasonID"] if season else None


def fetch_user_stats(
    client,
    nickname: str,
    season_id: int,
    character_names: dict[int, str],
    user_id: Optional[str] = None,
    on_partial: Optional[Callable[[dict], None]] = None,
    multi_weapon: frozenset[int] = frozenset(),
) -> dict:
    """닉네임 한 명의 전적 dict. 유저가 없으면 예외, 세부 조회 실패는 기본값으로 채움.

    user_id: 닉네임을 확정할 때 이미 얻었으면 넘겨서 같은 조회를 또 하지 않음.
    on_partial: 랭크와 시즌 통계를 받은 직후 (stage=STAGE_RECENT) 한 번 불림. 최근 게임은 페이지를
    여러 번 넘겨 오래 걸려서, 그 전에 모달에 티어부터 보여줌.
    multi_weapon: 무기를 여러 종류 쓸 수 있는 캐릭터 코드 (이 캐릭터만 무기 이름을 붙임).
    """
    if user_id is None:
        user_id = client.users.get_uid(nickname).user_id
    stats = failed_stats(nickname)
    stats.update(user_id=str(user_id), season_id=season_id, tier="언랭크")

    try:
        mmr = client.users.get_rank(user_id, season_id=season_id).mmr
        stats.update(mmr=mmr, tier=tier_name(mmr))
    except _API_FAILURES as e:
        stats["tier"] = FAILED_TIER
        print(f"  {nickname}: 랭크 조회 실패 ({e!r})")
    except Exception as e:  # 랭크 기록이 없으면 라이브러리가 KeyError 등을 냄
        print(f"  {nickname}: 랭크 기록 없음 ({e!r}) -> 언랭크")

    season_most: list[tuple[int, int]] = []  # 시즌 모스트 (캐릭터 코드, 시즌 판수), 판수 순
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
            most = sorted(season.character_stats or [], key=lambda c: -c.total_games)
            season_most = [(c.character_code, c.total_games) for c in most]
    except Exception as e:
        stats["games"] = None  # 0은 '시즌 기록 없음'이라 조회 실패와 구분함
        print(f"  {nickname}: 시즌 통계 조회 실패 ({e!r})")

    if on_partial is not None:
        on_partial(dict(stats, stage=STAGE_RECENT))

    try:
        # 시즌 랭크가 RECENT_GAME_COUNT보다 적으면 그 판수만큼만 찾음 (시즌 통계를 못 받았으면 RECENT_GAME_COUNT)
        season_games = stats["games"]
        count = RECENT_GAME_COUNT if season_games is None else min(RECENT_GAME_COUNT, season_games)
        # 캐릭터는 시즌 모스트에서, 숫자는 최근 게임에서 (시즌 통계를 못 받았으면 최근 게임에서 많이 한 순)
        stats.update(
            get_recent_stats(
                client, user_id, character_names, count=count, season_id=season_id, season_most=season_most,
                multi_weapon=multi_weapon,
            )
        )
    except Exception as e:
        stats["recent_games"] = None  # 0은 '기록 없음'이라 조회 실패와 구분함
        print(f"  {nickname}: 최근 게임 조회 실패 ({e!r})")

    print(
        f"  {nickname}: {stats['tier']}, 승률 {stats['top1']:.0f}% ({stats['games']}판), "
        + format_recent_stats(stats).replace("\n", " / ")
    )
    return stats


class EternalReturnStats:
    """ports.StatsProvider 구현 (이터널 리턴 Open API, 직접 또는 프록시로: api.client)."""

    def __init__(self, client_factory: ClientFactory):
        self._client = client_factory
        self.character_names: dict[int, str] = {}
        self.multi_weapon: frozenset[int] = frozenset()

    def load_character_names(self) -> None:
        """캐릭터 코드 -> 한글 이름(없으면 영문 이름)과 무기를 여러 종류 쓰는 캐릭터. 이름을 못 받으면 RuntimeError."""
        try:
            with self._client() as client:
                characters = client.meta.get_data("Character")
                l10n = client.meta.get_l10n_parsed()
        except Exception as e:
            raise RuntimeError(f"캐릭터 이름 로드 실패: {e}") from e
        self.multi_weapon = self._load_multi_weapon()
        for char in characters:
            code = char.get("code")
            name = l10n.get_character_name(code) or char.get("name")
            if code and name:
                self.character_names[code] = name
        if not self.character_names:
            raise RuntimeError("캐릭터 이름 데이터가 비어 있습니다.")
        print(f"✅ 캐릭터 이름 {len(self.character_names)}개 로드 완료")

    def _load_multi_weapon(self) -> frozenset[int]:
        """무기를 여러 종류 쓸 수 있는 캐릭터 코드. 못 받으면 빈 집합 (툴팁에 무기 이름만 안 붙음)."""
        try:
            with self._client() as client:
                mastery = client.meta.get_data("CharacterMastery")
        except Exception as e:
            print(f"캐릭터별 무기 로드 실패, 무기 이름 없이 표시: {e!r}")
            return frozenset()
        # weapon1~4 중 안 쓰는 칸은 'None'
        return frozenset(
            row["code"] for row in mastery if sum(row.get(f"weapon{i}") not in (None, "None") for i in range(1, 5)) > 1
        )

    def team_stats(self, ocr_results: list[dict], on_update: Optional[TeamUpdate] = None) -> list[dict]:
        """확정하지 못한 칸도 OCR이 읽은 글자로 '조회 실패' 카드를 만듭니다.

        팀원을 동시에 조회합니다. 프록시를 거치면 요청 하나가 오래 걸려(docs/DEVELOPMENT_NOTES.md)
        순서대로 조회하면 모달이 너무 늦게 뜸. 결과 순서는 ocr_results와 같음.
        on_update(ocr_results 안의 위치, 전적): 랭크·시즌을 받았을 때와 다 받았을 때 팀원마다 불림.
        """
        if not ocr_results:
            return []
        with self._client() as client:
            season_id = current_season_id(client)
        with ThreadPoolExecutor(max_workers=len(ocr_results)) as pool:
            team = list(
                pool.map(
                    lambda item: self._teammate_stats(item[0], item[1], season_id, on_update), enumerate(ocr_results)
                )
            )
        return [stats for stats in team if stats is not None]

    def _teammate_stats(
        self, index: int, ocr: dict, season_id: Optional[int], on_update: Optional[TeamUpdate]
    ) -> Optional[dict]:
        """팀원 한 명 (스레드마다 Client를 따로 씀). 읽은 글자도 없는 빈 칸이면 None."""
        nickname = None
        result = None
        partial = (lambda stats: on_update(index, stats)) if on_update else None
        try:
            with self._client() as client:
                resolved = resolve_teammate_names(client, [ocr])[0]
                nickname = resolved["resolved_nickname"]
                if nickname and season_id is not None:
                    result = fetch_user_stats(
                        client, nickname, season_id, self.character_names, resolved["user_id"], on_partial=partial,
                        multi_weapon=self.multi_weapon,
                    )
        except Exception as e:  # 한 명이 실패해도 나머지 팀원은 보여줌
            print(f"  '{nickname or ocr.get('best')}' 전적 조회 실패: {e!r}")
        if result is None:
            fallback = nickname or ocr.get("best") or ""
            result = failed_stats(fallback) if fallback else None
        if result is not None and on_update is not None:
            on_update(index, result)
        return result

    def user_stats(self, nickname: str) -> Optional[dict]:
        if not nickname.strip():
            return None
        try:
            with self._client() as client:
                season_id = current_season_id(client)
                if not season_id:
                    return None
                return fetch_user_stats(client, nickname, season_id, self.character_names, multi_weapon=self.multi_weapon)
        except Exception as e:
            print(f"재조회 실패: {e!r}")
            return None
