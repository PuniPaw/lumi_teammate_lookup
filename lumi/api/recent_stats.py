"""
최근 N게임 캐릭터·무기별 통계: 평균 딜량(damageToPlayer, 다른 플레이어에게 가한 총 피해량)과
평균 TK(teamKill, 그 게임에서 팀 전체가 올린 킬 수).

어떤 캐릭터를 보여줄지는 시즌 통계의 모스트(판수 순)로 정하고, 숫자는 최근 게임 중
그 캐릭터로 한 판만으로 냅니다. 시즌 모스트를 모르면 최근 게임에서 많이 한 순.
무기를 여러 개 쓰는 캐릭터(아야 권총/저격총/돌격소총 등)는 무기마다 한 줄.
"""

from typing import Optional

# 랭크 20판 (시즌 랭크가 더 적으면 그만큼). 일반을 많이 하는 팀원이 있으면 조회가 15~25초 걸리지만
# (10판은 4~9초, 2026-11-08 팀당 1회 측정) 모달을 먼저 띄우고 최근 게임 표를 나중에 채워서 늘림
RECENT_GAME_COUNT = 20
MOST_CHARACTER_COUNT = 5
# 포함할 매칭 모드: 3=랭크만 (2=일반, 6=코발트 등은 제외). 시즌 통계와 티어도 랭크 기준. None이면 전체.
RECENT_GAME_MODES: Optional[set[int]] = {3}
# 게임 수가 안 모여도 이 페이지 수까지만 조회 (한 페이지 약 10게임). 목록에 일반 게임이 섞여 와서
# 일반을 많이 하는 유저는 랭크 20판에 8~9페이지가 필요했음. 늘리면 요청이 늘어 429 위험 (docs/DEVELOPMENT_NOTES.md)
MAX_PAGES = 10
# 게임 기록의 bestWeapon(그 판에 쓴 무기) 코드 -> 이름. 게임의 무기 종류 순서이고 12는 없음.
# 1, 3, 4, 6, 9, 14, 16, 18, 24, 25는 무기가 하나뿐인 캐릭터의 기록과 대조해 확인 (2026-11-09)
WEAPON_NAMES = {
    1: "글러브", 2: "톤파", 3: "방망이", 4: "채찍", 5: "투척", 6: "암기", 7: "활", 8: "석궁",
    9: "권총", 10: "돌격소총", 11: "저격총", 13: "망치", 14: "도끼", 15: "단검", 16: "양손검",
    17: "폴암", 18: "쌍검", 19: "창", 20: "쌍절곤", 21: "레이피어", 22: "기타", 23: "카메라",
    24: "아르카나", 25: "VF의수",
}


