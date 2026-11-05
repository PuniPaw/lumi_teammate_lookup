"""player_stats: 티어 계산, 전적 dict 조립 (가짜 API 클라이언트)."""

from types import SimpleNamespace

import player_stats


def test_tier_name():
    assert player_stats.tier_name(0) == "언랭크"
    assert player_stats.tier_name(1) == "아이언 IV"
    assert player_stats.tier_name(5000) == "다이아몬드 IV"
    assert player_stats.tier_name(5780) == "다이아몬드 II"
    assert player_stats.tier_name(7600) == "미스릴"
    assert player_stats.tier_name(9999) == "이터니티"


class FakeUsers:
    def __init__(self, rank_error=False):
        self.rank_error = rank_error
        self._t = SimpleNamespace(
            get=lambda path, **kw: {"userGames": [{"gameId": 1, "matchingMode": 3, "damageToPlayer": 12000, "teamKill": 8}]}
        )

    def get_uid(self, nickname):
        return SimpleNamespace(user_id="uid-1")

    def get_rank(self, user_id, season_id):
        if self.rank_error:
            raise KeyError("serverCode")  # 랭크 기록이 없을 때 실제로 나는 오류
        return SimpleNamespace(mmr=5780)

    def get_stats(self, user_id, season_id):
        char = SimpleNamespace(character_code=1, total_games=40)
        return [
            SimpleNamespace(
                total_games=120, top1=0.14, top2=0.12, top3=0.11, average_rank=4.33, character_stats=[char]
            )
        ]


def test_fetch_user_stats(monkeypatch):
    monkeypatch.setitem(player_stats.CHARACTER_NAMES, 1, "재키")
    stats = player_stats.fetch_user_stats(SimpleNamespace(users=FakeUsers()), "PuniPaw", 31)
    assert stats["user_id"] == "uid-1"
    assert (stats["tier"], stats["mmr"]) == ("다이아몬드 II", 5780)
    assert (stats["games"], round(stats["top1"]), stats["average_rank"]) == (120, 14, 4.3)
    assert (stats["top_character"], stats["top_character_games"]) == ("재키", 40)
    assert (stats["recent_games"], stats["avg_damage_to_player"], stats["avg_team_kill"]) == (1, 12000, 8)


def test_fetch_user_stats_without_rank():
    stats = player_stats.fetch_user_stats(SimpleNamespace(users=FakeUsers(rank_error=True)), "PuniPaw", 31)
    assert (stats["tier"], stats["mmr"]) == ("언랭크", 0)
    assert stats["user_id"] == "uid-1"
