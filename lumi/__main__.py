"""python -m lumi : 게임 프로세스를 감시하다가 게임이 켜지면 앱을 실행합니다."""

from lumi.config import load_settings
from lumi.game.process import watch

if __name__ == "__main__":
    watch(load_settings())
