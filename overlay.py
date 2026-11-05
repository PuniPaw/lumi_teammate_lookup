"""팀원 전적 모달 창 (PySide6)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from player_stats import fetch_stats_by_nickname
from recent_stats import format_recent_stats

WINDOW_WIDTH = 340
SCREEN_MARGIN = 20


class TeammateRow(QFrame):
    """팀원 한 명의 카드. 닉네임을 고쳐 Enter를 누르면 재조회합니다."""

    def __init__(self, stats: dict):
        super().__init__()
        self.setStyleSheet("background-color: #2a2a2a; border-radius: 6px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        self.nickname_edit = QLineEdit(stats["nickname"])
        self.nickname_edit.setStyleSheet(
            "color: #ffd166; font-weight: bold; font-size: 13px;"
            "background: transparent; border: none; padding: 0;"
        )
        self.nickname_edit.returnPressed.connect(self._on_nickname_submitted)

        self.tier_line = self._label("color: #ffd700; font-size: 11px; font-weight: bold;")
        self.detail_line = self._label("color: #cccccc; font-size: 10px;")
        self.recent_line = self._label("color: #8ecae6; font-size: 10px;")
        self.status_line = self._label("color: #ff6b6b; font-size: 10px;")
        self.status_line.hide()

        for widget in (self.nickname_edit, self.tier_line, self.detail_line, self.recent_line, self.status_line):
            layout.addWidget(widget)
        self._apply_stats(stats)

    @staticmethod
    def _label(style: str) -> QLabel:
        label = QLabel()
        label.setStyleSheet(style)
        return label

    def _apply_stats(self, stats: dict) -> None:
        tier = f"🏆 {stats['tier']}"
        if stats.get("mmr", 0) > 0:
            tier += f" (MMR: {stats['mmr']})"
        self.tier_line.setText(tier)

        line1 = f"모스트 {stats['top_character']} {stats['top_character_games']}판"
        if stats.get("games", 0) > 0:
            line1 += f"  ·  전체 {stats['games']}판"
        if stats.get("average_rank", 0) > 0:
            line1 += f"  ·  평균 {stats['average_rank']:.2f}등"
        rates = [
            f"{label} {stats[key]:.0f}%"
            for key, label in (("top1", "승률"), ("top2", "2위"), ("top3", "3위"))
            if stats.get(key, 0) > 0
        ]
        self.detail_line.setText(line1 + ("\n" + "  ·  ".join(rates) if rates else ""))

        # 유저 조회 자체가 실패한 카드에 '기록 없음'을 띄우면 오해를 주므로 숨김
        self.recent_line.setVisible(bool(stats.get("user_id")))
        self.recent_line.setText(format_recent_stats(stats))

    def _on_nickname_submitted(self) -> None:
        nickname = self.nickname_edit.text().strip()
        self.status_line.hide()
        self.detail_line.setText("조회 중...")

        stats = fetch_stats_by_nickname(nickname)
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
        self.setStyleSheet("color: white; font-weight: bold; font-size: 14px; padding: 6px;")
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event):  # noqa: N802 (Qt 이벤트 이름)
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._window.pos()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_offset is not None:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._drag_offset = None


class OverlayWindow(QWidget):
    """팀원 카드들을 보여주는 항상-위 창."""

    def __init__(self, team_stats: list[dict]):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # 작업 표시줄에 안 뜸
        )
        # 뜰 때 게임 포커스를 뺏지 않음 (클릭하면 그때 활성화)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("background-color: #1e1e1e;")
        self.setFixedWidth(WINDOW_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(6)
        layout.addWidget(DraggableHeader("🎮 팀원 전적  (이름 클릭해서 수정 가능)", self))

        cards = QWidget()
        cards.setStyleSheet("background-color: transparent;")
        cards_layout = QVBoxLayout(cards)
        cards_layout.setSpacing(6)
        for stats in team_stats:
            cards_layout.addWidget(TeammateRow(stats))
        cards_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: transparent; border: none;")
        scroll.setWidget(cards)
        layout.addWidget(scroll)

        close_btn = QPushButton("닫기")
        close_btn.setStyleSheet("background-color: #333; color: white; border: none; padding: 6px;")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self.place_on_screen()

    def place_on_screen(self) -> None:
        """마우스가 있는 모니터(보통 게임 화면)의 오른쪽 위에 놓습니다.

        Qt 좌표는 Windows 배율이 적용된 논리 좌표라 고정 좌표를 쓰면 안 됨
        (예: 2880x1800 + 배율 200%는 논리 1440x900).
        """
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.adjustSize()
        width = min(self.width(), geo.width())
        height = min(self.height(), geo.height())
        x = max(geo.left(), geo.right() - width - SCREEN_MARGIN + 1)
        y = geo.top() + min(SCREEN_MARGIN, max(0, geo.height() - height))
        self.move(x, y)
