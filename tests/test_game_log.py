"""PlayerLog: 로그의 매칭 완료 줄 -> 매칭 신호 (연달아 찍히는 줄은 하나로)."""

import threading
import time

from lumi.game.log import PlayerLog


def test_consecutive_match_lines_are_one_match(tmp_path):
    log = tmp_path / "Player.log"
    log.write_text("boot\n", encoding="utf-8")
    clock = {"t": 0.0}
    matches = PlayerLog(str(log), clock=lambda: clock["t"]).matches()
    got = []

    def consume():
        for _ in matches:
            got.append(clock["t"])

    threading.Thread(target=consume, daemon=True).start()
    time.sleep(0.5)  # follow()가 파일 끝으로 이동할 시간
    with open(log, "a", encoding="utf-8") as f:
        f.write("[OnReceiveMatchingUpdate] MatchingComplete, matchPadding.userCount : 16\n")
        f.write("[OnReceiveMatchingUpdate] matchingNotification : MatchingPadding, Matched\n")
        f.write("[Something] unrelated\n")
    time.sleep(1.0)
    assert got == [0.0]  # 두 줄이 한 매칭

    clock["t"] = 60.0  # 다음 매칭
    with open(log, "a", encoding="utf-8") as f:
        f.write("[OnReceiveMatchingUpdate] MatchingComplete, matchPadding.userCount : null\n")
    time.sleep(1.0)
    assert got == [0.0, 60.0]
