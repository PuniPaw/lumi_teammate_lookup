"""
사용자가 바꿀 수 있는 설정. 기본값이 있고, .env 또는 환경 변수로 덮어씁니다.

| 환경 변수                 | 설정                     | 기본값 |
|--------------------------|--------------------------|--------|
| ETERNAL_RETURN_API_KEY   | Open API 키 (필수)        | 없음 |
| LUMI_DEBUG               | 디버그 출력/이미지 저장    | 꺼짐 (1/true로 켬) |
| LUMI_GAME_PROCESS        | 게임 프로세스 이름         | EternalReturn.exe |
| LUMI_GAME_WINDOW_TITLE   | 게임 창 제목 (부분 일치)   | Eternal Return |
| LUMI_LOG_PATH            | 게임 로그 경로             | %USERPROFILE%\\AppData\\LocalLow\\NimbleNeuron\\Eternal Return\\Player.log |
| LUMI_TESSERACT_CMD       | tesseract 실행 파일        | Windows 기본 설치 경로에 있으면 그것, 없으면 PATH |

알고리즘 상수(OCR 임계값 등)는 근거와 함께 각 모듈에 있습니다 (docs/DEVELOPMENT_NOTES.md).
"""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WINDOWS_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_DEFAULT_LOG_PATH = r"%USERPROFILE%\AppData\LocalLow\NimbleNeuron\Eternal Return\Player.log"


@dataclass(frozen=True)
class Settings:
    api_key: Optional[str] = None
    debug: bool = False
    game_process_name: str = "EternalReturn.exe"
    game_window_title: str = "Eternal Return"
    log_path: str = os.path.expandvars(_DEFAULT_LOG_PATH)
    tesseract_cmd: Optional[str] = None  # None이면 PATH의 tesseract
    debug_dir: str = os.path.join(PROJECT_ROOT, "debug")


def _flag(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    """.env(저장소 폴더)와 환경 변수에서 설정을 읽습니다."""
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    env = os.environ
    default = Settings()
    tesseract = env.get("LUMI_TESSERACT_CMD") or (_WINDOWS_TESSERACT if os.path.exists(_WINDOWS_TESSERACT) else None)
    return Settings(
        api_key=env.get("ETERNAL_RETURN_API_KEY") or None,
        debug=_flag(env.get("LUMI_DEBUG", "")),
        game_process_name=env.get("LUMI_GAME_PROCESS") or default.game_process_name,
        game_window_title=env.get("LUMI_GAME_WINDOW_TITLE") or default.game_window_title,
        log_path=os.path.expandvars(env.get("LUMI_LOG_PATH") or _DEFAULT_LOG_PATH),
        tesseract_cmd=tesseract,
    )
