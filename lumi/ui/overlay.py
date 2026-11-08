"""팀원 전적 모달 창 (PySide6). 팀원 카드를 가로로 나란히 놓습니다."""

import json
import os
from typing import Callable, Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from lumi.api.recent_stats import recent_games_title

# 닉네임 -> 전적 dict (못 찾으면 None). 모달에서 닉네임을 고쳐 Enter를 누를 때 사용
Refetch = Callable[[str], Optional[dict]]

CARD_WIDTH = 256
SCREEN_MARGIN = 20
# 글자 크기(px). 게임 화면 위에서 읽히도록 키움
FONT_NICKNAME, FONT_TIER, FONT_BODY, FONT_SMALL = 16, 13, 13, 11
TABLE_SIDE_PADDING = 4
# 이보다 적은 판수의 캐릭터 줄은 흐리게. 한 판의 딜량은 평균에서 보통 ±35% 흔들려서(실측)
# 2판 이하의 평균은 ±25% 넘게 흔들릴 수 있음 (docs/DEVELOPMENT_NOTES.md)
RELIABLE_GAMES = 3

BACKGROUND, CARD, LINE = "#16181d", "#22252c", "#2f333b"
TEXT, SUB, DIM = "#e8e8e8", "#a9adb6", "#5f646e"
NICKNAME, GAIN, LOSS, ERROR = "#ffd166", "#6ee7a8", "#f87171", "#ff6b6b"
TIER_COLORS = {
    "이터니티": "#ff5c8a", "미스릴": "#c084fc", "메테오라이트": "#7dd3fc", "다이아몬드": "#67e8f9",
    "플래티넘": "#5eead4", "골드": "#fbbf24", "실버": "#cbd5e1", "브론즈": "#d4a373", "아이언": "#9ca3af",
}
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "characters")
ICON_SIZE = 26
COLUMNS = ("", "판", "딜량", "TK", "RP")


def _label(text: str = "", color: str = TEXT, size: int = FONT_BODY, bold: bool = False, align=None) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {color}; font-size: {size}px; {'font-weight: bold;' if bold else ''} background: transparent;")
    if align is not None:
        label.setAlignment(align)
    return label


def character_icon(code) -> Optional[QPixmap]:
    """팬키트 초상화 아이콘 (lumi.debug.fankit_icons로 만듦). 없으면 None."""
    pixmap = QPixmap(os.path.join(ICON_DIR, f"{code}.png"))
    if pixmap.isNull():
        return None
    pixmap.setDevicePixelRatio(pixmap.width() / ICON_SIZE)  # 48px 원본을 논리 크기로 (고배율 화면에서 선명)
    return pixmap


class CharacterIcon(QLabel):
    """마우스를 올리면 캐릭터 이름을 띄움.

    Qt의 기본 툴팁은 활성 창에서만 뜨는데, 모달은 게임 포커스를 뺏지 않아 늘 비활성이라
    직접 띄움 (WA_AlwaysShowToolTips만으로는 실제 창에서 뜨지 않았음).
    """

    def enterEvent(self, event):  # noqa: N802 (Qt 이벤트 이름)
        QToolTip.showText(QCursor.pos(), self.toolTip(), self)
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        QToolTip.hideText()
        super().leaveEvent(event)


def _character_cell(character: dict, reliable: bool) -> QLabel:
    """아이콘만 표시 (이름은 마우스를 올리면). 아이콘이 없는 캐릭터는 이름 앞 두 글자."""
    pixmap = character_icon(character["code"])
    cell = CharacterIcon()
    cell.setToolTip(character["name"])
    if pixmap is not None:
        cell.setPixmap(pixmap)
    else:
        cell.setText(character["name"][:2])
        cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
    cell.setFixedSize(ICON_SIZE, ICON_SIZE)
    cell.setStyleSheet(f"background: {LINE}; border-radius: 4px; color: {TEXT}; font-size: {FONT_SMALL}px;")
    if not reliable:
        effect = QGraphicsOpacityEffect(cell)
        effect.setOpacity(0.4)
        cell.setGraphicsEffect(effect)
    return cell


def tier_text(stats: dict) -> tuple[str, str]:
    """(티어 문구, 색)."""
    tier = stats["tier"]
    color = next((c for name, c in TIER_COLORS.items() if tier.startswith(name)), SUB)
    if stats.get("mmr", 0) > 0:
        return f"{tier}  ·  {stats['mmr']}", color
    return tier, ERROR if tier == "조회 실패" else color


