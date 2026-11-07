"""
사용자가 바꿀 수 있는 설정. 기본값이 있고, .env 또는 환경 변수로 덮어씁니다.

| 환경 변수                 | 설정                     | 기본값 |
|--------------------------|--------------------------|--------|
| ETERNAL_RETURN_API_KEY   | Open API 키 (개발용)      | 없음. 있으면 프록시 대신 Open API를 직접 호출 |
| LUMI_API_URL             | API 프록시 주소            | DEFAULT_API_URL (배포판은 이 프록시를 씀) |
| LUMI_DEBUG               | 디버그 출력/이미지 저장    | 꺼짐 (1/true로 켬) |
| LUMI_GAME_PROCESS        | 게임 프로세스 이름         | EternalReturn.exe |
| LUMI_GAME_WINDOW_TITLE   | 게임 창 제목 (부분 일치)   | Eternal Return |
| LUMI_LOG_PATH            | 게임 로그 경로             | %USERPROFILE%\\AppData\\LocalLow\\NimbleNeuron\\Eternal Return\\Player.log |

.env와 debug/ 폴더 위치(DATA_DIR): 개발할 때는 저장소 폴더, exe로 빌드하면 %APPDATA%\\lumi.

알고리즘 상수(OCR 임계값 등)는 근거와 함께 각 모듈에 있습니다 (docs/DEVELOPMENT_NOTES.md).
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

# PyInstaller로 빌드한 exe에서 실행 중인지
FROZEN = getattr(sys, "frozen", False)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# exe는 설치 폴더에 쓰지 못할 수 있고 업데이트 때 지워지므로 사용자 폴더에 저장
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "lumi") if FROZEN else PROJECT_ROOT
_DEFAULT_LOG_PATH = r"%USERPROFILE%\AppData\LocalLow\NimbleNeuron\Eternal Return\Player.log"

# API 키를 가진 프록시 서버 주소 (proxy/). 사용자는 키 없이 이 주소로 조회함
DEFAULT_API_URL: Optional[str] = "https://lumi-proxy.lumi-lookup.workers.dev"


@dataclass(frozen=True)
class Settings:
    api_key: Optional[str] = None
    api_url: Optional[str] = DEFAULT_API_URL
    debug: bool = False
    game_process_name: str = "EternalReturn.exe"
    game_window_title: str = "Eternal Return"
    log_path: str = os.path.expandvars(_DEFAULT_LOG_PATH)
    debug_dir: str = os.path.join(DATA_DIR, "debug")


def _flag(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    """DATA_DIR의 .env와 환경 변수에서 설정을 읽습니다."""
    load_dotenv(os.path.join(DATA_DIR, ".env"))
    env = os.environ
    default = Settings()
    return Settings(
        api_key=env.get("ETERNAL_RETURN_API_KEY") or None,
        api_url=(env.get("LUMI_API_URL") or DEFAULT_API_URL or "").rstrip("/") or None,
        debug=_flag(env.get("LUMI_DEBUG", "")),
        game_process_name=env.get("LUMI_GAME_PROCESS") or default.game_process_name,
        game_window_title=env.get("LUMI_GAME_WINDOW_TITLE") or default.game_window_title,
        log_path=os.path.expandvars(env.get("LUMI_LOG_PATH") or _DEFAULT_LOG_PATH),
    )
