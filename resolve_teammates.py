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

from teammate_ocr import get_teammate_ocr_results

load_dotenv()
API_KEY = os.getenv("ETERNAL_RETURN_API_KEY")


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

        # variants 딕셔너리 값들을 후보로 사용 (중복 제거하되 순서는 유지)
        candidates = list(dict.fromkeys(result["variants"].values()))
        candidates = [c for c in candidates if c]  # 빈 문자열 제외

        found_nickname = None
        found_user_id = None

        for candidate in candidates:
            try:
                user = client.users.get_uid(candidate)
                found_nickname = candidate
                found_user_id = user.user_id
                break  # 찾았으면 더 시도할 필요 없음
            except NotFoundError:
                continue  # 이 후보는 아니었음, 다음 후보 시도
            except KeyError:
                # bserpy가 '유저 없음' 상황에서 NotFoundError 대신
                # KeyError(data["user"] 접근 실패)를 던지는 경우가 있어서
                # 이것도 '못 찾음'으로 취급하고 다음 후보로 넘어감
                continue

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