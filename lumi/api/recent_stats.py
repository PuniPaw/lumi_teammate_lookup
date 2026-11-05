"""
최근 N게임 통계: 평균 딜량(damageToPlayer, 다른 플레이어에게 가한 총 피해량)과
평균 TK(teamKill, 그 게임에서 팀 전체가 올린 킬 수).
"""

from typing import Optional

RECENT_GAME_COUNT = 20
# 포함할 매칭 모드: 2=일반, 3=랭크. 코발트(6) 등은 딜량/킬 기준이 달라 제외. None이면 전체.
RECENT_GAME_MODES: Optional[set[int]] = {2, 3}
# 게임 수가 안 모여도 이 페이지 수까지만 조회
MAX_PAGES = 5


def fetch_recent_games(
    client,
    user_id,
    count: int = RECENT_GAME_COUNT,
    modes: Optional[set[int]] = RECENT_GAME_MODES,
    max_pages: int = MAX_PAGES,
) -> list[dict]:
    """최근 경기(원본 JSON dict)를 최신순으로 최대 count개.

    bserpy의 get_games()는 첫 페이지만 주므로 'next' 커서를 따라 같은 엔드포인트를
    직접 호출합니다. 모드에 따라 필드가 빠진 응답이 있어 모델 대신 dict를 씁니다.
    """
    games: list[dict] = []
    seen: set = set()
    cursor = None
    for _ in range(max_pages):
        data = client.users._t.get(f"/v1/user/games/uid/{user_id}", next=cursor)
        for game in data.get("userGames") or []:
            if game.get("gameId") in seen:
                continue
            seen.add(game.get("gameId"))
            if modes is None or game.get("matchingMode") in modes:
                games.append(game)
        cursor = data.get("next")
        if len(games) >= count or not cursor:
            break
    return games[:count]


def summarize_recent_games(games: list[dict]) -> dict:
    """{"recent_games", "avg_damage_to_player", "avg_team_kill"} (경기가 없으면 평균은 None)."""
    n = len(games)
    if n == 0:
        return {"recent_games": 0, "avg_damage_to_player": None, "avg_team_kill": None}
    return {
        "recent_games": n,
        "avg_damage_to_player": sum(g.get("damageToPlayer") or 0 for g in games) / n,
        "avg_team_kill": sum(g.get("teamKill") or 0 for g in games) / n,
    }


def get_recent_stats(client, user_id, count: int = RECENT_GAME_COUNT) -> dict:
    return summarize_recent_games(fetch_recent_games(client, user_id, count=count))


def empty_recent_stats() -> dict:
    return summarize_recent_games([])


def format_recent_stats(stats: dict) -> str:
    """예: '최근 20게임  ·  평균 딜량 12,345  ·  평균 TK 6.2'"""
    n = stats.get("recent_games") or 0
    if n == 0:
        return "최근 게임 기록 없음"
    parts = [f"최근 {n}게임"]
    if stats.get("avg_damage_to_player") is not None:
        parts.append(f"평균 딜량 {stats['avg_damage_to_player']:,.0f}")
    if stats.get("avg_team_kill") is not None:
        parts.append(f"평균 TK {stats['avg_team_kill']:.1f}")
    return "  ·  ".join(parts)