def season_text(stats: dict) -> str:
    if stats["games"] is None:
        return "시즌 통계 조회 실패"
    if stats["games"] == 0:
        return "이번 시즌 랭크 기록 없음"
    parts = [f"시즌 {stats['games']}판"]
    if stats.get("average_rank", 0) > 0:
        parts.append(f"평균 {stats['average_rank']:.1f}등")
    parts.append(f"승률 {stats['top1']:.0f}%")
    return "  ·  ".join(parts)


class TeammateRow(QFrame):
    """팀원 한 명의 카드. 닉네임을 고쳐 Enter를 누르면 재조회합니다."""

    def __init__(self, stats: dict, refetch: Refetch):
        super().__init__()
        self._refetch = refetch
        self.setFixedWidth(CARD_WIDTH)
        self.setStyleSheet(f"TeammateRow {{ background-color: {CARD}; border-radius: 8px; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self.nickname_edit = QLineEdit(stats["nickname"])
        self.nickname_edit.setStyleSheet(
            f"color: {NICKNAME}; font-weight: bold; font-size: {FONT_NICKNAME}px;"
            " background: transparent; border: none; padding: 0;"
        )
        self.nickname_edit.returnPressed.connect(self._on_nickname_submitted)

        self.tier_line = _label(size=FONT_TIER, bold=True)
        self.detail_line = _label(color=SUB, size=FONT_SMALL)
        self.recent_line = _label(color=SUB, size=FONT_SMALL)
        self.table = QWidget()
        self.table.setStyleSheet("background: transparent;")  # 창 배경색이 상속되면 카드 안에 어두운 상자가 생김
        self.table_layout = QGridLayout(self.table)
        self.table_layout.setContentsMargins(TABLE_SIDE_PADDING, 2, TABLE_SIDE_PADDING, 2)
        self.table_layout.setHorizontalSpacing(6)
        self.table_layout.setVerticalSpacing(3)
        self.status_line = _label(color=ERROR, size=FONT_SMALL)
        self.status_line.hide()

        separator = QFrame()
        separator.setFixedHeight(1)
        separator.setStyleSheet(f"background: {LINE};")
        for widget in (self.nickname_edit, self.tier_line, self.detail_line, separator, self.recent_line, self.table):
            layout.addWidget(widget)
        layout.addStretch()
        layout.addWidget(self.status_line)
        self._apply_stats(stats)

    def _apply_stats(self, stats: dict) -> None:
        text, color = tier_text(stats)
        self.tier_line.setText(text)
        self.tier_line.setStyleSheet(
            f"color: {color}; font-size: {FONT_TIER}px; font-weight: bold; background: transparent;"
        )
        # 유저 조회 자체가 실패한 카드에 '기록 없음'을 띄우면 오해를 주므로 숨김
        found = bool(stats.get("user_id"))
        self.detail_line.setText(season_text(stats) if found else "이름을 고쳐 Enter를 누르면 다시 조회합니다")
        self.recent_line.setVisible(found)
        self.recent_line.setText(recent_games_title(stats))
        self._fill_table(stats["recent_characters"] if found else [])

    def _fill_table(self, characters: list[dict]) -> None:
        while self.table_layout.count():
            self.table_layout.takeAt(0).widget().deleteLater()
        self.table.setVisible(bool(characters))
        if not characters:
            return
        for col, title in enumerate(COLUMNS):
            self.table_layout.addWidget(_label(title, DIM, FONT_SMALL, align=RIGHT), 0, col)
        for row, c in enumerate(characters, start=1):
            reliable = c["games"] >= RELIABLE_GAMES
            main, sub = (TEXT, SUB) if reliable else (DIM, DIM)
            rp_color = (GAIN if c["avg_rp"] >= 0 else LOSS) if reliable else DIM
            cells = [
                _character_cell(c, reliable),
                _label(str(c["games"]), sub, align=RIGHT),
                _label(f"{c['avg_damage'] / 1000:.1f}k", main, bold=reliable, align=RIGHT),
                _label(f"{c['avg_team_kill']:.1f}", sub, align=RIGHT),
                _label(f"{c['avg_rp']:+.0f}", rp_color, align=RIGHT),
            ]
            for col, cell in enumerate(cells):
                self.table_layout.addWidget(cell, row, col)
        # 아이콘 칸은 고정, 숫자 칸들이 남은 폭을 똑같이 나눔 (아이콘과 숫자 사이가 벌어지지 않게)
        for col in range(1, len(COLUMNS)):
            self.table_layout.setColumnStretch(col, 1)

    def _on_nickname_submitted(self) -> None:
        nickname = self.nickname_edit.text().strip()
        self.status_line.hide()
        self.detail_line.setText("조회 중...")

        stats = self._refetch(nickname)
        if stats is None:
            self.detail_line.setText("이전 정보 유지됨")
            self.status_line.setText(f"'{nickname}' 유저를 찾을 수 없습니다.")
            self.status_line.show()
            return
        self._apply_stats(stats)


class DraggableHeader(QLabel):
    """누른 채 끌면 부모 창이 따라 움직이는 헤더."""

    def __init__(self, text: str, window: QWidget):
        super().__init__(text)
        self._window = window
        self._drag_offset = None
        self.setStyleSheet(f"color: {TEXT}; font-weight: bold; font-size: {FONT_TIER}px; padding: 2px;")
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event):  # noqa: N802 (Qt 이벤트 이름)
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._window.pos()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_offset is not None:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._drag_offset is not None:
            self._window.save_position()
        self._drag_offset = None


