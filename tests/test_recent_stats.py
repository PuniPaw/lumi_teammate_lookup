"""recent_stats 모듈 단위 테스트 (API 키 없이 가짜 응답으로 확인)."""

from lumi.api.recent_stats import (
    fetch_recent_games,
    format_recent_stats,
    summarize_recent_games,
)


def _game(game_id, mode=3, damage=10000, team_kill=5, character=1):
    return {
        "gameId": game_id,
        "matchingMode": mode,
        "characterNum": character,
        "damageToPlayer": damage,
        "teamKill": team_kill,
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
            {"code": 1, "name": "재키", "games": 2, "avg_damage": 15000, "avg_team_kill": 5.5, "avg_rp": 0},
            {"code": 2, "name": "아야", "games": 1, "avg_damage": 30000, "avg_team_kill": 9, "avg_rp": 0},
        ],
    }


def test_most_characters_are_capped_and_ties_favor_recent():
    games = [_game(i, character=c) for i, c in enumerate([7, 6, 5, 4, 3, 2, 1, 1])]
    names = [c["name"] for c in summarize_recent_games(games)["recent_characters"]]
    assert names == ["코드1", "코드7", "코드6", "코드5", "코드4"]


def test_summarize_handles_missing_fields_and_empty():
    assert summarize_recent_games([]) == {"recent_games": 0, "recent_characters": []}
    stats = summarize_recent_games([{"gameId": 1, "characterNum": 1}, _game(2, damage=3000, team_kill=3)])
    assert stats["recent_characters"][0]["avg_damage"] == 1500
    assert stats["recent_characters"][0]["avg_team_kill"] == 1.5


def test_format():
    stats = summarize_recent_games([_game(1, damage=12345.6, team_kill=6.25)] * 2, {1: "재키"})
    assert format_recent_stats(stats) == "최근 랭크 2게임\n재키 2판  ·  딜량 12,346  ·  TK 6.2  ·  RP +0"
    assert format_recent_stats(summarize_recent_games([])) == "최근 랭크 기록 없음"
