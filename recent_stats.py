"""
최근 N게임 기준 통계 (평균 딜량, 평균 TK)를 계산하는 모듈.

- 평균 딜량: 게임마다 '다른 플레이어 캐릭터에게 가한 총 피해량'
  (Open API의 damageToPlayer)의 평균
- 평균 TK : 게임마다 '팀 킬 수'(Open API의 teamKill, 그 게임에서 팀 전체가
  올린 킬 수)의 평균

Open API의 /v1/user/games/uid/{userId}는 한 번에 최근 경기 일부만 주고
응답의 'next' 값으로 다음 페이지를 이어서 받는 방식이라, 원하는 게임 수가
모일 때까지 여러 페이지를 조회합니다.

단독 실행 (닉네임 하나 조회): python recent_stats.py 닉네임
"""

import os
import sys
from typing import Optional

# 최근 몇 게임을 기준으로 평균을 낼지
RECENT_GAME_COUNT = 20

# 평균에 포함할 매칭 모드. 2=일반(스쿼드), 3=랭크(스쿼드).
# 코발트 프로토콜(6) 등은 게임 구조가 달라 딜량/킬 수 기준이 크게 다르므로
# 기본적으로 제외합니다. 모든 모드를 포함하려면 None으로 두세요.
RECENT_GAME_MODES: Optional[set[int]] = {2, 3}

# 원하는 게임 수가 안 모여도 이 페이지 수까지만 조회 (API 호출 수 제한)
MAX_PAGES = 5


def fetch_recent_games(
    client,
    user_id,
    count: int = RECENT_GAME_COUNT,
    modes: Optional[set[int]] = RECENT_GAME_MODES,
    max_pages: int = MAX_PAGES,
) -> list[dict]:
    """최근 경기 목록(원본 JSON dict)을 최신순으로 최대 count개 반환합니다.

    bserpy의 client.users.get_games()는 첫 페이지만 가져오기 때문에,
    'next' 커서를 따라가기 위해 같은 엔드포인트를 직접 호출합니다.
    (모델 객체 대신 원본 dict를 쓰는 이유: 모드에 따라 일부 필드가 빠진
     응답도 있어서, 필요한 필드만 안전하게 꺼내 쓰기 위함)
    """
    transport = client.users._t
    games: list[dict] = []
    seen_game_ids: set = set()
    next_cursor = None

    for _ in range(max_pages):
        data = transport.get(f"/v1/user/games/uid/{user_id}", next=next_cursor)
        for game in data.get("userGames") or []:
            game_id = game.get("gameId")
            if game_id in seen_game_ids:
                continue
            seen_game_ids.add(game_id)
            if modes is not None and game.get("matchingMode") not in modes:
                continue
            games.append(game)

        next_cursor = data.get("next")
        if len(games) >= count or not next_cursor:
            break

    return games[:count]


def summarize_recent_games(games: list[dict]) -> dict:
    """경기 목록으로 평균 딜량/평균 TK를 계산합니다.

    반환: {"recent_games": 경기 수,
           "avg_damage_to_player": float 또는 None (경기가 없으면),
           "avg_team_kill": float 또는 None}
    """
    n = len(games)
    if n == 0:
        return {"recent_games": 0, "avg_damage_to_player": None, "avg_team_kill": None}

    total_damage = sum(g.get("damageToPlayer") or 0 for g in games)
    total_team_kill = sum(g.get("teamKill") or 0 for g in games)
    return {
        "recent_games": n,
        "avg_damage_to_player": total_damage / n,
        "avg_team_kill": total_team_kill / n,
    }


def get_recent_stats(client, user_id, count: int = RECENT_GAME_COUNT) -> dict:
    """fetch + summarize를 한 번에. 조회 실패 시 예외를 그대로 던집니다."""
    return summarize_recent_games(fetch_recent_games(client, user_id, count=count))


def empty_recent_stats() -> dict:
    """조회 실패 등으로 값이 없을 때 쓰는 기본값."""
    return summarize_recent_games([])


def format_recent_stats(stats: dict) -> str:
    """오버레이에 표시할 한 줄 문자열을 만듭니다.

    예: '최근 20게임  ·  평균 딜량 12,345  ·  평균 TK 6.2'
    """
    n = stats.get("recent_games") or 0
    if n == 0:
        return "최근 게임 기록 없음"
    damage = stats.get("avg_damage_to_player")
    team_kill = stats.get("avg_team_kill")
    parts = [f"최근 {n}게임"]
    if damage is not None:
        parts.append(f"평균 딜량 {damage:,.0f}")
    if team_kill is not None:
        parts.append(f"평균 TK {team_kill:.1f}")
    return "  ·  ".join(parts)


def main():
    from dotenv import load_dotenv
    from bserpy import Client

    load_dotenv()
    api_key = os.getenv("ETERNAL_RETURN_API_KEY")
    if not api_key:
        print("ETERNAL_RETURN_API_KEY가 설정되지 않았습니다. .env를 확인하세요.")
        return
    if len(sys.argv) < 2:
        print("사용법: python recent_stats.py 닉네임")
        return

    nickname = sys.argv[1]
    with Client(api_key=api_key) as client:
        user = client.users.get_uid(nickname)
        stats = get_recent_stats(client, user.user_id)
    print(f"{nickname}: {format_recent_stats(stats)}")
    print(stats)


if __name__ == "__main__":
    main()
