"""recent_stats 모듈 단위 테스트 (API 키 없이 가짜 응답으로 확인)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from recent_stats import (  # noqa: E402
    fetch_recent_games,
    format_recent_stats,
    summarize_recent_games,
)


def _game(game_id, mode=3, damage=10000, team_kill=5):
    return {
        "gameId": game_id,
        "matchingMode": mode,
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
    assert [g["gameId"] for g in games] == [1, 3, 4]


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


def test_summarize_averages():
    games = [_game(1, damage=10000, team_kill=4), _game(2, damage=20000, team_kill=7)]
    stats = summarize_recent_games(games)
    assert stats == {
        "recent_games": 2,
        "avg_damage_to_player": 15000,
        "avg_team_kill": 5.5,
    }


def test_summarize_handles_missing_fields_and_empty():
    assert summarize_recent_games([])["avg_damage_to_player"] is None
    stats = summarize_recent_games([{"gameId": 1}, _game(2, damage=3000, team_kill=3)])
    assert stats["avg_damage_to_player"] == 1500
    assert stats["avg_team_kill"] == 1.5


def test_format():
    text = format_recent_stats(
        {"recent_games": 20, "avg_damage_to_player": 12345.6, "avg_team_kill": 6.25}
    )
    assert text == "최근 20게임  ·  평균 딜량 12,346  ·  평균 TK 6.2"
    assert format_recent_stats(summarize_recent_games([])) == "최근 게임 기록 없음"
