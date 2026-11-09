"""앱 전체 흐름 통합 테스트 (게임/API 없이, Qt offscreen).

외부 연결(ports)에 가짜 구현을 넘깁니다. OCR은 실제 PP-OCR로 저장된 화면을 읽습니다.
매칭 신호 -> 닉네임 인식(재시도) -> 모달 표시 -> 화면이 바뀌면 모달 닫기.
"""

import queue
import time

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from conftest import fixture  # noqa: E402
from lumi.api.player_stats import STAGE_RECENT, failed_stats, pending_stats  # noqa: E402
from lumi.app import MatchWorker, OverlayController, connect  # noqa: E402
from lumi.capture.screen import ImageScreen  # noqa: E402
from lumi.debug.store import DebugStore  # noqa: E402
from lumi.ocr.paddle import PaddleReader  # noqa: E402
from lumi.ui.overlay import OverlayWindow, TeammateRow  # noqa: E402


class FakeSignals:
    """send()를 부르면 매칭 신호 하나."""

    def __init__(self):
        self._q = queue.Queue()

    def send(self):
        self._q.put(None)

    def matches(self):
        while True:
            yield self._q.get()


class SequenceScreen(ImageScreen):
    """처음 몇 번은 다른 화면을 보여준 뒤 path로 바뀌는 화면 (refine=True인 OCR용 캡처만 셈)."""

    def __init__(self, path, first_frames):
        super().__init__(path)
        self.first_frames = list(first_frames)

    def name_crops(self, refine=True):
        if refine and self.first_frames:
            return ImageScreen(self.first_frames.pop(0)).name_crops(refine)
        return super().name_crops(refine)


class FakeStats:
    def __init__(self):
        self.seen = []

    def team_stats(self, ocr_results, on_update=None):
        self.seen = [r["best"] for r in ocr_results]
        team = [dict(failed_stats(n), user_id=f"uid-{n}", tier="골드 I") for n in self.seen]
        for i, stats in enumerate(team):
            if on_update:
                on_update(i, stats)
        return team

    def user_stats(self, nickname):
        return None


