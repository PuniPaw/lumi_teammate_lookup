"""
화면 캡처 -> 팀원별 닉네임 영역 크롭 -> OCR -> 이름 리스트 반환

이 모듈은 다른 코드(오버레이 UI, Open API 조회 등)에서 그대로 가져다
쓸 수 있도록, 캡처/전처리/OCR 로직을 함수로 정리해둔 것입니다.
디버깅용으로 직접 실행하고 싶으면 capture_test.py를 쓰세요.
"""

import mss
import pytesseract
import pygetwindow as gw
from PIL import Image, ImageOps

# ---------------------------------------------------------------------------
# Windows에서 Tesseract를 기본 경로에 설치했다면 아래 주석을 해제하세요.
# (설치 경로가 다르면 실제 경로로 수정)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# ---------------------------------------------------------------------------

# 게임 창을 찾을 때 쓰는 제목(부분 일치). 실제 창 제목이 다르면 수정하세요.
GAME_WINDOW_TITLE_KEYWORD = "Eternal Return"

# 팀원별 닉네임 영역을, 절대 픽셀이 아니라 "게임 창 크기 대비 비율(0~1)"로
# 정의합니다. 이러면 모니터가 바뀌거나 해상도가 달라져도(같은 종횡비라면)
# 자동으로 올바른 위치를 계산할 수 있습니다.
# (실제 게임 창 크기 1920x1716 기준으로 측정한 절대좌표를 비율로 환산한 값.
#  주의: 이 게임 창은 16:9(1080)가 아니라 1716 높이임 - 하단에 채팅/번역
#  패널이 포함된 크기로 보임)
CROP_REGIONS_PCT = [
    {"name": "teammate_1", "left": 0.5625, "top": 0.5449, "width": 0.0703, "height": 0.0087},
    {"name": "teammate_2", "left": 0.7109, "top": 0.5449, "width": 0.0703, "height": 0.0087},
    {"name": "teammate_3", "left": 0.8672, "top": 0.5449, "width": 0.0625, "height": 0.0087},
]


def _get_game_window_rect() -> dict:
    """이터널 리턴 창을 찾아서 (left, top, width, height)를 반환합니다.

    창을 못 찾으면 예외를 던집니다 - 게임이 켜져 있지 않거나,
    GAME_WINDOW_TITLE_KEYWORD가 실제 창 제목과 안 맞는 경우입니다.
    """
    windows = gw.getWindowsWithTitle(GAME_WINDOW_TITLE_KEYWORD)
    if not windows:
        raise RuntimeError(
            f"'{GAME_WINDOW_TITLE_KEYWORD}' 제목을 가진 창을 찾을 수 없습니다."
            "\n게임이 켜져 있는지, GAME_WINDOW_TITLE_KEYWORD가 실제 창 제목과"
            "\n맞는지 확인하세요 (작업 관리자 -> 세부 정보에서 확인 가능)."
        )
    win = windows[0]
    return {"left": win.left, "top": win.top, "width": win.width, "height": win.height}


def _resolve_crop_regions() -> list[dict]:
    """비율(CROP_REGIONS_PCT)을, 지금 실제 게임 창 위치/크기 기준의
    절대 픽셀 좌표로 환산합니다."""
    window = _get_game_window_rect()
    resolved = []
    for region in CROP_REGIONS_PCT:
        resolved.append(
            {
                "name": region["name"],
                "left": window["left"] + int(region["left"] * window["width"]),
                "top": window["top"] + int(region["top"] * window["height"]),
                "width": int(region["width"] * window["width"]),
                "height": int(region["height"] * window["height"]),
            }
        )
    return resolved


def _resolve_crop_regions_for_image(img_width: int, img_height: int) -> list[dict]:
    """이미지 파일 크기를 '창 크기'로 간주하고 비율을 절대좌표로 환산합니다.

    스크린샷 파일이 게임 창(또는 화면) 전체를 담고 있다는 전제입니다.
    """
    resolved = []
    for region in CROP_REGIONS_PCT:
        resolved.append(
            {
                "name": region["name"],
                "left": int(region["left"] * img_width),
                "top": int(region["top"] * img_height),
                "width": int(region["width"] * img_width),
                "height": int(region["height"] * img_height),
            }
        )
    return resolved


