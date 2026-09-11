import sys
import os
from typing import Optional, List, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFrame,
    QScrollArea,
)

from dotenv import load_dotenv
from bserpy import Client
from bserpy.utils import SeasonHelper


# .env 파일에서 API 키 로드
load_dotenv()
API_KEY = os.getenv("ETERNAL_RETURN_API_KEY")

# 캐릭터 코드 → 이름 매핑 (전역 변수)
CHARACTER_NAMES = {}


def load_character_names():
    """API에서 캐릭터 코드 → 이름 매핑을 로드합니다."""
    global CHARACTER_NAMES
    
    if not API_KEY:
        raise RuntimeError("API 키가 없어 캐릭터 이름을 로드할 수 없습니다.")
    
    try:
        with Client(api_key=API_KEY) as client:
            # 1. Character 데이터에서 code와 영어 이름 가져오기
            character_data = client.meta.get_data("Character")
            
            if not character_data:
                raise RuntimeError("Character 데이터가 비어있습니다.")
            
            # 2. l10n 데이터에서 한글 이름 가져오기
            # L10nData 객체가 dict처럼 동작하는지 확인
            l10n_data = client.meta.get_l10n_parsed()
            
            # l10n 데이터에서 Character/Name/숫자 → 한글 이름 매핑
            l10n_dict = {}
            if hasattr(l10n_data, 'data'):
                l10n_dict = l10n_data.data
            elif hasattr(l10n_data, '_data'):
                l10n_dict = l10n_data._data
            else:
                # dict로 변환 시도
                try:
                    l10n_dict = dict(l10n_data)
                except:
                    # __getitem__으로 접근 시도
                    l10n_dict = {}
                    for key in dir(l10n_data):
                        if key.startswith("Character/"):
                            value = getattr(l10n_data, key)
                            l10n_dict[key] = value
            
            # 3. Character 데이터와 l10n 데이터 조합
            for char in character_data:
                if isinstance(char, dict):
                    code = char.get("code") or char.get("characterCode")
                else:
                    code = getattr(char, "code", None) or getattr(char, "characterCode", None)
                
                if code:
                    # l10n에서 한글 이름 찾기 (Character/Name/숫자 형식)
                    key = f"Character/Name/{code}"
                    if key in l10n_dict:
                        CHARACTER_NAMES[code] = l10n_dict[key]
                    else:
                        # 영어 이름 사용 (fallback)
                        if isinstance(char, dict):
                            name = char.get("name") or char.get("characterName")
                        else:
                            name = getattr(char, "name", None) or getattr(char, "characterName", None)
                        
                        if name:
                            CHARACTER_NAMES[code] = name
            
            if not CHARACTER_NAMES:
                raise RuntimeError("캐릭터 이름 데이터가 비어있습니다.")
            
            print(f"✅ 캐릭터 이름 {len(CHARACTER_NAMES)}개 로드 완료")
            print(f"  예시: {list(CHARACTER_NAMES.items())[:5]}")
            
    except Exception as e:
        raise RuntimeError(f"캐릭터 이름 로드 실패: {e}")

def get_top_character(character_stats) -> tuple:
    """character_stats에서 가장 많이 플레이한 캐릭터의 (이름, 판수)를 찾습니다."""
    if not character_stats:
        return "?", 0
    
    try:
        if isinstance(character_stats, list):
            if len(character_stats) == 0:
                return "?", 0
            
            top_char = max(character_stats, key=lambda x: getattr(x, 'total_games', 0))
            character_code = getattr(top_char, 'character_code', 0)
            games = getattr(top_char, 'total_games', 0)
            
            if character_code in CHARACTER_NAMES:
                return CHARACTER_NAMES[character_code], games
            else:
                print(f"  ⚠️ character_code {character_code}를 CHARACTER_NAMES에서 찾을 수 없음")
                return f"코드{character_code}", games
        
        elif isinstance(character_stats, dict):
            char_list = character_stats.get("characterStats", [])
            if not char_list:
                return "?", 0
            
            top_char = max(char_list, key=lambda x: x.get("total_games", 0))
            character_code = top_char.get("character_code", 0)
            games = top_char.get("total_games", 0)
            
            if character_code in CHARACTER_NAMES:
                return CHARACTER_NAMES[character_code], games
            else:
                return f"코드{character_code}", games
    
    except Exception as e:
        print(f"  캐릭터 정보 파싱 실패: {e}")
    
    return "?", 0

