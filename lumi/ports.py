"""
앱(lumi/app.py)이 외부 세계와 닿는 지점의 인터페이스.

app.py는 이 인터페이스에만 의존하고, 실제 구현(어댑터)은 실행 시작점에서
설정(config.Settings)으로 만들어 넘깁니다. 테스트에서는 가짜 구현을 넘깁니다.

| 인터페이스         | 실제 구현                                  |
|-------------------|-------------------------------------------|
| ScreenSource      | capture.screen.LiveScreen (게임 화면)       |
|                   | capture.screen.ImageScreen (스크린샷 파일)   |
| NicknameReader    | ocr.reader.TesseractReader                  |
| StatsProvider     | api.player_stats.EternalReturnStats         |
| MatchSignals      | game.log.PlayerLog                          |
"""

from typing import Iterator, Optional, Protocol

from PIL import Image


class ScreenSource(Protocol):
    def name_crops(self, refine: bool = True) -> list[Image.Image]:
        """팀원 닉네임 칸 이미지들. refine=False는 미세 보정 없이 항상 같은 위치."""

    def is_active(self) -> bool:
        """게임 화면이 다른 창에 가려지지 않았는지."""

    def snapshot(self) -> tuple[Image.Image, dict]:
        """디버그용 전체 화면 (닉네임 칸 표시)과 창 정보."""


class NicknameReader(Protocol):
    def read(self, crops: list[Image.Image]) -> list[dict]:
        """칸별 OCR 결과: {"name", "best", "confidence", "candidates", "candidate_scores", "crop_image"}"""


class StatsProvider(Protocol):
    def team_stats(self, ocr_results: list[dict]) -> list[dict]:
        """OCR 결과로 닉네임을 확정하고 팀원별 전적 dict를 만듭니다."""

    def user_stats(self, nickname: str) -> Optional[dict]:
        """닉네임 한 명의 전적. 못 찾으면 None (모달에서 닉네임 수정 시)."""


class MatchSignals(Protocol):
    def matches(self) -> Iterator[None]:
        """매칭 완료 신호가 올 때마다 하나씩 (무한 반복)."""
