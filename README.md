# lumi-teammate-lookup

이터널 리턴에서 매칭이 잡히면 팀원 닉네임을 화면에서 읽어(OCR) 전적을 모달로 보여주고, 게임이 시작되면 모달을 닫습니다.

모달에 표시되는 정보 (팀원별):
- 현재 시즌 랭크 티어 / MMR
- 모스트 캐릭터, 판수, 평균 순위, 승률(1·2·3위 비율)
- 최근 20게임(일반+랭크) 평균 딜량, 평균 TK

## 준비

1. 패키지 설치
   ```
   pip install -r requirements.txt
   ```
   닉네임 OCR은 PaddleOCR(PP-OCRv5) 인식 모델을 RapidOCR(ONNX)로 돌립니다. 처음 실행할 때 모델 파일 약 30MB를 ModelScope에서 받습니다.
2. 저장소 폴더에 `.env` 파일
   ```
   ETERNAL_RETURN_API_KEY=발급받은 키
   ```

## 실행

```
python -m lumi
```
게임이 켜지면 앱(`lumi.app`)이 자동으로 실행됩니다. 게임 창을 맨 앞에 두세요 (화면을 보이는 그대로 캡처합니다).

## 설정

`.env` 또는 환경 변수로 바꿀 수 있습니다 (`lumi/config.py`).

| 환경 변수 | 설명 | 기본값 |
|---|---|---|
| `ETERNAL_RETURN_API_KEY` | Open API 키 (필수) | |
| `LUMI_DEBUG` | 디버그 출력/이미지 저장 (`1`로 켬) | 꺼짐 |
| `LUMI_GAME_PROCESS` | 게임 프로세스 이름 | `EternalReturn.exe` |
| `LUMI_GAME_WINDOW_TITLE` | 게임 창 제목 (부분 일치) | `Eternal Return` |
| `LUMI_LOG_PATH` | 게임 로그 경로 | `%USERPROFILE%\AppData\LocalLow\NimbleNeuron\Eternal Return\Player.log` |

## 구조

```
lumi/
  __main__.py       python -m lumi: 게임 프로세스 감시 -> 앱 실행
  app.py            매칭 -> OCR -> 전적 조회 -> 모달 흐름, 실제 구현 조립(build)
  config.py         설정 (Settings)
  ports.py          외부 연결 인터페이스 (ScreenSource, NicknameReader, StatsProvider, MatchSignals)
  game/             process.py 게임 감시, log.py 매칭 감지(PlayerLog), match_flow.py 재시도/게임 시작 판단
  capture/          screen.py 닉네임 칸 위치 계산과 캡처 (LiveScreen, ImageScreen)
  ocr/              paddle.py PP-OCR (PaddleReader), image.py 테두리 제거/빈 칸 판별,
                    chars.py 문자 종류, candidates.py 잡음 후보/비슷한 글자
  api/              resolve.py 닉네임 확정, player_stats.py 전적 (EternalReturnStats), recent_stats.py 최근 20게임
  ui/               overlay.py 모달
  debug/            store.py 디버그 이미지, crops.py / check.py 확인 도구
tests/              fixtures/ 실제 게임 화면
docs/               개발 노트
```

`app.py`는 `ports.py`의 인터페이스에만 의존하고, 실제 구현(게임 화면, PP-OCR, Open API, 로그 파일)은 `build()`에서 설정으로 만들어 넘깁니다. 테스트에서는 가짜 구현을 넘깁니다.

## 문제 확인

- 스크린샷으로 OCR + API 확정까지 확인: `python -m lumi.debug.check <스크린샷>` (생략하면 지금 게임 화면)
- 닉네임 칸을 원본 해상도로 잘라 보기: `python -m lumi.debug.crops <스크린샷>`
- 매칭 관련 로그 확인: `python -m lumi.game.log`
- 디버그 이미지 저장: `.env`에 `LUMI_DEBUG=1` → `debug/`에 매 판 닉네임 칸, 실패한 판은 게임 화면 저장 (최근 20판 유지)

## 테스트

```
pip install pytest
python -m pytest tests
```
`tests/fixtures/`의 실제 게임 화면으로 닉네임 인식 정확도를 확인합니다 (요약 출력: `python tests/test_paddle_reader.py`).

개발 과정과 설계 근거는 [docs/DEVELOPMENT_NOTES.md](docs/DEVELOPMENT_NOTES.md)에 있습니다.
