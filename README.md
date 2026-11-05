# lumi-teammate-lookup

이터널 리턴에서 매칭이 잡히면 팀원 닉네임을 화면에서 읽어(OCR) 전적을 모달로 보여주고, 게임이 시작되면 모달을 닫습니다.

모달에 표시되는 정보 (팀원별):
- 현재 시즌 랭크 티어 / MMR
- 모스트 캐릭터, 판수, 평균 순위, 승률(1·2·3위 비율)
- 최근 20게임(일반+랭크) 평균 딜량, 평균 TK

## 준비

1. Tesseract OCR 설치 (Windows 기본 경로 `C:\Program Files\Tesseract-OCR`)
   - 언어팩: Korean, Japanese, Chinese (Simplified), Chinese (Traditional) 추가 선택
2. 패키지 설치
   ```
   pip install -r requirements.txt
   ```
3. 저장소 폴더에 `.env` 파일
   ```
   ETERNAL_RETURN_API_KEY=발급받은 키
   ```

## 실행

```
python game_watcher.py
```
게임이 켜지면 `live_overlay.py`가 자동으로 실행됩니다. 게임 창을 맨 앞에 두세요 (화면을 보이는 그대로 캡처합니다).

## 구조

| 파일 | 역할 |
|---|---|
| `game_watcher.py` | 게임 프로세스 감시, `live_overlay.py` 실행/종료 |
| `live_overlay.py` | 매칭 감지 → OCR → 전적 조회 → 모달 표시/닫기 |
| `log_watcher.py` | `Player.log`에서 매칭 완료 감지 |
| `screen_capture.py` | 게임 창 찾기, 해상도별 닉네임 칸 위치 계산, 캡처 |
| `teammate_ocr.py` | 닉네임 칸 OCR → 점수순 후보 |
| `resolve_teammates.py` | 후보를 Open API로 조회해 닉네임 확정 |
| `player_stats.py` | 티어/시즌 통계/최근 게임 조회 |
| `recent_stats.py` | 최근 N게임 평균 딜량/TK |
| `match_flow.py` | OCR 재시도, 게임 시작(닉네임 칸 사라짐) 판단 |
| `overlay.py` | 모달 UI (PySide6) |
| `debug_store.py`, `debug_crops.py` | 디버그 이미지 저장/분석 |

## 문제 확인

- 스크린샷으로 OCR + API 확정까지 확인: `python resolve_teammates.py <스크린샷>`
- 닉네임 칸을 원본 해상도로 잘라 보기: `python debug_crops.py <스크린샷>`
- 매칭 관련 로그 확인: `python log_watcher.py`
- 디버그 이미지 저장 켜기: `.env`에 `LUMI_DEBUG=1` → `debug/`에 매 판 닉네임 칸, 실패한 판은 게임 화면 저장 (최근 20판 유지)

## 테스트

```
pip install pytest
python -m pytest tests
```
`tests/fixtures/`의 실제 게임 화면으로 닉네임 인식 정확도를 확인합니다 (`python tests/test_ocr_images.py`로 요약 출력).

개발 과정과 설계 근거는 [docs/DEVELOPMENT_NOTES.md](docs/DEVELOPMENT_NOTES.md)에 있습니다.
