"""설정: 기본값과 환경 변수 덮어쓰기, API 클라이언트 선택, exe 실행 명령."""

import sys

from lumi import config
from lumi.api.client import client_factory
from lumi.game import process


def test_defaults(monkeypatch):
    for key in ("ETERNAL_RETURN_API_KEY", "LUMI_API_URL", "LUMI_DEBUG", "LUMI_GAME_PROCESS",
                "LUMI_GAME_WINDOW_TITLE", "LUMI_LOG_PATH"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    s = config.load_settings()
    assert s.api_key is None
    assert s.api_url == config.DEFAULT_API_URL
    assert s.debug is False
    assert s.game_process_name == "EternalReturn.exe"
    assert s.game_window_title == "Eternal Return"
    assert s.log_path.endswith("Player.log")


def test_env_overrides(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("ETERNAL_RETURN_API_KEY", "key")
    monkeypatch.setenv("LUMI_API_URL", "https://proxy.example/")
    monkeypatch.setenv("LUMI_DEBUG", "true")
    monkeypatch.setenv("LUMI_GAME_PROCESS", "ER.exe")
    monkeypatch.setenv("LUMI_GAME_WINDOW_TITLE", "ER")
    monkeypatch.setenv("LUMI_LOG_PATH", "/tmp/x.log")
    s = config.load_settings()
    assert (s.api_key, s.debug, s.game_process_name, s.game_window_title) == ("key", True, "ER.exe", "ER")
    assert s.api_url == "https://proxy.example"
    assert s.log_path == "/tmp/x.log"


def test_client_uses_key_directly_else_proxy():
    direct = client_factory(config.Settings(api_key="key", api_url="https://proxy.example"))()
    assert str(direct._transport._client.base_url).startswith("https://open-api.bser.io")
    assert direct._transport._client.headers["x-api-key"] == "key"
    direct.close()

    proxied = client_factory(config.Settings(api_key=None, api_url="https://proxy.example"))()
    assert str(proxied._transport._client.base_url).startswith("https://proxy.example")
    assert "x-api-key" not in proxied._transport._client.headers  # 키는 프록시가 붙임
    proxied.close()

    assert client_factory(config.Settings(api_key=None, api_url=None)) is None


def test_app_command(monkeypatch):
    monkeypatch.setattr(process, "FROZEN", False)
    assert process.app_command() == [sys.executable, "-m", "lumi.app"]
    # exe에서는 sys.executable이 exe 자신이라 -m을 못 씀
    monkeypatch.setattr(process, "FROZEN", True)
    assert process.app_command() == [sys.executable, "--app"]
