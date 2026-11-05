"""저장된 스크린샷으로 닉네임 OCR 정확도를 확인하는 회귀 테스트.

실행: python -m pytest tests/test_ocr_images.py -v
     (pytest가 없으면: python tests/test_ocr_images.py)

EXPECTED에 (파일, 팀원 칸) -> 정답 닉네임을 적어 둡니다. 새 스크린샷을
추가하면 여기에 정답을 같이 적어 두세요.
- best 일치: OCR만으로 정답을 맞힘 (API 키가 없어도 정답이 표시됨)
- API 조회 대상 포함: API 검증(resolve_teammates)이 실제로 조회하는 후보 안에
  정답이 있음 -> API 키가 있으면 정답이 확정됨
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from resolve_teammates import _candidates_to_try  # noqa: E402
from teammate_ocr import get_teammate_ocr_results_from_image  # noqa: E402

# 정답 닉네임. None = 닉네임이 없는 화면(빈 칸)
EXPECTED = {
    "matching_lobby_screen.png": ["PuniPaw", "sooin", "ya발견"],
    "normal_matched_lobby.png": ["PuniPaw", "BlackBrave", "HYUHAN"],
    "test2.png": ["PuniPaw", "MirNight", "アンベリィ"],
    "test3.png": ["PuniPaw", "로즈만때리는루크", "마브하라"],
    "test4.png": ["PuniPaw", "静戒丨BS", "레몬데몬"],
    # 16:10 화면 (원래 2880x1800, 2000x1250으로 축소됨). 해상도/비율이 달라도
    # ui_regions()가 같은 공식으로 닉네임 위치를 찾는지 확인용
    "lobby_16x10.webp": ["PuniPaw", "12345a", "얼음마녀"],
}

# 정답이 후보 목록 안에만 있으면 되는 칸 (API 검증 단계에서 정답이 확정됨)
CANDIDATE_ONLY = {
    ("matching_lobby_screen.png", 2),  # ya발견: 'y'/'V'가 이 폰트에서 거의 같음
    ("test2.png", 2),  # アンベリィ: 작은 'ィ'를 'イィ'로 두 번 읽는 경우가 있음
}

# 아직 해결 못 한 칸 (테스트에서 제외, 개선 시 CANDIDATE_ONLY로 옮기기)
KNOWN_FAILURES = {
    # 静戒丨BS: 정답이 후보 목록(8위 안팎)엔 들어오지만 점수가 낮아 API 조회
    # 대상에서 빠짐. 静/靜(간체/번체), 丨/| 구분이 어려움.
    ("test4.png", 1),
}


def _results():
    for image, names in EXPECTED.items():
        results = get_teammate_ocr_results_from_image(os.path.join(ROOT, image))
        for idx, (expected, result) in enumerate(zip(names, results)):
            yield image, idx, expected, result


def test_nicknames():
    failures = []
    for image, idx, expected, result in _results():
        if (image, idx) in KNOWN_FAILURES:
            continue
        if (image, idx) in CANDIDATE_ONLY:
            ok = expected in _candidates_to_try(result)
        else:
            ok = result["best"] == expected
        if not ok:
            failures.append(
                f"{image}[{idx}] expected={expected!r} best={result['best']!r} "
                f"candidates={result['candidates'][:6]}"
            )
    assert not failures, "\n".join(failures)


if __name__ == "__main__":
    total = best_ok = cand_ok = 0
    for image, idx, expected, result in _results():
        total += 1
        b = result["best"] == expected
        c = expected in _candidates_to_try(result)
        best_ok += b
        cand_ok += c
        rank = result["candidates"].index(expected) + 1 if expected in result["candidates"] else "-"
        mark = "OK " if b else ("API" if c else "XX ")
        print(f"[{mark}] {image}[{idx}] expected={expected!r} best={result['best']!r} "
              f"({result['best_source']}, {result['confidence']}) rank={rank} "
              f"top={result['candidates'][:4]}")
    print(f"\nbest 일치: {best_ok}/{total}, API 조회 대상 포함: {cand_ok}/{total}")
