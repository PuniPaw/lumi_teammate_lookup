"""설정: 기본값과 환경 변수 덮어쓰기."""

from lumi import config


def test_defaults(monkeypatch):
    for key in ("ETERNAL_RETURN_API_KEY", "LUMI_DEBUG", "LUMI_GAME_PROCESS", "LUMI_GAME_WINDOW_TITLE", "LUMI_LOG_PATH"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    s = config.load_settings()
    assert s.api_key is None
    assert s.debug is False
    assert s.game_process_name == "EternalReturn.exe"
    assert s.game_window_title == "Eternal Return"
    assert s.log_path.endswith("Player.log")


def test_env_overrides(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("ETERNAL_RETURN_API_KEY", "key")
    monkeypatch.setenv("LUMI_DEBUG", "true")
    monkeypatch.setenv("LUMI_GAME_PROCESS", "ER.exe")
    monkeypatch.setenv("LUMI_GAME_WINDOW_TITLE", "ER")
    monkeypatch.setenv("LUMI_LOG_PATH", "/tmp/x.log")
    monkeypatch.setenv("LUMI_TESSERACT_CMD", "/usr/bin/tesseract")
    s = config.load_settings()
    assert (s.api_key, s.debug, s.game_process_name, s.game_window_title) == ("key", True, "ER.exe", "ER")
    assert (s.log_path, s.tesseract_cmd) == ("/tmp/x.log", "/usr/bin/tesseract")
