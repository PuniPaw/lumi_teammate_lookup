"""저장된 게임 화면으로 닉네임 인식 정확도를 확인하는 회귀 테스트.

새 스크린샷을 tests/fixtures/에 넣으면 EXPECTED에 정답도 적어 두세요.
- 기본: OCR 1순위가 정답
- API_RESOLVED: API로 조회하는 후보(+ 비슷한 글자 변형) 안에 정답이 있으면 통과

정확도 요약 출력: python tests/test_ocr_images.py
"""

from PIL import Image

from conftest import fixture, name_crops
from lumi.api.resolve import candidates_to_try, lookalike_candidates
from lumi.ocr.reader import TesseractReader

reader = TesseractReader()

EXPECTED = {
    "matching_lobby_screen.png": ["PuniPaw", "sooin", "ya발견"],
    "normal_matched_lobby.png": ["PuniPaw", "BlackBrave", "HYUHAN"],
    "test2.png": ["PuniPaw", "MirNight", "アンベリィ"],
    "test3.png": ["PuniPaw", "로즈만때리는루크", "마브하라"],
    "test4.png": ["PuniPaw", "静戒丨BS", "레몬데몬"],
    # 16:10 실게임 화면 (2880x1800을 2000x1250으로 축소한 것)
    "lobby_16x10.webp": ["PuniPaw", "12345a", "얼음마녀"],
    "lobby_16x10_chinese.webp": ["PuniPaw", "藤田皮卡丘", "불법체류자엠마"],
    "lobby_16x10_portrait.webp": ["PuniPaw", "라비에오", "124qer123"],
}

API_RESOLVED = {
    ("matching_lobby_screen.png", 2),  # 'y'와 'V'가 이 폰트에서 거의 같음
    ("test2.png", 2),  # 작은 'ィ'를 'イィ'로 읽기도 함
    ("test4.png", 1),  # 靜戒|BS -> 비슷한 글자 변형
    ("lobby_16x10_chinese.webp", 1),  # 첫 글자를 騰/滕/朋 등으로 읽음 -> 비슷한 글자 변형
}


def api_tried(result: dict) -> list[str]:
    tried = candidates_to_try(result)
    return tried + lookalike_candidates(tried)


def _results():
    for image, names in EXPECTED.items():
        for idx, (expected, result) in enumerate(zip(names, reader.read(name_crops(image)))):
            yield image, idx, expected, result


def test_nicknames():
    failures = []
    for image, idx, expected, result in _results():
        ok = expected in api_tried(result) if (image, idx) in API_RESOLVED else result["best"] == expected
        if not ok:
            failures.append(f"{image}[{idx}] {expected!r}: best={result['best']!r} 후보={result['candidates'][:6]}")
    assert not failures, "\n".join(failures)


def test_native_resolution_crop():
    """실게임 2880x1800 원본 크롭"""
    crop = Image.open(fixture("crop_2880x1800_fujita.png")).convert("RGB")
    assert "藤田皮卡丘" in api_tried(reader.read([crop])[0])


if __name__ == "__main__":
    total = best_ok = api_ok = 0
    for image, idx, expected, result in _results():
        total += 1
        best_ok += result["best"] == expected
        api_ok += expected in api_tried(result)
        mark = "OK " if result["best"] == expected else ("API" if expected in api_tried(result) else "XX ")
        print(f"[{mark}] {image}[{idx}] {expected!r}: best={result['best']!r} ({result['confidence']})")
    print(f"\n1순위 정답: {best_ok}/{total}, API 조회 대상 포함: {api_ok}/{total}")
