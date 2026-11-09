"""player_stats: 티어 계산, 전적 dict 조립 (가짜 API 클라이언트)."""

import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

from bserpy._errors import RateLimitError

from lumi.api import player_stats
from lumi.api.recent_stats import format_recent_stats


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
            get=lambda path, **kw: {
                "userGames": [{"gameId": 1, "matchingMode": 3, "characterNum": 1, "damageToPlayer": 12000, "teamKill": 8}]
            }
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
    assert stats["recent_games"] == 1
    assert stats["recent_characters"] == [
        {"code": 1, "name": "재키", "season_games": 40, "games": 1, "avg_damage": 12000, "avg_team_kill": 8, "avg_rp": 0}
    ]


def test_most_characters_come_from_season_stats():
    users = FakeUsers()
    chars = [SimpleNamespace(character_code=c, total_games=g) for c, g in ((2, 30), (1, 40), (3, 5))]
    users.get_stats = lambda user_id, season_id: [
        SimpleNamespace(total_games=75, top1=0.1, top2=0.1, top3=0.1, average_rank=4.0, character_stats=chars)
    ]
    stats = player_stats.fetch_user_stats(SimpleNamespace(users=users), "PuniPaw", 31, {1: "재키", 2: "아야"})
    rows = [(c["code"], c["season_games"], c["games"]) for c in stats["recent_characters"]]
    assert rows == [(1, 40, 1), (2, 30, 0), (3, 5, 0)]  # 시즌 판수 순, 최근 판수는 최근 게임에서


def test_failed_season_lookup_falls_back_to_recent_characters():
    users = FakeUsers()
    users.get_stats = Mock(side_effect=RateLimitError("Too Many Requests"))
    stats = player_stats.fetch_user_stats(SimpleNamespace(users=users), "PuniPaw", 31, {1: "재키"})
    assert [(c["name"], c["season_games"], c["games"]) for c in stats["recent_characters"]] == [("재키", None, 1)]


def test_fetch_user_stats_without_rank():
    stats = player_stats.fetch_user_stats(SimpleNamespace(users=FakeUsers(rank_error=True)), "PuniPaw", 31, {})
    assert (stats["tier"], stats["mmr"]) == ("언랭크", 0)
    assert stats["user_id"] == "uid-1"


def test_failed_rank_lookup_is_not_shown_as_unranked():
    users = FakeUsers()
    users.get_rank = Mock(side_effect=RateLimitError("Too Many Requests"))
    stats = player_stats.fetch_user_stats(SimpleNamespace(users=users), "PuniPaw", 31, {1: "재키"})
    assert (stats["tier"], stats["mmr"]) == ("조회 실패", 0)
    assert stats["games"] == 120  # 다른 조회는 그대로 보여줌


def test_failed_season_lookup_is_marked():
    users = FakeUsers()
    users.get_stats = Mock(side_effect=RateLimitError("Too Many Requests"))
    stats = player_stats.fetch_user_stats(SimpleNamespace(users=users), "PuniPaw", 31, {1: "재키"})
    assert stats["games"] is None
    assert stats["tier"] == "다이아몬드 II"


def test_player_without_season_record_is_not_marked_failed():
    users = FakeUsers()
    users.get_stats = lambda user_id, season_id: []
    stats = player_stats.fetch_user_stats(SimpleNamespace(users=users), "PuniPaw", 31, {1: "재키"})
    assert stats["games"] == 0


def test_failed_recent_lookup_is_not_shown_as_no_record():
    users = FakeUsers()
    users._t = SimpleNamespace(get=Mock(side_effect=RateLimitError("Too Many Requests")))
    stats = player_stats.fetch_user_stats(SimpleNamespace(users=users), "PuniPaw", 31, {1: "재키"})
    assert format_recent_stats(stats) == "최근 게임 조회 실패"
    assert stats["tier"] == "다이아몬드 II"


def test_player_without_recent_games_is_shown_as_no_record():
    users = FakeUsers()
    users._t = SimpleNamespace(get=lambda path, **kw: {"userGames": []})
    stats = player_stats.fetch_user_stats(SimpleNamespace(users=users), "PuniPaw", 31, {1: "재키"})
    # 시즌 모스트는 최근 게임이 없어도 줄로 남음
    assert format_recent_stats(stats) == "최근 랭크 기록 없음\n재키 (시즌 40판) 최근 기록 없음"


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


def test_team_stats_runs_concurrently_and_keeps_order(monkeypatch):
    """프록시를 거치면 요청이 느려서 팀원을 동시에 조회함. 늦게 끝난 팀원도 제자리에 있어야 함"""
    monkeypatch.setattr(player_stats, "current_season_id", lambda client: 31)
    both_started = threading.Barrier(3, timeout=5)  # 3명이 동시에 조회 중이 아니면 BrokenBarrierError

    def resolve(client, ocr_results):
        name = ocr_results[0]["best"]
        both_started.wait()
        if name == "A":
            time.sleep(0.1)  # 첫 팀원이 가장 늦게 끝남
        return [{"resolved_nickname": name, "user_id": f"uid-{name}"}]

    monkeypatch.setattr(player_stats, "resolve_teammate_names", resolve)
    used_ids = []

    def fetch(client, nickname, season_id, character_names, user_id=None):
        used_ids.append(user_id)
        return player_stats.failed_stats(nickname)

    monkeypatch.setattr(player_stats, "fetch_user_stats", fetch)
    provider = player_stats.EternalReturnStats(FakeClient)
    team = provider.team_stats([{"name": n, "best": n} for n in ("A", "B", "C")])
    assert [s["nickname"] for s in team] == ["A", "B", "C"]
    assert sorted(used_ids) == ["uid-A", "uid-B", "uid-C"]  # 확정 때 얻은 uid를 다시 조회하지 않음


def test_one_failed_teammate_keeps_the_others(monkeypatch):
    monkeypatch.setattr(player_stats, "current_season_id", lambda client: 31)

    def resolve(client, ocr_results):
        name = ocr_results[0]["best"]
        if name == "B":
            raise RuntimeError("network")
        return [{"resolved_nickname": name, "user_id": f"uid-{name}"}]

    monkeypatch.setattr(player_stats, "resolve_teammate_names", resolve)
    monkeypatch.setattr(
        player_stats, "fetch_user_stats",
        lambda client, nickname, *a, **k: dict(player_stats.failed_stats(nickname), tier="골드 I"),
    )
    team = player_stats.EternalReturnStats(FakeClient).team_stats([{"name": n, "best": n} for n in ("A", "B")])
    assert [(s["nickname"], s["tier"]) for s in team] == [("A", "골드 I"), ("B", "조회 실패")]
