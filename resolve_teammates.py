"""
OCR 후보를 Open API로 조회해 실제로 존재하는 닉네임을 확정합니다.

점수순으로 후보를 조회해 처음 찾은 유저를 채택하고, 못 찾으면 '모양이 비슷한
글자'로 바꾼 변형을 몇 개 더 조회합니다. 그래도 없으면 None.

파일로 확인 (OCR + API 확정):
  python resolve_teammates.py <스크린샷>
"""

import os
import sys

from bserpy import Client, NotFoundError
from dotenv import load_dotenv

from teammate_ocr import get_teammate_ocr_results, get_teammate_ocr_results_from_image, lookalike_variants

load_dotenv()
API_KEY = os.getenv("ETERNAL_RETURN_API_KEY")

# 점수 낮은 후보(글자 일부만 읽은 것 등)는 우연히 실존하는 다른 유저와 일치할 수 있어
# 조회하지 않음 (실제로 '1BS', '一一一一'이 다른 유저로 확정된 적 있음)
MAX_CANDIDATES = 8
MIN_CANDIDATE_SCORE = 60
CANDIDATE_SCORE_MARGIN = 25  # 1등 후보와의 점수 차이 허용 범위
MIN_NICKNAME_LENGTH = 2

# '비슷한 글자' 변형 조회 개수 / 최소 길이 (짧으면 다른 유저와 우연히 일치할 위험이 큼)
MAX_LOOKALIKE_LOOKUPS = 6
MIN_LOOKALIKE_LENGTH = 3


def candidates_to_try(result: dict) -> list[str]:
    """OCR 결과에서 API로 조회할 후보 (점수순)."""
    scores = result["candidate_scores"]
    if not scores:
        return []
    threshold = max(MIN_CANDIDATE_SCORE, max(scores.values()) - CANDIDATE_SCORE_MARGIN)
    picked = [t for t in result["candidates"] if scores[t] >= threshold and len(t) >= MIN_NICKNAME_LENGTH]
    return picked[:MAX_CANDIDATES]


def lookalike_candidates(tried: list[str]) -> list[str]:
    """이미 조회한 후보들의 '비슷한 글자' 변형 ('滕田皮卡丘' -> '藤田皮卡丘')."""
    out = []
    for text in tried:
        if len(text) < MIN_LOOKALIKE_LENGTH:
            continue
        out += [v for v in lookalike_variants(text) if v not in tried and v not in out]
    return out[:MAX_LOOKALIKE_LOOKUPS]


def _lookup(client: Client, nickname: str):
    try:
        return client.users.get_uid(nickname)
    except (NotFoundError, KeyError):  # 유저가 없으면 bserpy가 KeyError를 내기도 함
        return None


def resolve_teammate_names(client: Client, ocr_results: list[dict]) -> list[dict]:
    """팀원별 확정 결과.

    반환: [{"region_name", "resolved_nickname"(또는 None), "user_id"(또는 None),
            "tried_candidates"(조회한 순서)}]
    """
    resolved = []
    for result in ocr_results:
        tried = candidates_to_try(result)
        found = None
        for nickname in tried:
            user = _lookup(client, nickname)
            if user is not None:
                found = (nickname, user.user_id)
                break
        if found is None:
            for nickname in lookalike_candidates(tried):
                tried.append(nickname)
                user = _lookup(client, nickname)
                if user is not None:
                    found = (nickname, user.user_id)
                    break

        resolved.append(
            {
                "region_name": result["name"],
                "resolved_nickname": found[0] if found else None,
                "user_id": found[1] if found else None,
                "tried_candidates": tried,
            }
        )
    return resolved


def main():
    if not API_KEY:
        print("ETERNAL_RETURN_API_KEY가 설정되지 않았습니다. .env를 확인하세요.")
        return
    if len(sys.argv) > 1:
        print(f"스크린샷 OCR 중: {sys.argv[1]}")
        ocr_results = get_teammate_ocr_results_from_image(sys.argv[1])
    else:
        print("게임 화면 캡처 + OCR 중... (매칭 화면이 떠 있어야 합니다)")
        ocr_results = get_teammate_ocr_results()

    print("\n--- OCR 결과 ---")
    for r in ocr_results:
        print(f"{r['name']}: {r['best']!r} (점수 {r['confidence']})  후보: {r['candidates'][:6]}")

    with Client(api_key=API_KEY) as client:
        resolved = resolve_teammate_names(client, ocr_results)

    print("\n--- 확정 결과 ---")
    for r in resolved:
        name = repr(r["resolved_nickname"]) if r["resolved_nickname"] else "못 찾음"
        print(f"{r['region_name']}: {name}  [조회한 후보: {r['tried_candidates']}]")


if __name__ == "__main__":
    main()
