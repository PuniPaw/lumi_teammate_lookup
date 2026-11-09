"""
공식 팬키트(Google Drive)에서 캐릭터 Mini 초상화만 받아 모달용 아이콘(48x48)을 만듭니다.

사용법: python -m lumi.debug.fankit_icons
결과: lumi/assets/characters/<API 캐릭터 코드>.png (git에 올리지 않음, 빌드 전에 실행)
신규 캐릭터가 팬키트에 추가되면 다시 실행하세요. 매번 처음부터 다시 만듭니다.

팬키트 폴더는 '001. Jackie'처럼 번호로 시작하지만, 이 번호는 API 캐릭터 코드와 다를 수 있습니다
(2026-11-08: 피오라, 자히르, 현우, 키아라, 시셀라, 실비아, 아드리아나, 쇼이치 8명이 달랐음).
그래서 폴더의 영문 이름을 API 캐릭터 데이터의 영문 이름(name)과 맞춰 코드를 정합니다.
폴더 안 '02. Default'에 Full/Half/Mini 이미지가 있습니다 (Mini는 122x160, 위쪽 정사각형이 얼굴).
"""

import html
import io
import os
import re
import shutil
import time
import unicodedata

import httpx
from PIL import Image

CHARACTER_FOLDER = "1m__ubKg-KY7TqnqbFqwHi1DVxrdBeTEW"  # Eternal Return Fankit / 01. Character
ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "characters")
ICON_SIZE = 48
_ENTRY = re.compile(r'id="entry-([\w-]+)".*?class="flip-entry-title">([^<]*)<', re.S)


def name_key(name: str) -> str:
    """'István' -> 'istvan', 'Li Dailin' -> 'lidailin' (악센트, 공백, 기호 무시)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())


def match_folders(folder_titles: list[str], api_names: dict[int, str]) -> tuple[dict[str, int], list[str]]:
    """팬키트 폴더 제목 -> API 캐릭터 코드. 이름이 맞는 API 캐릭터가 없는 폴더(NPC 등)는 따로 돌려줌."""
    codes = {name_key(name): code for code, name in api_names.items()}
    matched, unmatched = {}, []
    for title in folder_titles:
        name = re.sub(r"^\d+\.\s*", "", title)
        code = codes.get(name_key(name))
        if code is None:
            unmatched.append(title)
        else:
            matched[title] = code
    return matched, unmatched


def _listing(client: httpx.Client, folder_id: str) -> list[tuple[str, str]]:
    r = client.get("https://drive.google.com/embeddedfolderview", params={"id": folder_id})
    r.raise_for_status()
    return [(i, html.unescape(t).strip()) for i, t in _ENTRY.findall(r.text)]


def _icon(png: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    return image.crop((0, 0, image.width, image.width)).resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)


def _api_character_names() -> dict[int, str]:
    from lumi.api.client import client_factory
    from lumi.config import load_settings

    make_client = client_factory(load_settings())
    if make_client is None:
        raise SystemExit("API 설정이 없어 캐릭터 코드를 알 수 없습니다 (.env 또는 프록시 주소)")
    with make_client() as client:
        return {c["code"]: c["name"] for c in client.meta.get_data("Character")}


def main() -> None:
    api_names = _api_character_names()
    shutil.rmtree(ICON_DIR, ignore_errors=True)  # 예전 번호 기준 아이콘이 남지 않게
    os.makedirs(ICON_DIR)
    problems = []
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        folders = [(i, t) for i, t in _listing(client, CHARACTER_FOLDER) if re.match(r"\d+\.", t)]
        matched, unmatched = match_folders([t for _, t in folders], api_names)
        for folder_id, title in folders:
            code = matched.get(title)
            if code is None:
                continue
            default = next((i for i, t in _listing(client, folder_id) if t.startswith("02.")), None)
            files = _listing(client, default) if default else []
            mini = next((i for i, t in files if "mini" in t.lower() and t.lower().endswith(".png")), None)
            if mini is None:
                problems.append(f"{title} (Mini 이미지 없음)")
                continue
            r = client.get("https://drive.google.com/uc", params={"export": "download", "id": mini})
            if r.status_code != 200 or not r.content.startswith(b"\x89PNG"):
                problems.append(f"{title} (다운로드 {r.status_code})")
                continue
            _icon(r.content).save(os.path.join(ICON_DIR, f"{code}.png"), optimize=True)
            print(f"  {title} -> 코드 {code} {api_names[code]}")
            time.sleep(0.2)
    print(f"아이콘 {len(os.listdir(ICON_DIR))}개 / API 캐릭터 {len(api_names)}명: {ICON_DIR}")
    no_icon = sorted(set(api_names) - set(matched.values()))
    if no_icon:
        print("팬키트 폴더가 없는 캐릭터:", ", ".join(f"{c} {api_names[c]}" for c in no_icon))
    if unmatched:
        print("API 캐릭터와 이름이 안 맞는 폴더 (NPC 등):", ", ".join(unmatched))
    if problems:
        print("실패:", ", ".join(problems))


if __name__ == "__main__":
    main()