class OverlayWindow(QWidget):
    """팀원 카드들을 가로로 보여주는 항상-위 창."""

    def __init__(self, team_stats: list[dict], refetch: Refetch, position_file: Optional[str] = None):
        super().__init__()
        self._position_file = position_file
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # 작업 표시줄에 안 뜸
        )
        # 뜰 때 게임 포커스를 뺏지 않음 (클릭하면 그때 활성화)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(f"background-color: {BACKGROUND};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        # 창 크기를 항상 내용에 맞춤. 스타일시트 글자 크기는 표시 직전에 적용돼서, 미리 잰 크기로는
        # 마지막 캐릭터 줄이 잘렸음 (재조회로 줄 수가 바뀔 때도 맞춰짐)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        header = QHBoxLayout()
        header.addWidget(DraggableHeader("팀원 전적  ·  이름을 눌러 고치고 Enter", self), 1)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 22)
        close_btn.setStyleSheet(f"color: {SUB}; background: transparent; border: none; font-size: 13px;")
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)
        layout.addLayout(header)

        cards = QHBoxLayout()
        cards.setSpacing(6)
        for stats in team_stats:
            cards.addWidget(TeammateRow(stats, refetch))
        layout.addLayout(cards)
        layout.addWidget(
            _label(
                f"최근 랭크 게임의 캐릭터별 판당 평균  ·  흐린 줄은 {RELIABLE_GAMES - 1}판 이하라 참고용"
                "  ·  아이콘에 마우스를 올리면 이름",
                DIM,
                FONT_SMALL,
            )
        )
        # IP 이용 정책: 공식 콘텐츠로 오인되지 않게 표기
        layout.addWidget(_label("비공식 팬 도구  ·  캐릭터 이미지 © Nimble Neuron (공식 팬키트)", DIM, FONT_SMALL))

        self.place_on_screen()

    def save_position(self) -> None:
        if not self._position_file:
            return
        try:
            with open(self._position_file, "w", encoding="utf-8") as f:
                json.dump({"x": self.x(), "y": self.y()}, f)
        except OSError as e:
            print(f"⚠️ 모달 위치 저장 실패: {e}")

    def _saved_position(self) -> Optional[QPoint]:
        if not self._position_file:
            return None
        try:
            with open(self._position_file, encoding="utf-8") as f:
                data = json.load(f)
            return QPoint(int(data["x"]), int(data["y"]))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def place_on_screen(self) -> None:
        """사용자가 옮겨 둔 위치가 있으면 거기, 없으면 마우스가 있는 모니터(보통 게임 화면)의 오른쪽 위.

        Qt 좌표는 Windows 배율이 적용된 논리 좌표라 고정 좌표를 쓰면 안 됨
        (예: 2880x1800 + 배율 200%는 논리 1440x900).
        """
        self.ensurePolished()
        self.adjustSize()
        saved = self._saved_position()
        # 저장한 위치의 모니터가 빠졌으면 무시. 팀원 수에 따라 폭이 달라서 화면 안으로 당김
        screen = QGuiApplication.screenAt(saved) if saved is not None else None
        if screen is not None:
            geo = screen.availableGeometry()
            x = max(geo.left(), min(saved.x(), geo.right() - self.width() + 1))
            y = max(geo.top(), min(saved.y(), geo.bottom() - self.height() + 1))
            self.move(x, y)
            return

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        width = min(self.width(), geo.width())
        height = min(self.height(), geo.height())
        x = max(geo.left(), geo.right() - width - SCREEN_MARGIN + 1)
        y = geo.top() + min(SCREEN_MARGIN, max(0, geo.height() - height))
        self.move(x, y)
