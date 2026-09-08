"""
Open API 연동 검증용 스크립트.

사용법:
  1) .env.example을 복사해서 .env 파일을 만들고, 발급받은 API 키를 넣습니다.
  2) pip install python-dotenv (requirements.txt에 이미 추가돼 있음)
  3) python lookup_test.py 로 실행

정상 동작하면, 테스트 닉네임의 유저 정보와 최근 시즌 랭크가 출력됩니다.
"""

import os

from dotenv import load_dotenv
from bserpy import Client

load_dotenv()  # .env 파일을 읽어서 환경변수로 등록

API_KEY = os.getenv("ETERNAL_RETURN_API_KEY")

# TODO: 실제로 존재하는 닉네임으로 바꿔서 테스트하세요 (본인 닉네임 추천)
TEST_NICKNAME = "PuniPaw"


def main():
    if not API_KEY:
        print(
            "ETERNAL_RETURN_API_KEY가 설정되지 않았습니다."
            "\n.env 파일에 키를 넣었는지 확인하세요 (.env.example 참고)."
        )
        return

    with Client(api_key=API_KEY) as client:
        print(f"'{TEST_NICKNAME}' 유저 조회 중...")
        user = client.users.get_uid(TEST_NICKNAME)

        print(f"찾음! user_id={user.user_id}")
        
        # 시즌 ID는 시즌마다 바뀌므로, 최신 시즌 번호는 공식 문서/API로
        # 확인해서 바꿔야 할 수 있습니다. 우선 임의 값으로 시도해봅니다.
        SEASON_ID = 39

        try:
            rank = client.users.get_rank(user.user_id, season_id=SEASON_ID)
            print(f"시즌 {SEASON_ID} 랭크: {rank.rank}위, MMR {rank.mmr}")
        except Exception as e:
            print(f"랭크 조회 실패 (시즌 ID가 안 맞을 수 있음): {e}")


if __name__ == "__main__":
    main()