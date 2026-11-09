"""recent_stats 모듈 단위 테스트 (API 키 없이 가짜 응답으로 확인)."""

from lumi.api.recent_stats import (
    fetch_recent_games,
    format_recent_stats,
    summarize_recent_games,
)


def _game(game_id, mode=3, damage=10000, team_kill=5, character=1, weapon=None):
    return {
        "gameId": game_id,
        "matchingMode": mode,
        "characterNum": character,
        "damageToPlayer": damage,
        "teamKill": team_kill,
        "bestWeapon": weapon,
    }


class FakeTransport:
    """'next' 커서로 페이지를 나눠 주는 가짜 API."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, path, **params):
        self.calls.append((path, params.get("next")))
        index = params.get("next") or 0
        page = self.pages[index]
        result = {"code": 200, "userGames": page}
        if index + 1 < len(self.pages):
            result["next"] = index + 1
        return result


class FakeClient:
    def __init__(self, pages):
        self.users = type("Users", (), {})()
        self.users._t = FakeTransport(pages)


def test_paginates_until_count_reached():
    pages = [
        [_game(i) for i in range(0, 10)],
        [_game(i) for i in range(10, 20)],
        [_game(i) for i in range(20, 30)],
    ]
    client = FakeClient(pages)
    games = fetch_recent_games(client, "uid", count=20)
    assert [g["gameId"] for g in games] == list(range(20))
    # 20개가 모이면 세 번째 페이지는 요청하지 않음
    assert len(client.users._t.calls) == 2
    assert client.users._t.calls[0] == ("/v1/user/games/uid/uid", None)


def test_filters_modes_and_duplicates():
    pages = [
        [_game(1, mode=3), _game(2, mode=6), _game(3, mode=2)],
        [_game(3, mode=2), _game(4, mode=3)],  # 3은 중복
    ]
    games = fetch_recent_games(FakeClient(pages), "uid", count=20)
    assert [g["gameId"] for g in games] == [1, 4]  # 랭크(3)만


def test_stops_at_previous_season_ranked_game():
    pages = [
        [dict(_game(1), seasonId=31), dict(_game(2, mode=2), seasonId=0)],
        [dict(_game(3), seasonId=30), dict(_game(4), seasonId=31)],
    ]
    games = fetch_recent_games(FakeClient(pages), "uid", count=20, season_id=31)
    assert [g["gameId"] for g in games] == [1]


def test_all_modes_when_none():
    pages = [[_game(1, mode=3), _game(2, mode=6)]]
    games = fetch_recent_games(FakeClient(pages), "uid", count=20, modes=None)
    assert [g["gameId"] for g in games] == [1, 2]


def test_stops_at_max_pages():
    pages = [[_game(i * 10 + j, mode=6) for j in range(10)] for i in range(10)]
    client = FakeClient(pages)
    games = fetch_recent_games(client, "uid", count=20, max_pages=3)
    assert games == []
    assert len(client.users._t.calls) == 3


def test_damage_is_averaged_per_character():
    games = [
        _game(1, character=1, damage=10000, team_kill=4),
        _game(2, character=2, damage=30000, team_kill=9),
        _game(3, character=1, damage=20000, team_kill=7),
    ]
    stats = summarize_recent_games(games, {1: "재키", 2: "아야"})
    assert stats == {
        "recent_games": 3,
        "recent_characters": [
            {"code": 1, "name": "재키", "weapon": None, "season_games": None, "games": 2, "avg_damage": 15000, "avg_team_kill": 5.5, "avg_rp": 0},
            {"code": 2, "name": "아야", "weapon": None, "season_games": None, "games": 1, "avg_damage": 30000, "avg_team_kill": 9, "avg_rp": 0},
        ],
    }


def test_most_characters_are_capped_and_ties_favor_recent():
    games = [_game(i, character=c) for i, c in enumerate([7, 6, 5, 4, 3, 2, 1, 1])]
    names = [c["name"] for c in summarize_recent_games(games)["recent_characters"]]
    assert names == ["코드1", "코드7", "코드6", "코드5", "코드4"]


def test_season_most_picks_characters_and_recent_games_give_numbers():
    games = [
        dict(_game(1, character=1, damage=10000, team_kill=4), mmrGain=20),
        _game(2, character=9, damage=99999),  # 시즌 모스트 뒤에 최근 게임 캐릭터로 붙음
        dict(_game(3, character=1, damage=20000, team_kill=8), mmrGain=-10),
    ]
    stats = summarize_recent_games(games, {1: "재키", 2: "아야", 9: "시셀라"}, season_most=[(2, 50), (1, 40)])
    assert stats["recent_games"] == 3
    aya, jackie, extra = stats["recent_characters"]  # 시즌 판수 순, 그 뒤에 최근 게임
    assert (aya["name"], aya["season_games"], aya["games"], aya["avg_damage"]) == ("아야", 50, 0, None)
    assert (jackie["season_games"], jackie["games"], jackie["avg_damage"], jackie["avg_team_kill"], jackie["avg_rp"]) == (
        40, 2, 15000, 6, 5,
    )
    assert (extra["name"], extra["season_games"], extra["games"]) == ("시셀라", None, 1)
    assert format_recent_stats(stats) == (
        "최근 랭크 3게임\n아야 (시즌 50판) 최근 기록 없음\n"
        "재키 (시즌 40판) 2판  ·  딜량 15,000  ·  TK 6.0  ·  RP +5\n"
        "시셀라 1판  ·  딜량 99,999  ·  TK 5.0  ·  RP +0"
    )


def test_unplayed_season_most_is_followed_by_recent_characters_without_duplicates():
    """시즌 모스트 3개를 최근에 하나도 안 했어도 최근에 한 캐릭터 숫자가 보여야 함 (총 5개)"""
    games = [_game(i, character=c) for i, c in enumerate([7, 7, 7, 3, 8, 8, 9, 6])]
    stats = summarize_recent_games(games, season_most=[(1, 90), (2, 50), (3, 20)])
    rows = [(c["code"], c["season_games"], c["games"]) for c in stats["recent_characters"]]
    # 3은 시즌 모스트라 한 번만, 남은 2자리는 최근에 많이 한 7(3판), 8(2판)
    assert rows == [(1, 90, 0), (2, 50, 0), (3, 20, 1), (7, None, 3), (8, None, 2)]


def test_each_weapon_of_a_character_gets_its_own_row():
    """아야 권총/저격총처럼 무기가 다르면 따로 세고, 같은 캐릭터 줄은 붙어 있음"""
    games = [
        _game(1, character=9, weapon=9, damage=10000),
        _game(2, character=7, weapon=1),
        _game(3, character=9, weapon=11, damage=30000),
        _game(4, character=9, weapon=9, damage=20000),
    ]
    stats = summarize_recent_games(games, {9: "아야", 7: "재키"}, season_most=[(7, 60), (9, 40)], multi_weapon=frozenset({9}))
    rows = [(c["name"], c["weapon"], c["season_games"], c["games"], c["avg_damage"]) for c in stats["recent_characters"]]
    assert rows == [
        ("재키", None, 60, 1, 10000),  # 무기가 하나뿐인 캐릭터는 무기 이름을 안 붙임
        ("아야", "권총", 40, 2, 15000),  # 시즌 판수는 무기를 나누지 않은 캐릭터 값
        ("아야", "저격총", 40, 1, 30000),
    ]
    assert format_recent_stats(stats).splitlines()[2] == "아야(권총) (시즌 40판) 2판  ·  딜량 15,000  ·  TK 5.0  ·  RP +0"


def test_weapon_rows_count_toward_the_row_limit():
    games = [_game(i, character=1, weapon=w) for i, w in enumerate([15, 16, 14, 18])] + [_game(9, character=2), _game(10, character=3)]
    stats = summarize_recent_games(games, multi_weapon=frozenset({1}))
    rows = [(c["code"], c["weapon"]) for c in stats["recent_characters"]]
    assert rows == [(1, "단검"), (1, "양손검"), (1, "도끼"), (1, "쌍검"), (2, None)]


def test_summarize_handles_missing_fields_and_empty():
    assert summarize_recent_games([]) == {"recent_games": 0, "recent_characters": []}
    stats = summarize_recent_games([{"gameId": 1, "characterNum": 1}, _game(2, damage=3000, team_kill=3)])
    assert stats["recent_characters"][0]["avg_damage"] == 1500
    assert stats["recent_characters"][0]["avg_team_kill"] == 1.5


def test_format():
    stats = summarize_recent_games([_game(1, damage=12345.6, team_kill=6.25)] * 2, {1: "재키"})
    assert format_recent_stats(stats) == "최근 랭크 2게임\n재키 2판  ·  딜량 12,346  ·  TK 6.2  ·  RP +0"
    assert format_recent_stats(summarize_recent_games([])) == "최근 랭크 기록 없음"