def _capture_region(sct, region: dict) -> Image.Image:
    shot = sct.grab(
        {
            "left": region["left"],
            "top": region["top"],
            "width": region["width"],
            "height": region["height"],
        }
    )
    return Image.frombytes("RGB", shot.size, shot.rgb)


def _preprocess(img: Image.Image) -> Image.Image:
    """OCR 정확도를 올리기 위한 전처리.

    닉네임이 '어두운 반투명 배경 + 흰 글씨'라서 반전이 필요하지만,
    하드 이진화(threshold)는 한글처럼 획이 얇은 글자의 안티에일리어싱
    픽셀을 날려버려 획이 끊길 수 있습니다. 대신 부드러운 반전 +
    자동 대비 보정으로 얇은 획을 최대한 보존합니다.
    또한 글자가 이미지 가장자리에 딱 붙어 있으면 Tesseract가 줄 경계를
    못 잡는 경우가 있어, 상하좌우에 흰 여백을 추가합니다.
    """
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


def _score(text: str) -> int:
    # 글자(영문/한글)는 +1, 숫자/기타 기호는 -2 (닉네임에 갑자기
    # 숫자가 잔뜩 섞여 나오는 건 대부분 오인식이므로 페널티)
    s = 0
    for ch in text:
        if ch.isalpha():
            s += 1
        elif ch.isdigit() or not ch.isspace():
            s -= 2
    return s


def _extract_latin(text: str) -> str:
    """영문/숫자만 뽑아냅니다 (eng 후보에서 노이즈 기호 제거용)."""
    return "".join(ch for ch in text if ch.isalnum() and ch.isascii())


def _extract_hangul(text: str) -> str:
    """완성형 한글 음절만 뽑아냅니다 (kor 후보에서 노이즈 기호/자모 파편
    제거용). 'ㄴ', 'ㅁ' 같은 낱자모는 대부분 오인식 잡음이라 제외합니다."""
    return "".join(ch for ch in text if "\uac00" <= ch <= "\ud7a3")


def _dedupe_consecutive(s: str) -> str:
    """연속으로 겹치는 글자를 하나로 줄입니다 ('yaa' -> 'ya').

    OCR이 폰트 특성상 글자를 겹쳐 읽는 경우를 보정하기 위한 마지막
    수단(fallback)입니다. 'sooin'처럼 진짜로 중복 글자가 있는 닉네임을
    망가뜨릴 수 있어서, 원래 후보가 다 실패했을 때만 시도하는 용도로만
    씁니다 (원래 후보를 대체하지 않고 추가로만 덧붙임)."""
    result = []
    for ch in s:
        if not result or result[-1] != ch:
            result.append(ch)
    return "".join(result)


def _run_ocr(img: Image.Image) -> dict:
    """여러 언어 조합으로 OCR을 돌려서 각 결과와, 그중 가장 그럴듯한
    결과(best)를 함께 반환합니다.

    kor+eng 결합 언어팩은 짧고 애매한 문자열(예: 소문자 영단어)을
    한글 자모나 숫자로 잘못 해석하는 경우가 있어서, eng 단독/kor 단독
    결과도 같이 뽑아보고 '문자(글자) 비중이 가장 높은' 결과를 고릅니다.

    또한 'ya발견'처럼 영문+한글이 섞인 닉네임은 eng 후보가 영문 부분만,
    kor 후보가 한글 부분만 맞는 경우가 있어서, 각각에서 유효한 글자만
    뽑아 조합한 후보(영문+한글, 한글+영문 두 순서 모두)도 추가합니다.
    """
    config = "--psm 7"
    variants = {
        "kor+eng": pytesseract.image_to_string(img, config=config, lang="kor+eng"),
        "eng": pytesseract.image_to_string(img, config=config, lang="eng"),
        "kor": pytesseract.image_to_string(img, config=config, lang="kor"),
    }
    variants = {k: v.strip() for k, v in variants.items()}

    latin_part = _extract_latin(variants["eng"])
    hangul_part = _extract_hangul(variants["kor"])
    if latin_part and hangul_part:
        variants["combined_latin_first"] = latin_part + hangul_part
        variants["combined_hangul_first"] = hangul_part + latin_part

        # 마지막 폴백: 영문 부분에서 연속 중복 글자를 줄인 버전도 시도
        # ('yaa발견' -> 'ya발견'). 원래 후보가 다 실패했을 때만 쓰이도록
        # 뒤쪽에 추가 (dict는 삽입 순서를 유지하므로 나중에 시도됨).
        deduped_latin = _dedupe_consecutive(latin_part)
        if deduped_latin != latin_part:
            variants["combined_latin_first_dedup"] = deduped_latin + hangul_part
            variants["combined_hangul_first_dedup"] = hangul_part + deduped_latin

    best_key = (
        max(variants, key=lambda k: _score(variants[k]))
        if any(variants.values())
        else "kor+eng"
    )
    return {"variants": variants, "best": variants[best_key], "best_source": best_key}