def fetch_recent_games(
    client,
    user_id,
    count: int = RECENT_GAME_COUNT,
    modes: Optional[set[int]] = RECENT_GAME_MODES,
    max_pages: int = MAX_PAGES,
    season_id: Optional[int] = None,
) -> list[dict]:
    """최근 경기(원본 JSON dict)를 최신순으로 최대 count개.

    season_id를 주면 그 시즌 랭크 게임만 세고, 이전 시즌 랭크 게임이 나오면 멈춤
    (일반 게임은 seasonId가 0이라 시즌 판단에 쓰지 않음).
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
            if season_id is not None and game.get("seasonId") and game["seasonId"] != season_id:
                return games[:count]
            if modes is None or game.get("matchingMode") in modes:
                games.append(game)
        cursor = data.get("next")
        if len(games) >= count or not cursor:
            break
    return games[:count]


def _character_row(code, weapon, played: list[dict], names: dict[int, str], season_games: Optional[int]) -> dict:
    """캐릭터·무기 한 줄. 최근 판이 없거나 무기 이름을 안 붙이면 weapon은 None, 최근 판이 없으면 평균도 None."""
    n = len(played)
    return {
        "code": code,
        "name": names.get(code) or f"코드{code}",
        "weapon": WEAPON_NAMES.get(weapon),
        "season_games": season_games,
        "games": n,
        "avg_damage": sum(g.get("damageToPlayer") or 0 for g in played) / n if n else None,
        "avg_team_kill": sum(g.get("teamKill") or 0 for g in played) / n if n else None,
        "avg_rp": sum(g.get("mmrGain") or 0 for g in played) / n if n else None,
    }


def summarize_recent_games(
    games: list[dict],
    character_names: Optional[dict[int, str]] = None,
    season_most: Optional[list[tuple[int, int]]] = None,
    multi_weapon: frozenset[int] = frozenset(),
) -> dict:
    """{"recent_games": 게임 수, "recent_characters": 캐릭터·무기별 줄 (최대 MOST_CHARACTER_COUNT개)}.

    season_most: 시즌 통계의 모스트 [(캐릭터 코드, 시즌 판수)] (판수 순, API가 3개까지만 줌). 이 캐릭터들을
    먼저 이 순서로 넣고, 최근 게임에서 안 한 캐릭터도 넣음 (games=0, weapon과 평균 None).
    그 뒤에 최근 게임에서 많이 한 캐릭터 중 앞에 없는 것 (판수가 같으면 더 최근에 한 캐릭터가 앞,
    season_games=None). 시즌 모스트를 최근에 하나도 안 했어도 최근에 한 캐릭터의 숫자가 보이게 함.

    한 캐릭터를 무기 여러 개로 했으면 무기마다 한 줄씩 붙여서 넣음 (최근 판수 순). 시즌 판수는 무기를
    나누지 않은 캐릭터 전체 값이라 그 캐릭터의 줄마다 같은 값.
    multi_weapon: 무기를 여러 종류 쓸 수 있는 캐릭터 코드. 이 캐릭터의 줄에만 weapon(무기 이름)을 붙임.

    줄마다 {"code", "name", "weapon", "season_games", "games", "avg_damage", "avg_team_kill", "avg_rp"}.
    games와 평균은 그 캐릭터·무기로 한 최근 게임만의 판당 값 (avg_rp는 mmrGain, 랭크 게임에서 얻거나 잃은 RP).
    """
    names = character_names or {}
    by_character: dict[int, dict[int, list[dict]]] = {}
    for game in games:
        by_character.setdefault(game.get("characterNum"), {}).setdefault(game.get("bestWeapon"), []).append(game)
    season = dict((season_most or [])[:MOST_CHARACTER_COUNT])
    recent = sorted(
        (code for code in by_character if code not in season),
        key=lambda code: -sum(len(played) for played in by_character[code].values()),
    )
    rows: list[dict] = []
    for code in [*season, *recent]:
        weapons = by_character.get(code) or {None: []}
        for weapon, played in sorted(weapons.items(), key=lambda item: -len(item[1])):
            label = weapon if code in multi_weapon else None
            rows.append(_character_row(code, label, played, names, season.get(code)))
    return {"recent_games": len(games), "recent_characters": rows[:MOST_CHARACTER_COUNT]}


def get_recent_stats(
    client,
    user_id,
    character_names: dict[int, str],
    count: int = RECENT_GAME_COUNT,
    season_id: Optional[int] = None,
    season_most: Optional[list[tuple[int, int]]] = None,
    multi_weapon: frozenset[int] = frozenset(),
) -> dict:
    games = fetch_recent_games(client, user_id, count=count, season_id=season_id) if count > 0 else []
    return summarize_recent_games(games, character_names, season_most, multi_weapon)


def empty_recent_stats() -> dict:
    return summarize_recent_games([])


def format_recent_stats(stats: dict) -> str:
    """예: '최근 랭크 20게임\n아야(권총) (시즌 40판) 4판  ·  딜량 15,223  ·  TK 9.4  ·  RP +12' (캐릭터·무기마다 한 줄)"""
    lines = [recent_games_title(stats)]
    for c in stats["recent_characters"]:
        name = f"{c['name']}({c['weapon']})" if c.get("weapon") else c["name"]
        if c.get("season_games") is not None:
            name += f" (시즌 {c['season_games']}판)"
        if not c["games"]:
            lines.append(f"{name} 최근 기록 없음")
            continue
        lines.append(
            f"{name} {c['games']}판  ·  딜량 {c['avg_damage']:,.0f}  ·  TK {c['avg_team_kill']:.1f}"
            f"  ·  RP {c['avg_rp']:+.0f}"
        )
    return "\n".join(lines)


def recent_games_title(stats: dict) -> str:
    n = stats["recent_games"]
    if n is None:
        return "최근 게임 조회 실패"
    if n == 0:
        return "최근 랭크 기록 없음"
    return f"최근 랭크 {n}게임"
