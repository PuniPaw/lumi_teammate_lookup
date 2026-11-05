"""
게임 화면에서 팀원 닉네임 칸을 찾아 잘라냅니다.

- LiveScreen: 실제 게임 화면 (Windows)
- ImageScreen: 저장된 스크린샷 (테스트/디버그)

닉네임 칸 위치는 기준 해상도 1920x1080에서 잰 좌표를 ui_regions()로 변환합니다.
이터널 리턴 UI는 배율 min(가로/1920, 세로/1080)로 커지고 화면 중앙 기준으로
배치되므로, 해상도나 화면 비율이 달라도 같은 공식이 적용됩니다.
"""

import mss
from PIL import Image, ImageDraw

REFERENCE_WIDTH = 1920
REFERENCE_HEIGHT = 1080
# 기준 해상도에서의 팀원별 닉네임 칸 (px)
NAME_REGIONS_REF = [
    {"name": "teammate_1", "left": 1080, "top": 935, "width": 134, "height": 14},
    {"name": "teammate_2", "left": 1364, "top": 935, "width": 134, "height": 14},
    {"name": "teammate_3", "left": 1665, "top": 935, "width": 120, "height": 14},
]

# 위치 미세 보정: 위아래로 '칸 높이 x 이 값'만큼 넓게 캡처한 뒤, 글자가 가장
# 많이 들어오는 위치를 고릅니다.
VERTICAL_SEARCH_RATIO = 1.0
# 글자 경계로 볼 이웃 픽셀 밝기 차이 / 글자가 있다고 볼 최소 경계 수
EDGE_THRESHOLD = 60
MIN_EDGES_FOR_TEXT = 20
# 고른 구간 위아래에 더하는 여유 ('y', 'g' 꼬리 보존). 칸 높이 대비.
WINDOW_MARGIN_RATIO = 0.08


def ui_regions(width: int, height: int) -> list[dict]:
    """게임 화면(width x height)에서의 닉네임 칸 좌표. 게임 화면 왼쪽 위 기준."""
    scale = min(width / REFERENCE_WIDTH, height / REFERENCE_HEIGHT)
    cx, cy = width / 2, height / 2
    return [
        {
            "name": r["name"],
            "left": round(cx + (r["left"] - REFERENCE_WIDTH / 2) * scale),
            "top": round(cy + (r["top"] - REFERENCE_HEIGHT / 2) * scale),
            "width": max(1, round(r["width"] * scale)),
            "height": max(1, round(r["height"] * scale)),
        }
        for r in NAME_REGIONS_REF
    ]


def _search_box(region: dict, area_height: int) -> dict:
    pad = round(region["height"] * VERTICAL_SEARCH_RATIO)
    top = max(0, region["top"] - pad)
    bottom = min(area_height, region["top"] + region["height"] + pad)
    return {**region, "top": top, "height": max(region["height"], bottom - top)}


def _best_window(strip: Image.Image, height: int, expected_offset: int) -> Image.Image:
    """위아래로 넓게 캡처한 strip에서 글자가 가장 많이 들어오는 높이 height 구간.

    글자 양은 행마다 '옆 픽셀과 밝기 차이가 큰 지점'의 수로 셉니다. 닉네임 아래의
    색깔 진행 막대처럼 가로로 균일한 띠는 이 값이 거의 0이라 글자로 세지 않습니다.
    글자가 없으면 예상 위치를 그대로 씁니다.
    """
    expected_offset = min(max(0, expected_offset), max(0, strip.height - height))
    gray = strip.convert("L")
    px = gray.load()
    row_edges = [
        sum(1 for x in range(1, gray.width) if abs(px[x, y] - px[x - 1, y]) > EDGE_THRESHOLD)
        for y in range(gray.height)
    ]

    best_y, best_count = expected_offset, -1
    for y in range(max(1, gray.height - height + 1)):
        count = sum(row_edges[y : y + height])
        closer = abs(y - expected_offset) < abs(best_y - expected_offset)
        if count > best_count or (count == best_count and closer):
            best_y, best_count = y, count
    if best_count < MIN_EDGES_FOR_TEXT:
        best_y = expected_offset

    margin = max(1, round(height * WINDOW_MARGIN_RATIO))
    return strip.crop((0, max(0, best_y - margin), strip.width, min(gray.height, best_y + height + margin)))


def _grab(sct, box: dict) -> Image.Image:
    shot = sct.grab({k: box[k] for k in ("left", "top", "width", "height")})
    return Image.frombytes("RGB", shot.size, shot.rgb)