def get_team_stats_from_api(nicknames: List[str]) -> List[Dict]:
    """실제 API에서 팀원들의 전적 데이터를 조회합니다."""
    if not API_KEY:
        print("❌ API 키가 없습니다. .env 파일을 확인하세요.")
        sys.exit(1)
    if not nicknames:
        print("❌ 닉네임이 비어있습니다.")
        sys.exit(1)

    team_stats = []
    try:
        with Client(api_key=API_KEY) as client:
            seasons = SeasonHelper(client)
            current_season = seasons.current_season()
            if not current_season:
                print("⚠️ 현재 진행 중인 시즌이 없습니다.")
                sys.exit(1)

            season_id = current_season["seasonID"]
            print(f"현재 시즌: {current_season['seasonName']} (ID: {season_id})")

            for nickname in nicknames:
                print(f"\n🔍 '{nickname}' 조회 중...")
                try:
                    team_stats.append(_fetch_single_user_stats(client, nickname, season_id))
                except Exception as e:
                    print(f"  '{nickname}' 조회 실패: {e}")
                    team_stats.append(_failed_stats(nickname))
    except Exception as e:
        print(f"API 연결 실패: {e}")
        sys.exit(1)

    return team_stats


def get_tier_name(mmr: int) -> str:
    """MMR 점수를 기반으로 티어 이름과 세부 단계를 반환합니다."""
    
    # 미스릴 이상 (단계 없음)
    if mmr >= 8300:
        return "이터니티"
    elif mmr >= 7600:
        return "미스릴"
    
    # 메테오라이트 (IV ~ I)
    elif mmr >= 7300:
        return "메테오라이트 I"
    elif mmr >= 7000:
        return "메테오라이트 II"
    elif mmr >= 6700:
        return "메테오라이트 III"
    elif mmr >= 6400:
        return "메테오라이트 IV"
    
    # 다이아몬드 (IV ~ I)
    elif mmr >= 6050:
        return "다이아몬드 I"
    elif mmr >= 5700:
        return "다이아몬드 II"
    elif mmr >= 5350:
        return "다이아몬드 III"
    elif mmr >= 5000:
        return "다이아몬드 IV"
    
    # 플래티넘 (IV ~ I)
    elif mmr >= 4650:
        return "플래티넘 I"
    elif mmr >= 4300:
        return "플래티넘 II"
    elif mmr >= 3950:
        return "플래티넘 III"
    elif mmr >= 3400:
        return "플래티넘 IV"
    
    # 골드 (IV ~ I)
    elif mmr >= 3300:
        return "골드 I"
    elif mmr >= 3000:
        return "골드 II"
    elif mmr >= 2700:
        return "골드 III"
    elif mmr >= 2400:
        return "골드 IV"
    
    # 실버 (IV ~ I)
    elif mmr >= 2150:
        return "실버 I"
    elif mmr >= 1900:
        return "실버 II"
    elif mmr >= 1650:
        return "실버 III"
    elif mmr >= 1400:
        return "실버 IV"
    
    # 브론즈 (IV ~ I)
    elif mmr >= 1200:
        return "브론즈 I"
    elif mmr >= 1000:
        return "브론즈 II"
    elif mmr >= 800:
        return "브론즈 III"
    elif mmr >= 600:
        return "브론즈 IV"
    
    # 아이언 (IV ~ I)
    elif mmr >= 450:
        return "아이언 I"
    elif mmr >= 300:
        return "아이언 II"
    elif mmr >= 150:
        return "아이언 III"
    elif mmr > 0:
        return "아이언 IV"
    
    else:
        return "언랭크"

