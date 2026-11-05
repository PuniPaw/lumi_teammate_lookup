"""
OCR 후보 닉네임들을 Open API로 실제 검증해서, 진짜 존재하는 닉네임을
확정하는 모듈.

OCR(teammate_ocr.py)이 한 이름당 여러 후보(kor+eng/eng/kor)를 내놓는데,
그중 어느 게 정답인지 텍스트만 보고 판단하기 어려운 경우가 있었습니다.
대신 각 후보를 Open API에 실제로 조회해서, "유저 찾음" 응답이 오는
첫 번째 후보를 정답으로 채택합니다. 어느 후보도 못 찾으면 None으로 남겨서
나중에 사용자가 수동으로 고치거나 무시할 수 있게 합니다.

실행 (단독 테스트): python resolve_teammates.py
"""

import os

from dotenv import load_dotenv
from bserpy import Client, NotFoundError

from teammate_ocr import get_teammate_ocr_results, lookalike_variants

load_dotenv()
API_KEY = os.getenv("ETERNAL_RETURN_API_KEY")

# 팀원 한 명당 API로 확인해 볼 OCR 후보 최대 개수
MAX_CANDIDATES = 8

# 점수가 낮은 후보(글자 일부만 읽은 것 등)를 API에 조회하면, 우연히
# 실존하는 '다른 유저'와 일치해서 엉뚱한 전적이 뜰 수 있습니다.
# (예: '静戒丨BS'의 일부만 읽은 '1BS'가 실제 유저로 확정된 적이 있음)
# 그래서 아래 조건을 모두 만족하는 후보만 조회합니다.
MIN_CANDIDATE_SCORE = 60  # OCR 점수(0~100+) 최소값
CANDIDATE_SCORE_MARGIN = 25  # 1등 후보 점수와의 차이 허용 범위
MIN_NICKNAME_LENGTH = 2  # 한 글자 후보는 대부분 잡음


# 일반 후보로 못 찾았을 때 '모양이 비슷한 글자로 바꾼 변형'을 최대 몇 개 조회할지.
# 짧은 닉네임은 변형이 다른 유저와 우연히 일치할 위험이 커서 제외합니다.
MAX_LOOKALIKE_LOOKUPS = 6
MIN_LOOKALIKE_LENGTH = 3


def _lookalike_candidates(tried: list[str]) -> list[str]:
    """이미 시도한 후보들의 '비슷한 글자' 변형 (예: '滕田皮卡丘' -> '藤田皮卡丘')."""
    out = []
    for text in tried:
        if len(text) < MIN_LOOKALIKE_LENGTH:
            continue
        for v in lookalike_variants(text):
            if v not in tried and v not in out:
                out.append(v)
    return out[:MAX_LOOKALIKE_LOOKUPS]


def _lookup(client: Client, nickname: str):
    """닉네임으로 유저를 조회. 없으면 None."""
    try:
        return client.users.get_uid(nickname)
    except NotFoundError:
        return None
    except KeyError:
        # bserpy가 '유저 없음' 상황에서 NotFoundError 대신
        # KeyError(data["user"] 접근 실패)를 던지는 경우가 있음
        return None


def _candidates_to_try(result: dict) -> list[str]:
    """OCR 결과에서 API로 확인해 볼 후보만 점수순으로 골라냅니다."""
    scores = result.get("candidate_scores")
    if not scores:
        # 점수 정보가 없는 예전 형식의 결과
        candidates = result.get("candidates") or list(result["variants"].values())
        return list(dict.fromkeys(c for c in candidates if c))[:MAX_CANDIDATES]

    best_score = max(scores.values())
    threshold = max(MIN_CANDIDATE_SCORE, best_score - CANDIDATE_SCORE_MARGIN)
    picked = [
        text
        for text in result["candidates"]
        if scores.get(text, 0) >= threshold and len(text) >= MIN_NICKNAME_LENGTH
    ]
    return picked[:MAX_CANDIDATES]


def resolve_teammate_names(client: Client, ocr_results: list[dict]) -> list[dict]:
    """OCR 결과 리스트를 받아서, 각 팀원마다 실제로 존재하는 닉네임과
    user_id를 확정해서 반환합니다.

    반환 형식 (팀원별 하나씩):
      {
        "region_name": "teammate_1",
        "resolved_nickname": "PuniPaw" 또는 None (못 찾은 경우),
        "user_id": "..." 또는 None,
        "tried_candidates": ["PuniPaw", "PuniPaw", "0ㅁ40103"],  # 시도한 순서
      }
    """
    resolved = []

    for result in ocr_results:
        region_name = result["name"]

        # OCR 점수가 충분히 높은 후보만, 점수 높은 순으로 시도
        candidates = _candidates_to_try(result)

        found_nickname = None
        found_user_id = None

        for candidate in candidates:
            user = _lookup(client, candidate)
            if user is not None:
                found_nickname, found_user_id = candidate, user.user_id
                break  # 찾았으면 더 시도할 필요 없음

        # 못 찾았으면 '모양이 비슷한 글자'로 바꾼 변형을 몇 개 더 시도
        if found_nickname is None:
            for candidate in _lookalike_candidates(candidates):
                candidates.append(candidate)
                user = _lookup(client, candidate)
                if user is not None:
                    found_nickname, found_user_id = candidate, user.user_id
                    break

        resolved.append(
            {
                "region_name": region_name,
                "resolved_nickname": found_nickname,
                "user_id": found_user_id,
                "tried_candidates": candidates,
            }
        )

    return resolved


def main():
    if not API_KEY:
        print("ETERNAL_RETURN_API_KEY가 설정되지 않았습니다. .env를 확인하세요.")
        return

    print("화면 캡처 + OCR 중... (게임 로비 화면이 떠 있어야 합니다)")
    ocr_results = get_teammate_ocr_results(save_debug_images=True)

    with Client(api_key=API_KEY) as client:
        resolved = resolve_teammate_names(client, ocr_results)

    print("\n--- 확정 결과 ---")
    for r in resolved:
        if r["resolved_nickname"]:
            print(
                f"{r['region_name']}: '{r['resolved_nickname']}' "
                f"(user_id={r['user_id']})  [시도한 후보: {r['tried_candidates']}]"
            )
        else:
            print(
                f"{r['region_name']}: 어떤 후보도 못 찾음 "
                f"[시도한 후보: {r['tried_candidates']}]"
            )


if __name__ == "__main__":
    main()