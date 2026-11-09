"""python -m lumi : 게임 프로세스를 감시하다가 게임이 켜지면 앱을 실행합니다.

--app 을 붙이면 감시 없이 앱(lumi.app)을 바로 실행합니다. exe로 빌드하면 감시 프로세스가
자기 자신(exe)을 --app 으로 다시 실행합니다 (lumi.game.process.app_command).
"""

import os
import sys

from lumi.config import DATA_DIR, FROZEN, load_settings
from lumi.logfile import setup_log

if __name__ == "__main__":
    is_app = "--app" in sys.argv[1:]
    if FROZEN:
        setup_log(os.path.join(DATA_DIR, "logs"), "app" if is_app else "watch")
    if is_app:
        from lumi.app import main

        main()
    else:
        from lumi.game.process import watch

        watch(load_settings())