def _fetch_single_user_stats(client, nickname: str, season_id) -> Dict:
    """단일 유저의 랭크+통계 정보를 조회해서 dict로 반환합니다.
    (get_team_stats_from_api / refetch_stats_for_nickname 공용 헬퍼)
    실패해도 예외를 던지지 않고 기본값이 채워진 dict를 반환합니다.
    """
    user = client.users.get_uid(nickname)
    user_num = user.user_id

    # 랭크 조회
    try:
        rank = client.users.get_rank(user_num, season_id=season_id)
        mmr = rank.mmr
        tier = get_tier_name(mmr)
    except Exception as e:
        print(f"  랭크 조회 실패: {e}")
        tier, mmr = "언랭크", 0

    # 통계 조회 (기본값을 먼저 세팅해서 NameError 방지)
    games = top1 = top2 = top3 = average_rank = 0
    top_character, top_character_games = "?", 0
    try:
        stats = client.users.get_stats(user_num, season_id=season_id)
        if isinstance(stats, list) and len(stats) > 0:
            user_stats = stats[0]
            games = getattr(user_stats, 'total_games', 0)
            top1 = getattr(user_stats, 'top1', 0) * 100
            top2 = getattr(user_stats, 'top2', 0) * 100
            top3 = getattr(user_stats, 'top3', 0) * 100
            average_rank = round(getattr(user_stats, 'average_rank', 0), 1)

            character_stats = getattr(user_stats, 'character_stats', [])
            if character_stats:
                top_character, top_character_games = get_top_character(character_stats)
        print(f"  {nickname}: {tier}, 승률 {top1:.0f}% (게임 수: {games}), 모스트 {top_character} ({top_character_games}판)")
    except Exception as e:
        print(f"  통계 조회 실패: {e}")

    return {
        "nickname": nickname,
        "tier": tier,
        "top_character": top_character,
        "top_character_games": top_character_games,
        "mmr": mmr,
        "games": games,
        "top1": top1,
        "top2": top2,
        "top3": top3,
        "average_rank": average_rank,
        "user_id": str(user_num),
        "season_id": season_id,
    }


def _failed_stats(nickname: str) -> Dict:
    """조회 실패 시 채워 넣는 기본 dict (두 함수 공용)"""
    return {
        "nickname": nickname,
        "tier": "조회 실패",
        "top_character": "?",
        "top_character_games": 0,
        "mmr": 0,
        "games": 0,
        "top1": 0,
        "top2": 0,
        "top3": 0,
        "average_rank": 0,
        "user_id": None,
        "season_id": None,
    }

