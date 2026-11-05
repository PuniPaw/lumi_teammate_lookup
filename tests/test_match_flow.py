"""match_flow(재시도 / 게임 시작 감지) 테스트. 저장된 스크린샷을 사용."""

from conftest import name_crops
from lumi.game.match_flow import LobbyPresence, background_difference, slot_ready, wait_for_teammates


def crops_from_image(name):
    return name_crops(name, refine=False)  # 게임 시작 감지는 항상 같은 위치를 비교


def _slot(best, score):
    return {"best": best, "confidence": score, "candidate_scores": {best: score} if best else {}}


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


# ---------------------------------------------------------------------------
# wait_for_teammates
# ---------------------------------------------------------------------------

def test_slot_ready():
    assert slot_ready(_slot("PuniPaw", 101))
    assert not slot_ready(_slot("sooin", 70))  # 6글자 미만은 75점 기준
    assert not slot_ready(_slot("1", 90))  # 한 글자 잡음
    assert not slot_ready(_slot("fis", 70))  # 짧은 잡음 (실존 유저와 일치한 적 있음)
    assert slot_ready(_slot("124qer123", 61))  # 긴 닉네임은 기준이 낮음
    assert not slot_ready(_slot("124qer123", 55))
    assert not slot_ready(_slot("", 0))


def test_retries_until_all_slots_ready():
    frames = [
        [_slot("", 0), _slot("", 0), _slot("", 0)],  # 아직 안 그려짐
        [_slot("PuniPaw", 100), _slot("so", 50), _slot("", 0)],  # 그려지는 중
        [_slot("PuniPaw", 100), _slot("sooin", 95), _slot("ya발견", 84)],
        [_slot("never", 0)] * 3,
    ]
    calls = []

    def read():
        calls.append(1)
        return frames[len(calls) - 1]

    clock = FakeClock()
    results, ready = wait_for_teammates(read, timeout=15, interval=0.5, now=clock.now, sleep=clock.sleep)
    assert ready == 3
    assert [r["best"] for r in results] == ["PuniPaw", "sooin", "ya발견"]
    assert len(calls) == 3


def test_timeout_returns_best_partial():
    frames = [
        [_slot("PuniPaw", 100), _slot("", 0), _slot("", 0)],
        [_slot("PuniPaw", 100), _slot("MirNight", 99), _slot("", 0)],
    ]
    calls = []

    def read():
        calls.append(1)
        return frames[min(len(calls), len(frames)) - 1]

    clock = FakeClock()
    results, ready = wait_for_teammates(read, timeout=3, interval=0.5, now=clock.now, sleep=clock.sleep)
    assert ready == 2
    assert results[1]["best"] == "MirNight"
    assert clock.t >= 3


def test_nothing_read_returns_none_and_survives_errors():
    def read():
        raise RuntimeError("게임 창 없음")

    clock = FakeClock()
    results, ready = wait_for_teammates(read, timeout=2, interval=0.5, now=clock.now, sleep=clock.sleep)
    assert results is None and ready == 0


def test_should_stop_aborts():
    clock = FakeClock()
    results, ready = wait_for_teammates(
        lambda: [_slot("", 0)], should_stop=lambda: True, now=clock.now, sleep=clock.sleep
    )
    assert results is None


# ---------------------------------------------------------------------------
# LobbyPresence (실제 스크린샷 사용)
# ---------------------------------------------------------------------------

LOBBIES = [
    "matching_lobby_screen.png",
    "normal_matched_lobby.png",
    "test2.png",
    "test3.png",
    "test4.png",
    "lobby_16x10.webp",
]
NOT_LOBBIES = ["team_lobby.png", "main.png"]


def test_background_difference_separates_lobby_from_other_screens():
    for ref_name in LOBBIES:
        ref = crops_from_image((ref_name))
        assert background_difference(ref, ref) == 0
        for other in LOBBIES:
            assert background_difference(ref, crops_from_image((other))) < 20, other
        for other in NOT_LOBBIES:
            assert background_difference(ref, crops_from_image((other))) > 40, other


def test_presence_needs_consecutive_misses():
    lobby = crops_from_image(("test2.png"))
    ingame = crops_from_image(("main.png"))
    presence = LobbyPresence(lobby, consecutive=3)

    assert not presence.update(lobby)
    assert not presence.update(ingame)
    assert not presence.update(lobby)  # 일시적 변화 -> 카운트 초기화
    assert not presence.update(ingame)
    assert not presence.update(ingame)
    assert presence.update(ingame)  # 3회 연속 -> 게임 시작


def test_presence_treats_missing_window_as_gone():
    presence = LobbyPresence(crops_from_image(("test2.png")), consecutive=2)
    assert not presence.update(None)
    assert presence.update(None)
