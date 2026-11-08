"""
공식 팬키트(Google Drive)에서 캐릭터 Mini 초상화만 받아 모달용 아이콘(48x48)을 만듭니다.

사용법: python -m lumi.debug.fankit_icons
결과: lumi/assets/characters/<캐릭터 코드>.png (git에 올리지 않음, 빌드 전에 실행)
신규 캐릭터가 팬키트에 추가되면 다시 실행하세요. 이미 있는 아이콘은 건너뜁니다.

팬키트 폴더는 '001. Jackie'처럼 API 캐릭터 코드로 시작하고, 그 안 '02. Default'에
Full/Half/Mini 이미지가 있습니다 (Mini는 122x160, 위쪽 정사각형이 얼굴).
"""

import html
import io
import os
import re
import time

import httpx
from PIL import Image

CHARACTER_FOLDER = "1m__ubKg-KY7TqnqbFqwHi1DVxrdBeTEW"  # Eternal Return Fankit / 01. Character
ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "characters")
ICON_SIZE = 48
_ENTRY = re.compile(r'id="entry-([\w-]+)".*?class="flip-entry-title">([^<]*)<', re.S)


def _listing(client: httpx.Client, folder_id: str) -> list[tuple[str, str]]:
    r = client.get("https://drive.google.com/embeddedfolderview", params={"id": folder_id})
    r.raise_for_status()
    return [(i, html.unescape(t).strip()) for i, t in _ENTRY.findall(r.text)]


def _icon(png: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    return image.crop((0, 0, image.width, image.width)).resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)


def main() -> None:
    os.makedirs(ICON_DIR, exist_ok=True)
    missing = []
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        for folder_id, title in _listing(client, CHARACTER_FOLDER):
            m = re.match(r"(\d+)\.", title)
            if not m:
                continue
            path = os.path.join(ICON_DIR, f"{int(m.group(1))}.png")
            if os.path.exists(path):
                continue
            default = next((i for i, t in _listing(client, folder_id) if t.startswith("02.")), None)
            files = _listing(client, default) if default else []
            mini = next((i for i, t in files if "mini" in t.lower() and t.lower().endswith(".png")), None)
            if mini is None:
                missing.append(title)  # NPC 폴더(9999. Dr. Wickeline 등)는 Mini가 없음
                continue
            r = client.get("https://drive.google.com/uc", params={"export": "download", "id": mini})
            if r.status_code != 200 or not r.content.startswith(b"\x89PNG"):
                missing.append(f"{title} (다운로드 {r.status_code})")
                continue
            _icon(r.content).save(path, optimize=True)
            print(f"  {title}")
            time.sleep(0.2)
    print(f"아이콘 {len(os.listdir(ICON_DIR))}개: {ICON_DIR}")
    if missing:
        print("Mini 이미지 없음:", ", ".join(missing))


if __name__ == "__main__":
    main()