class TeammateRow(QFrame):
    def __init__(self, stats):
        super().__init__()
        self.setStyleSheet(
            "background-color: #2a2a2a; border-radius: 6px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        self.nickname_edit = QLineEdit(stats["nickname"])
        self.nickname_edit.setStyleSheet(
            "color: #ffd166; font-weight: bold; font-size: 13px;"
            "background: transparent; border: none; padding: 0;"
        )
        self.nickname_edit.returnPressed.connect(self._on_nickname_submitted)
        layout.addWidget(self.nickname_edit)

        self.tier_line = QLabel()
        self.tier_line.setStyleSheet("color: #ffd700; font-size: 11px; font-weight: bold;")
        layout.addWidget(self.tier_line)

        self.detail_line = QLabel()
        self.detail_line.setStyleSheet("color: #cccccc; font-size: 10px;")
        layout.addWidget(self.detail_line)

        self.status_line = QLabel("")
        self.status_line.setStyleSheet("color: #ff6b6b; font-size: 10px;")
        self.status_line.hide()
        layout.addWidget(self.status_line)

        # 초기 표시도 동일한 업데이트 로직을 재사용
        self._apply_stats(stats)

    def _build_tier_text(self, stats):
        tier_text = f"🏆 {stats['tier']}"
        if stats.get('mmr', 0) > 0:
            tier_text += f" (MMR: {stats['mmr']})"
        return tier_text

    def _build_detail_text(self, stats):
        line1 = f"모스트 {stats['top_character']} {stats['top_character_games']}판"
        if stats.get('games', 0) > 0:
            line1 += f"  ·  전체 {stats['games']}판"
        if stats.get('average_rank', 0) > 0:
            line1 += f"  ·  평균 {stats['average_rank']:.2f}등"

        line2 = ""
        if stats.get('top1', 0) > 0:
            line2 += f"승률 {stats['top1']:.0f}%"
        if stats.get('top2', 0) > 0:
            line2 += f"  ·  2위 {stats['top2']:.0f}%"
        if stats.get('top3', 0) > 0:
            line2 += f"  ·  3위 {stats['top3']:.0f}%"

        return f"{line1}\n{line2}" if line2 else line1

    def _apply_stats(self, stats):
        """stats 딕셔너리를 받아 tier_line/detail_line UI를 갱신하는 단일 진입점"""
        self.tier_line.setText(self._build_tier_text(stats))
        self.detail_line.setText(self._build_detail_text(stats))

    def _on_nickname_submitted(self):
        new_nickname = self.nickname_edit.text().strip()
        self.status_line.hide()
        self.detail_line.setText("조회 중...")

        result = refetch_stats_for_nickname(new_nickname)
        print(f"재조회 결과: {result}")
        if result is None:
            self.detail_line.setText("이전 정보 유지됨")
            self.status_line.setText(f"'{new_nickname}' 유저를 찾을 수 없습니다.")
            self.status_line.show()
            return

        self._apply_stats(result)

def refetch_stats_for_nickname(nickname: str) -> Optional[Dict]:
    """사용자가 닉네임을 수정하고 Enter를 눌렀을 때 실제 API로 재조회합니다."""
    if not nickname.strip():
        return None
    if not API_KEY:
        print("❌ API 키가 없습니다.")
        return None

    try:
        with Client(api_key=API_KEY) as client:
            seasons = SeasonHelper(client)
            current_season = seasons.current_season()
            if not current_season:
                return None
            season_id = current_season["seasonID"]

            return _fetch_single_user_stats(client, nickname, season_id)
    except Exception as e:
        print(f"재조회 실패: {e}")
        return None


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

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet("background-color: #1e1e1e;")
        self.move(1500, 50)
        self.setFixedWidth(340)

        # 메인 레이아웃
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 10)
        main_layout.setSpacing(6)

        # 헤더
        header = DraggableHeader(
            "🎮 팀원 전적  (이름 클릭해서 수정 가능)", self
        )
        main_layout.addWidget(header)

        # 스크롤 영역
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("background-color: transparent; border: none;")
        
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background-color: transparent;")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(6)
        
        # 팀원별 카드 추가
        for stats in team_stats:
            row = TeammateRow(stats)
            scroll_layout.addWidget(row)
        
        scroll_layout.addStretch()  # 마지막에 여유 공간
        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)

        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setStyleSheet(
            "background-color: #333; color: white; border: none; padding: 6px;"
        )
        close_btn.clicked.connect(self.close)
        main_layout.addWidget(close_btn)


def parse_team_stats_from_argv():
    """명령줄 인자에서 팀원 닉네임을 파싱합니다.
    
    형식: python overlay_demo.py "닉네임1,닉네임2,닉네임3"
    """
    if len(sys.argv) > 1:
        # 쉼표로 구분된 닉네임 파싱
        nicknames = sys.argv[1].split(",")
        return [n.strip() for n in nicknames if n.strip()]
    return None


def main():
    app = QApplication(sys.argv)
    
    # 캐릭터 이름 데이터 로드 (앱 시작 시 한 번)
    try:
        load_character_names()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # 팀원 닉네임 가져오기
    nicknames = parse_team_stats_from_argv()
    
    if not nicknames:
        print("❌ 닉네임이 지정되지 않았습니다.")
        print("  사용법: python overlay_demo.py '닉네임1,닉네임2,닉네임3'")
        sys.exit(1)
    
    print(f"🔍 API에서 팀원 정보 조회 중: {nicknames}")
    team_stats = get_team_stats_from_api(nicknames)
    
    # 오버레이 창 표시
    window = OverlayWindow(team_stats)
    window.show()
    
    print("\n✅ 오버레이가 표시되었습니다.")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()