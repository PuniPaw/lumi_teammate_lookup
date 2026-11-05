"""player_stats: 티어 계산, 전적 dict 조립 (가짜 API 클라이언트)."""

from types import SimpleNamespace

from lumi.api import player_stats


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


def test_fetch_user_stats():
    stats = player_stats.fetch_user_stats(SimpleNamespace(users=FakeUsers()), "PuniPaw", 31, {1: "재키"})
    assert stats["user_id"] == "uid-1"
    assert (stats["tier"], stats["mmr"]) == ("다이아몬드 II", 5780)
    assert (stats["games"], round(stats["top1"]), stats["average_rank"]) == (120, 14, 4.3)
    assert (stats["top_character"], stats["top_character_games"]) == ("재키", 40)
    assert (stats["recent_games"], stats["avg_damage_to_player"], stats["avg_team_kill"]) == (1, 12000, 8)


def test_fetch_user_stats_without_rank():
    stats = player_stats.fetch_user_stats(SimpleNamespace(users=FakeUsers(rank_error=True)), "PuniPaw", 31, {})
    assert (stats["tier"], stats["mmr"]) == ("언랭크", 0)
    assert stats["user_id"] == "uid-1"


class FakeClient:
    """EternalReturnStats에 넘기는 가짜 bserpy Client (with 문 지원)."""

    def __init__(self):
        self.users = FakeUsers()
        self.users.get_uid = self._get_uid

    @staticmethod
    def _get_uid(nickname):
        if nickname != "PuniPaw":
            from bserpy import NotFoundError

            raise NotFoundError("not found")
        return SimpleNamespace(user_id="uid-1")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_team_stats_with_unresolved_slot(monkeypatch):
    monkeypatch.setattr(player_stats, "current_season_id", lambda client: 31)
    provider = player_stats.EternalReturnStats(FakeClient)
    ocr = [
        {"name": "teammate_1", "best": "PuniPaw", "candidates": ["PuniPaw"], "candidate_scores": {"PuniPaw": 95}},
        {"name": "teammate_2", "best": "Nobody", "candidates": ["Nobody"], "candidate_scores": {"Nobody": 90}},
        {"name": "teammate_3", "best": "", "candidates": [], "candidate_scores": {}},
    ]
    team = provider.team_stats(ocr)
    assert [s["nickname"] for s in team] == ["PuniPaw", "Nobody"]  # 빈 칸은 카드 없음
    assert team[0]["user_id"] == "uid-1"
    assert (team[1]["tier"], team[1]["user_id"]) == ("조회 실패", None)  # 못 찾으면 수정 가능한 카드
    assert provider.user_stats("Nobody") is None
