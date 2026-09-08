"""
2~4단계 검증용 스크립트: 화면 캡처 -> 팀원별 닉네임 영역 크롭 -> OCR 테스트

사용법:
  1) 이터널 리턴 캐릭터 선택(로비) 화면을 띄운 상태로 이 스크립트를 실행합니다.
  2) CROP_REGIONS에 적어둔 좌표대로 팀원별 영역이 잘리고, 각각 OCR 결과가
     콘솔에 출력됩니다.
  3) debug_crop_<이름>.png 파일들을 열어서 실제로 닉네임만 깔끔하게
     담고 있는지 확인하고, 필요하면 좌표를 미세 조정하세요.

좌표는 해상도/모니터 배치에 따라 달라지므로, 본인 환경 기준으로 맞춰야 합니다.
"""

import mss
import pytesseract
from PIL import Image

# ---------------------------------------------------------------------------
# Windows에서 Tesseract를 기본 경로에 설치했다면 아래 주석을 해제하세요.
# (설치 경로가 다르면 실제 경로로 수정)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# ---------------------------------------------------------------------------

# list_monitors.py 실행 결과로 확인한, 게임이 떠 있는 모니터 번호
MONITOR_INDEX = 2

# 팀원별 닉네임 영역 (그림판으로 좌상단/우하단 좌표를 재서 계산한 값)
# 주의: mss.grab()의 left/top은 "가상 데스크탑 전체 기준 절대좌표"입니다.
CROP_REGIONS = [
    {"name": "teammate_1", "left": 1080, "top": 943, "width": 135, "height": 18},
    {"name": "teammate_2", "left": 1365, "top": 943, "width": 135, "height": 18},
    {"name": "teammate_3", "left": 1650, "top": 943, "width": 135, "height": 18},
]


def capture_full(sct):
    """디버그용 전체 화면 캡처"""
    monitor = sct.monitors[MONITOR_INDEX]
    full_shot = sct.grab(monitor)
    full_img = Image.frombytes("RGB", full_shot.size, full_shot.rgb)
    full_img.save("debug_full.png")


def capture_region(sct, region: dict) -> Image.Image:
    shot = sct.grab(
        {
            "left": region["left"],
            "top": region["top"],
            "width": region["width"],
            "height": region["height"],
        }
    )
    return Image.frombytes("RGB", shot.size, shot.rgb)


def preprocess(img: Image.Image) -> Image.Image:
    """OCR 정확도를 올리기 위한 전처리.

    닉네임이 '어두운 반투명 배경 + 흰 글씨'라서 반전이 필요하지만,
    하드 이진화(threshold)는 한글처럼 획이 얇은 글자의 안티에일리어싱
    픽셀을 날려버려 획이 끊길 수 있습니다. 대신 부드러운 반전 +
    자동 대비 보정으로 얇은 획을 최대한 보존합니다.
    또한 글자가 이미지 가장자리에 딱 붙어 있으면 Tesseract가 줄 경계를
    못 잡는 경우가 있어, 상하좌우에 흰 여백을 추가합니다.
    """
    from PIL import ImageOps

    gray = img.convert("L")
    # 작은 텍스트(특히 한글)는 넉넉히 확대해야 인식률이 올라감
    scaled = gray.resize((gray.width * 6, gray.height * 6), Image.LANCZOS)

    # 흰 글씨/어두운 배경 -> 검은 글씨/흰 배경으로 부드럽게 반전
    inverted = ImageOps.invert(scaled)
    # 대비를 자동으로 끌어올려 글씨를 더 또렷하게
    contrasted = ImageOps.autocontrast(inverted, cutoff=1)
    # 가장자리에 흰 여백 추가 (글자가 경계에 붙어 인식 실패하는 것 방지)
    padded = ImageOps.expand(contrasted, border=30, fill=255)
    return padded


def run_ocr(img: Image.Image) -> dict:
    """여러 언어 조합으로 OCR을 돌려서 각 결과와, 그중 가장 그럴듯한
    결과(best)를 함께 반환합니다.

    kor+eng 결합 언어팩은 짧고 애매한 문자열(예: 소문자 영단어)을
    한글 자모나 숫자로 잘못 해석하는 경우가 있어서, eng 단독/kor 단독
    결과도 같이 뽑아보고 '문자(글자) 비중이 가장 높은' 결과를 고릅니다.
    """
    config = "--psm 7"
    variants = {
        "kor+eng": pytesseract.image_to_string(img, config=config, lang="kor+eng"),
        "eng": pytesseract.image_to_string(img, config=config, lang="eng"),
        "kor": pytesseract.image_to_string(img, config=config, lang="kor"),
    }
    variants = {k: v.strip() for k, v in variants.items()}

    def score(text: str) -> int:
        # 글자(영문/한글)는 +1, 숫자/기타 기호는 -2 (닉네임에 갑자기
        # 숫자가 잔뜩 섞여 나오는 건 대부분 오인식이므로 페널티)
        s = 0
        for ch in text:
            if ch.isalpha():
                s += 1
            elif ch.isdigit() or not ch.isspace():
                s -= 2
        return s

    best_key = max(variants, key=lambda k: score(variants[k])) if any(variants.values()) else "kor+eng"
    return {"variants": variants, "best": variants[best_key], "best_source": best_key}


def main():
    print("화면 캡처 중... (게임 로비 화면이 떠 있어야 합니다)")

    with mss.mss() as sct:
        capture_full(sct)

        results = {}
        for region in CROP_REGIONS:
            name = region["name"]
            crop_img = capture_region(sct, region)
            crop_img.save(f"debug_crop_{name}.png")

            processed = preprocess(crop_img)
            processed.save(f"debug_processed_{name}.png")

            results[name] = run_ocr(processed)

    print("\n--- OCR 결과 ---")
    for name, result in results.items():
        print(f"{name}: best={result['best']!r} (source={result['best_source']})")
        print(f"  전체 후보: {result['variants']}")
    print("----------------")
    print(
        "\ndebug_crop_<이름>.png 파일들을 열어서 각 영역이 닉네임을"
        "\n제대로 담고 있는지 확인하세요."
        "\n결과가 이상하면 CROP_REGIONS 좌표를 수정하고 다시 실행해보세요."
    )


if __name__ == "__main__":
    main()