def _wait_until(app, cond, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_match_shows_modal_then_closes_when_game_starts(tmp_path):
    pytest.importorskip("rapidocr")
    app = QApplication.instance() or QApplication([])
    # 닉네임이 아직 안 그려진 화면 2번 -> 매칭 화면
    screen = SequenceScreen(fixture("test3.png"), [fixture("team_lobby.png")] * 2)
    signals, stats = FakeSignals(), FakeStats()
    debug = DebugStore(enabled=False, directory=str(tmp_path))

    worker = MatchWorker(signals, screen, PaddleReader(), stats, debug)
    controller = OverlayController(screen, stats, debug)
    controller.timer.setInterval(50)
    connect(worker, controller)
    worker.start()

    signals.send()
    assert _wait_until(app, lambda: controller.window is not None), "모달이 뜨지 않음"
    assert worker.current_match_id() == 1
    assert controller.window.isVisible()
    # 조회가 끝나면 같은 창의 카드가 채워짐
    rows = controller.window.rows
    assert _wait_until(app, lambda: all(r.tier_line.text() == "골드 I" for r in rows)), "카드가 채워지지 않음"
    assert stats.seen == ["PuniPaw", "로즈만때리는루크", "마브하라"]
    assert [r.nickname_edit.text() for r in rows] == ["PuniPaw", "로즈만때리는루크", "마브하라"]

    # 캐릭터 선택 중 (같은 화면) -> 계속 떠 있음
    for _ in range(10):
        app.processEvents()
        time.sleep(0.05)
    assert controller.window is not None

    # 게임 시작 -> 닉네임 칸이 사라진 화면
    screen.path = fixture("main.png")
    assert _wait_until(app, lambda: controller.window is None, timeout=5), "모달이 닫히지 않음"


def test_overlay_is_placed_inside_screen():
    """고정 좌표를 쓰면 배율 200% 화면에서 화면 밖에 뜰 수 있음"""
    app = QApplication.instance() or QApplication([])
    window = OverlayWindow([failed_stats(n) for n in ("PuniPaw", "12345a", "얼음마녀")], refetch=lambda n: None)
    window.show()
    app.processEvents()

    screen = app.primaryScreen().availableGeometry()
    geo = window.frameGeometry()
    assert screen.contains(geo.topLeft()) and screen.contains(geo.topRight())
    assert geo.right() >= screen.right() - 100
    window.close()


def test_modal_shows_failed_recent_lookup():
    QApplication.instance() or QApplication([])
    stats = dict(failed_stats("PuniPaw"), user_id="uid-1", tier="다이아몬드 IV", recent_games=None)
    row = TeammateRow(stats, refetch=lambda n: None)
    assert row.recent_line.text() == "최근 게임 조회 실패"
    assert not row.recent_line.isHidden()


def test_modal_shows_failed_season_lookup():
    QApplication.instance() or QApplication([])
    stats = dict(failed_stats("PuniPaw"), user_id="uid-1", tier="다이아몬드 IV", games=None)
    row = TeammateRow(stats, refetch=lambda n: None)
    assert row.detail_line.text() == "시즌 통계 조회 실패"


def test_modal_lists_characters_and_says_when_no_ranked_games():
    QApplication.instance() or QApplication([])
    character = {"code": 1, "name": "재키", "games": 4, "avg_damage": 15200, "avg_team_kill": 9.4, "avg_rp": -12}
    stats = dict(failed_stats("PuniPaw"), user_id="uid-1", tier="골드 I", recent_games=4, recent_characters=[character])
    row = TeammateRow(stats, refetch=lambda n: None)
    labels = row.table.findChildren(QLabel)
    assert [label.text() for label in labels if label.text()][-4:] == ["4", "15.2k", "9.4", "-12"]
    assert [label.toolTip() for label in labels if label.toolTip()] == ["재키"]  # 이름은 아이콘에 마우스를 올리면

    row._apply_stats(dict(stats, recent_games=0, recent_characters=[]))
    assert row.recent_line.text() == "최근 랭크 기록 없음"
    assert row.table.isHidden()


def test_modal_shows_season_most_with_recent_numbers():
    QApplication.instance() or QApplication([])
    played = {"code": 1, "name": "재키", "season_games": 40, "games": 4, "avg_damage": 15200, "avg_team_kill": 9.4, "avg_rp": 7}
    unplayed = {"code": 2, "name": "아야", "season_games": 30, "games": 0, "avg_damage": None, "avg_team_kill": None, "avg_rp": None}
    stats = dict(failed_stats("PuniPaw"), user_id="uid-1", tier="골드 I", recent_games=4, recent_characters=[played, unplayed])
    row = TeammateRow(stats, refetch=lambda n: None)
    texts = [label.text() for label in row.table.findChildren(QLabel) if label.text()]
    assert texts[:5] == ["시즌", "최근", "딜량", "TK", "RP"]
    # 아이콘 파일이 없으면 아이콘 칸에 이름 앞 두 글자가 들어가서 숫자 칸만 비교
    numbers = [t for t in texts[5:] if t not in ("재키", "아야")]
    assert numbers == ["40", "4", "15.2k", "9.4", "+7", "30", "0", "–", "–", "–"]
    tips = [label.toolTip() for label in row.table.findChildren(QLabel) if label.toolTip()]
    assert tips == ["재키  ·  시즌 40판", "아야  ·  시즌 30판"]


def test_weapon_rows_show_weapon_on_hover_and_share_season_count():
    QApplication.instance() or QApplication([])

    def row(weapon, games):
        return {"code": 9, "name": "아야", "weapon": weapon, "season_games": 50, "games": games,
                "avg_damage": 15000, "avg_team_kill": 8, "avg_rp": 3}

    stats = dict(failed_stats("PuniPaw"), user_id="uid-1", tier="골드 I", recent_games=5,
                 recent_characters=[row("권총", 3), row("저격총", 2)])
    card = TeammateRow(stats, refetch=lambda n: None)
    layout = card.table_layout
    cells = {}
    for i in range(layout.count()):
        r, c, rows, _ = layout.getItemPosition(i)
        cells.setdefault(c, []).append((r, rows, layout.itemAt(i).widget()))
    assert [w.toolTip() for _, _, w in cells[0][1:]] == ["아야(권총)  ·  시즌 50판", "아야(저격총)  ·  시즌 50판"]
    assert [(r, rows, w.text()) for r, rows, w in cells[1][1:]] == [(1, 2, "50")]  # 시즌 판수는 한 칸으로 걸침
    assert [w.text() for _, _, w in cells[2][1:]] == ["3", "2"]
    assert "권총" not in [label.text() for label in card.table.findChildren(QLabel)]  # 무기는 표에 글자로 안 씀


def test_moved_overlay_reopens_where_it_was_left(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = str(tmp_path / "overlay_position.json")
    team = [failed_stats("PuniPaw")]
    first = OverlayWindow(team, refetch=lambda n: None, position_file=path)
    screen = app.primaryScreen().availableGeometry()
    first.move(screen.left() + 30, screen.top() + 40)
    first.save_position()

    second = OverlayWindow(team, refetch=lambda n: None, position_file=path)
    assert (second.x(), second.y()) == (screen.left() + 30, screen.top() + 40)


def test_saved_position_off_every_screen_falls_back_to_top_right(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "overlay_position.json"
    path.write_text('{"x": -99999, "y": -99999}', encoding="utf-8")
    window = OverlayWindow([failed_stats("PuniPaw")], refetch=lambda n: None, position_file=str(path))
    screen = app.primaryScreen().availableGeometry()
    assert screen.contains(window.frameGeometry().topRight())
    assert window.frameGeometry().right() >= screen.right() - 100

    path.write_text("not json", encoding="utf-8")
    window = OverlayWindow([failed_stats("PuniPaw")], refetch=lambda n: None, position_file=str(path))
    assert window.frameGeometry().right() >= screen.right() - 100


def test_cards_fill_in_as_lookup_progresses():
    QApplication.instance() or QApplication([])
    window = OverlayWindow([pending_stats("PuniPaw")], refetch=lambda n: None)
    row = window.rows[0]
    assert row.tier_line.text() == "조회 중..."
    assert row.recent_line.isHidden() and row.table.isHidden()

    basic = dict(failed_stats("PuniPaw"), user_id="uid-1", tier="골드 I", mmr=3100, games=40)
    window.update_teammate(0, dict(basic, stage=STAGE_RECENT))
    assert row.tier_line.text().startswith("골드 I")
    assert row.recent_line.text() == "최근 랭크 게임 불러오는 중..."

    character = {"code": 1, "name": "재키", "games": 4, "avg_damage": 15200, "avg_team_kill": 9.4, "avg_rp": -12}
    window.update_teammate(0, dict(basic, recent_games=4, recent_characters=[character]))
    assert row.recent_line.text() == "최근 랭크 4게임"
    assert not row.table.isHidden()


def test_late_lookup_does_not_overwrite_a_corrected_nickname():
    QApplication.instance() or QApplication([])
    corrected = dict(failed_stats("PuniPaw"), user_id="uid-1", tier="골드 I")
    window = OverlayWindow([pending_stats("PuniPaw1")], refetch=lambda n: corrected)
    row = window.rows[0]
    row.nickname_edit.setText("PuniPaw")
    row.nickname_edit.returnPressed.emit()
    window.update_teammate(0, failed_stats("PuniPaw1"))  # 처음 읽은 글자로 한 조회가 늦게 끝남
    assert row.tier_line.text() == "골드 I"


def test_card_of_unfound_player_does_not_claim_no_record():
    QApplication.instance() or QApplication([])
    row = TeammateRow(failed_stats("MirNight"), refetch=lambda n: None)
    assert "기록 없음" not in row.detail_line.text()
    assert row.recent_line.isHidden() and row.table.isHidden()


class FixedReader:
    """정해진 OCR 결과를 돌려주고 호출 횟수를 셈."""

    def __init__(self, results):
        self.results = results
        self.calls = 0

    def read(self, crops):
        self.calls += 1
        return self.results


class ToggleScreen(ImageScreen):
    def __init__(self, path, active):
        super().__init__(path)
        self.active = active

    def is_active(self):
        return self.active


def _slot(name, best, score):
    return {"name": name, "best": best, "confidence": score,
            "candidates": [best] if best else [], "candidate_scores": {best: score} if best else {},
            "crop_image": None}


def test_hidden_game_window_is_not_read(tmp_path, monkeypatch):
    """게임 창이 가려져 있으면 OCR 하지 않고, 결과 없이 끝남 (다른 창 글자 오매칭 방지)"""
    import lumi.app

    monkeypatch.setattr(lumi.app, "wait_for_teammates",
                        lambda read, should_stop: (lambda r: (r or None, 0))(read()))
    reader = FixedReader([_slot("teammate_1", "fis", 79.0)])
    stats = FakeStats()
    worker = MatchWorker(FakeSignals(), ToggleScreen(fixture("test3.png"), active=False), reader, stats,
                         DebugStore(enabled=False, directory=str(tmp_path)))
    worker._handle_match(0)
    assert reader.calls == 0
    assert stats.seen == []


def test_modal_stays_open_while_game_window_is_hidden(tmp_path):
    """alt+tab으로 다른 창이 앞에 오면 그 창을 캡처하게 되므로 게임 시작으로 보지 않음"""
    app = QApplication.instance() or QApplication([])
    screen = ToggleScreen(fixture("test3.png"), active=True)
    controller = OverlayController(screen, FakeStats(), DebugStore(enabled=False, directory=str(tmp_path)))
    controller.timer.setInterval(50)
    controller.on_team_started(1, [failed_stats("PuniPaw")], screen.name_crops(refine=False))

    # 가려진 동안 캡처되는 화면은 로비가 아님 -> 그래도 닫히지 않아야 함
    screen.active, screen.path = False, fixture("main.png")
    assert not _wait_until(app, lambda: controller.window is None, timeout=1), "가려진 동안 모달이 닫힘"

    # 게임 창으로 돌아왔는데 로비면 계속 떠 있음
    screen.active, screen.path = True, fixture("test3.png")
    assert not _wait_until(app, lambda: controller.window is None, timeout=0.5)

    # 실제로 게임이 시작되면 닫힘
    screen.path = fixture("main.png")
    assert _wait_until(app, lambda: controller.window is None, timeout=5), "모달이 닫히지 않음"


def test_only_confident_slots_are_looked_up():
    from lumi.app import lookup_targets

    results = [_slot("teammate_1", "PuniPaw", 95.0), _slot("teammate_2", "和一", 60.0), _slot("teammate_3", "", 0.0)]
    targets = lookup_targets(results)
    assert targets[0]["candidates"] == ["PuniPaw"]
    assert targets[1]["candidates"] == [] and targets[1]["best"] == "和一"  # 조회 안 함, 카드에는 표시
    assert targets[2]["candidates"] == []