def game_window(title: str) -> dict:
    """제목에 title이 들어간 게임 창의 화면 좌표와 크기. 못 찾으면 RuntimeError.

    반환: {"left", "top", "width", "height", "title", "active"}
    """
    import pygetwindow as gw  # Windows 전용이라 실제 캡처할 때만 import

    windows = gw.getWindowsWithTitle(title)
    if not windows:
        raise RuntimeError(
            f"'{title}' 제목의 창을 찾을 수 없습니다. "
            "게임이 켜져 있는지, LUMI_GAME_WINDOW_TITLE이 창 제목과 맞는지 확인하세요."
        )
    # 같은 단어가 들어간 다른 창(브라우저 탭 등)이 있을 수 있어 가장 큰 창을 고름
    visible = [w for w in windows if not getattr(w, "isMinimized", False) and w.width > 0]
    win = max(visible or windows, key=lambda w: w.width * w.height)
    left, top, width, height = win.left, win.top, win.width, win.height

    # 창 모드에서는 제목 표시줄/테두리를 뺀 클라이언트 영역을 씀
    try:
        import win32gui

        _, _, client_w, client_h = win32gui.GetClientRect(win._hWnd)
        client_left, client_top = win32gui.ClientToScreen(win._hWnd, (0, 0))
        if client_w > 0 and client_h > 0:
            left, top, width, height = client_left, client_top, client_w, client_h
    except Exception:
        pass

    return {
        "left": left,
        "top": top,
        "width": width,
        "height": height,
        "title": win.title,
        # 화면을 보이는 그대로 캡처하므로 다른 창이 게임을 가리면 그 창을 읽게 됨
        "active": bool(getattr(win, "isActive", True)),
    }


def _game_area(img: Image.Image) -> Image.Image:
    """스크린샷 아래쪽의 흰 여백을 잘라 게임 화면만 남김 (일부 테스트 이미지용)."""
    gray = img.convert("L")
    w, h = gray.size
    bottom = h
    while bottom > 1 and gray.crop((0, bottom - 1, w, bottom)).getextrema()[0] >= 240:
        bottom -= 1
    return img if bottom == h else img.crop((0, 0, w, bottom))


def crops_from_image(image_path: str, refine: bool = True) -> list[Image.Image]:
    """저장된 스크린샷에서 capture_crops()와 같은 방식으로 닉네임 칸을 자릅니다."""
    full = _game_area(Image.open(image_path).convert("RGB"))
    crops = []
    for region in ui_regions(full.width, full.height):
        box = _search_box(region, full.height) if refine else region
        strip = full.crop((box["left"], box["top"], box["left"] + box["width"], box["top"] + box["height"]))
        if refine:
            strip = _best_window(strip, region["height"], region["top"] - box["top"])
        crops.append(strip)
    return crops


def _mark_regions(img: Image.Image) -> Image.Image:
    """닉네임 칸 위치를 빨간 박스로 표시 (칸 바깥 2px에 그려 칸 내용은 그대로)."""
    draw = ImageDraw.Draw(img)
    for r in ui_regions(img.width, img.height):
        draw.rectangle(
            (r["left"] - 2, r["top"] - 2, r["left"] + r["width"] + 2, r["top"] + r["height"] + 2),
            outline=(255, 0, 0),
            width=2,
        )
    return img


class LiveScreen:
    """실제 게임 화면 (ports.ScreenSource)."""

    def __init__(self, window_title: str):
        self.window_title = window_title

    def name_crops(self, refine: bool = True) -> list[Image.Image]:
        # 창이 움직이거나 크기가 바뀌어도 맞도록 매번 창 위치를 다시 구함
        window = game_window(self.window_title)
        crops = []
        with mss.mss() as sct:
            for region in ui_regions(window["width"], window["height"]):
                box = _search_box(region, window["height"]) if refine else region
                shot = _grab(sct, {**box, "left": window["left"] + box["left"], "top": window["top"] + box["top"]})
                if refine:
                    shot = _best_window(shot, region["height"], region["top"] - box["top"])
                crops.append(shot)
        return crops

    def is_active(self) -> bool:
        try:
            return game_window(self.window_title)["active"]
        except Exception:
            return True  # 확인할 수 없으면 경고하지 않음

    def snapshot(self) -> tuple[Image.Image, dict]:
        window = game_window(self.window_title)
        with mss.mss() as sct:
            return _mark_regions(_grab(sct, window)), window


class ImageScreen:
    """저장된 스크린샷 (ports.ScreenSource). path를 바꿔 가며 화면 전환을 흉내낼 수 있음."""

    def __init__(self, path: str):
        self.path = path

    def name_crops(self, refine: bool = True) -> list[Image.Image]:
        return crops_from_image(self.path, refine=refine)

    def is_active(self) -> bool:
        return True

    def snapshot(self) -> tuple[Image.Image, dict]:
        img = _game_area(Image.open(self.path).convert("RGB"))
        return _mark_regions(img), {"left": 0, "top": 0, "width": img.width, "height": img.height, "title": self.path}