def get_teammate_ocr_results(save_debug_images: bool = False) -> list[dict]:
    """팀원별 OCR 결과(후보 전체 포함)를 CROP_REGIONS_PCT 순서대로 반환합니다.

    각 원소: {"name": "teammate_1", "best": "PuniPaw",
              "best_source": "kor+eng", "variants": {...}}

    save_debug_images=True로 두면 debug_crop_*.png / debug_processed_*.png
    파일을 같이 저장합니다 (좌표/전처리 확인용, 평소엔 필요 없음).
    """
    # 매번 실행 시점의 실제 게임 창 위치/크기를 기준으로 좌표를 다시 계산
    # (모니터가 바뀌거나 창이 이동해도 항상 정확한 위치를 계산함)
    crop_regions = _resolve_crop_regions()

    results = []
    with mss.mss() as sct:
        for region in crop_regions:
            name = region["name"]
            crop_img = _capture_region(sct, region)
            processed = _preprocess(crop_img)

            if save_debug_images:
                crop_img.save(f"debug_crop_{name}.png")
                processed.save(f"debug_processed_{name}.png")

            ocr_result = _run_ocr(processed)
            results.append({"name": name, **ocr_result})

    return results


def get_teammate_names() -> list[str]:
    """팀원 닉네임만 간단히 리스트로 받고 싶을 때 쓰는 함수.

    예: ["PuniPaw", "sooin", "ya발견"]
    """
    results = get_teammate_ocr_results(save_debug_images=False)
    return [r["best"] for r in results]


def get_teammate_ocr_results_from_image(
    image_path: str, save_debug_images: bool = False
) -> list[dict]:
    """실시간 화면 캡처 대신, 저장해둔 스크린샷 파일로 같은 파이프라인을
    테스트할 때 쓰는 함수.

    게임을 매번 실행하지 않고도 크롭 좌표/전처리/OCR을 반복 테스트할 수
    있어서 개발 중에 유용합니다. 이미지 전체가 게임 창(또는 전체화면)을
    담고 있다는 전제로, 이미지 크기를 기준으로 CROP_REGIONS_PCT를
    절대좌표로 환산합니다.

    반환 형식은 get_teammate_ocr_results()와 동일합니다.
    """
    full_img = Image.open(image_path).convert("RGB")
    crop_regions = _resolve_crop_regions_for_image(full_img.width, full_img.height)

    results = []
    for region in crop_regions:
        name = region["name"]
        box = (
            region["left"],
            region["top"],
            region["left"] + region["width"],
            region["top"] + region["height"],
        )
        crop_img = full_img.crop(box)
        processed = _preprocess(crop_img)

        if save_debug_images:
            crop_img.save(f"debug_crop_{name}.png")
            processed.save(f"debug_processed_{name}.png")

        ocr_result = _run_ocr(processed)
        results.append({"name": name, **ocr_result})

    return results


if __name__ == "__main__":
    # 모듈만 단독으로 실행했을 때 간단히 확인해볼 수 있도록
    print(get_teammate_names())