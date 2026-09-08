"""
오버레이 UI 데모 (mock 데이터 버전) - PySide6(Qt) 사용.

tkinter의 overrideredirect(테두리 없는 창) 방식은 빠른 드래그 시
재귀 오류(RecursionError)와 화면 잔상 문제가 있어서, 더 안정적인
Qt(PySide6)로 바꿨습니다. Qt는 프레임 없는 항상-위 창과 드래그를
훨씬 안정적으로 처리합니다.

나중에 할 일: get_mock_team_stats() 함수를 실제 bserpy 조회 결과로
교체하면 그대로 실전 투입 가능합니다. (다른 부분은 안 건드려도 됨)

실행: python overlay_demo.py
- 화면 우측 상단에 항상 위(always-on-top)로 뜨는 작은 창이 나타납니다.
- 상단 헤더를 마우스로 눌러서 끌면 창을 옮길 수 있습니다.
- 닫으려면 "닫기" 버튼을 누르세요.
"""

import sys

from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
)


def get_mock_team_stats():
    """실제로는 OCR로 얻은 닉네임 -> bserpy로 조회한 전적으로 교체될 부분.

    지금은 UI를 미리 완성해두기 위한 가짜 데이터입니다.
    """
    return [
        {
            "nickname": "PuniPaw",
            "tier": "다이아 II",
            "win_rate": "34%",
            "top_character": "재키",
            "comment": "이 분 요즘 폼 미쳤는데? 조심하자",
        },
        {
            "nickname": "sooin",
            "tier": "플래티넘 I",
            "win_rate": "28%",
            "top_character": "아디나",
            "comment": "무난한 실력, 평범하게 가면 될 듯",
        },
        {
            "nickname": "ya발견",
            "tier": "골드 III",
            "win_rate": "19%",
            "top_character": "실비아",
            "comment": "부담 갖지 말고 편하게 캐리해보자",
        },
    ]


class TeammateRow(QFrame):
    def __init__(self, stats):
        super().__init__()
        self.setStyleSheet(
            "background-color: #2a2a2a; border-radius: 6px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        name_line = QLabel(f"{stats['nickname']}  |  {stats['tier']}")
        name_line.setStyleSheet(
            "color: #ffd166; font-weight: bold; font-size: 13px;"
        )
        layout.addWidget(name_line)

        detail_line = QLabel(
            f"승률 {stats['win_rate']}  ·  최고 숙련 {stats['top_character']}"
        )
        detail_line.setStyleSheet("color: #cccccc; font-size: 11px;")
        layout.addWidget(detail_line)

        comment_line = QLabel(f"💬 {stats['comment']}")
        comment_line.setStyleSheet(
            "color: #8ecae6; font-size: 11px; font-style: italic;"
        )
        comment_line.setWordWrap(True)
        layout.addWidget(comment_line)


class DraggableHeader(QLabel):
    """헤더를 누른 채 끌면 부모 창(OverlayWindow)이 따라 움직임."""

    def __init__(self, text, parent_window):
        super().__init__(text)
        self._parent_window = parent_window
        self._drag_offset = None
        self.setStyleSheet(
            "color: white; font-weight: bold; font-size: 14px; padding: 6px;"
        )
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 창 좌상단 기준, 클릭한 지점의 상대 좌표를 저장
            self._drag_offset = (
                event.globalPosition().toPoint() - self._parent_window.pos()
            )

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self._parent_window.move(new_pos)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None


class OverlayWindow(QWidget):
    def __init__(self, team_stats):
        super().__init__()

        # 테두리 없는 창 + 항상 위에 표시
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet("background-color: #1e1e1e;")
        self.move(1500, 50)  # 화면 우측 상단 초기 위치 (필요시 조정)
        self.setFixedWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(6)

        header = DraggableHeader("🎮 팀원 전적  (여기를 끌어서 이동)", self)
        layout.addWidget(header)

        for stats in team_stats:
            layout.addWidget(TeammateRow(stats))

        close_btn = QPushButton("닫기")
        close_btn.setStyleSheet(
            "background-color: #333; color: white; border: none; padding: 6px;"
        )
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)


def main():
    app = QApplication(sys.argv)
    team_stats = get_mock_team_stats()
    window = OverlayWindow(team_stats)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()