"""닉네임 칸 이미지 정리: 테두리 제거, 빈 칸 판별."""

from PIL import Image


def trim_edge_columns(img: Image.Image) -> Image.Image:
    """좌우 끝의 밝은 세로 테두리 제거 ('|' 잡음 방지).

    닉네임 배경은 어두워 글자가 있는 열도 위/아래 끝은 어둡지만, 테두리는 열 전체가 밝음.
    """
    gray = img.convert("L")
    w, h = gray.size
    px = gray.load()

    def is_border(x: int) -> bool:
        return min(px[x, y] for y in range(h)) > 70

    left, right = 0, w
    while right - left > 1 and is_border(right - 1):
        right -= 1
    while right - left > 1 and is_border(left):
        left += 1
    return img if (left, right) == (0, w) else img.crop((left, 0, right, h))


def text_pixel_ratio(img: Image.Image) -> float:
    """배경(중앙값)보다 80 이상 밝은 픽셀 비율 = 흰 글씨가 차지하는 비율."""
    hist = img.convert("L").histogram()
    total = sum(hist)
    if total == 0:
        return 0.0
    acc = median = 0
    for value, count in enumerate(hist):
        acc += count
        if acc * 2 >= total:
            median = value
            break
    return sum(hist[median + 81 :]) / total
