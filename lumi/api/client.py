"""
Open API 클라이언트(bserpy Client)를 만드는 함수.

- 개발: ETERNAL_RETURN_API_KEY가 있으면 Open API를 직접 호출
- 배포: 키 없이 프록시 서버(Settings.api_url)를 호출. 프록시가 키를 붙여 Open API로 전달함
  (키를 exe에 넣으면 누구나 꺼내 쓸 수 있어서)
"""

from typing import Callable, Optional

import httpx
from bserpy import Client

from lumi.config import Settings

ClientFactory = Callable[[], Client]

PROXY_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
# bserpy는 빈 키를 거부함. 프록시로 보낼 때는 헤더에 키를 싣지 않으므로 아무 값이나
_PROXY_PLACEHOLDER_KEY = "proxy"


def client_factory(settings: Settings) -> Optional[ClientFactory]:
    """조회할 때마다 새 Client를 만드는 함수 (with 문으로 닫음). API 설정이 없으면 None."""
    if settings.api_key:
        return lambda: Client(api_key=settings.api_key)
    if settings.api_url:
        return lambda: Client(
            api_key=_PROXY_PLACEHOLDER_KEY,
            http_client=httpx.Client(base_url=settings.api_url, timeout=PROXY_TIMEOUT),
        )
    return None


MISSING_API_MESSAGE = (
    "API 설정이 없습니다. 개발할 때는 .env에 ETERNAL_RETURN_API_KEY를, "
    "프록시를 쓸 때는 LUMI_API_URL을 넣으세요."
)
