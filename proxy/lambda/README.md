# lumi API 프록시 (AWS Lambda, 서울 리전)

Cloudflare Worker(`proxy/worker.js`)와 같은 일을 합니다. 한국에서 Cloudflare 미국 서버로 연결돼 느려서
한국 리전으로 옮기는 중입니다 (`docs/DEVELOPMENT_NOTES.md`의 'API 프록시').

- 코드는 `index.mjs` 파일 하나이고, 설치할 패키지가 없습니다.
- 테스트: `node --test proxy/lambda/index.test.mjs`

## 처음 배포 (AWS 콘솔)

1. [AWS 계정](https://aws.amazon.com/)을 만듭니다 (결제 카드 필요). 콘솔 오른쪽 위 리전을 **아시아 태평양(서울) `ap-northeast-2`** 로 바꿉니다.
2. **요금 알림을 먼저 설정합니다.** Function URL은 인터넷에 공개되므로, 누가 마구 호출하면 요금이 나올 수 있습니다.
   Billing and Cost Management → Budgets → 템플릿 'Zero spend budget' 또는 월 1달러 예산을 만들고 이메일을 등록합니다.
3. Lambda → 함수 생성
   - 새로 작성, 함수 이름 `lumi-proxy`
   - 런타임: 목록에서 가장 최신 Node.js, 아키텍처 `arm64`
4. 코드: 코드 탭에서 기본 `index.mjs` 내용을 지우고 이 폴더의 `index.mjs` 내용을 붙여넣은 뒤 **Deploy**를 누릅니다.
5. 구성 탭
   - 환경 변수: 키 `ER_API_KEY`, 값은 Open API 키
   - 일반 구성: 메모리 128 MB, 제한 시간 15초
   - 함수 URL: 생성 → 인증 유형 `NONE` (앱이 인증 없이 부릅니다. 허용 경로와 요청 제한으로 막습니다)
6. 표시되는 `https://....lambda-url.ap-northeast-2.on.aws/` 주소 뒤에 `v2/data/Season`을 붙여 브라우저로 열어 시즌 JSON이 나오면 됩니다.
7. 앱에 주소 넣기: `lumi/config.py`의 `DEFAULT_API_URL`

## 코드 수정 후

콘솔 코드 탭에 `index.mjs`를 다시 붙여넣고 **Deploy**.

## 알아둘 점

- 캐시와 요청 제한은 Lambda 인스턴스 메모리에 있습니다. 인스턴스가 여러 개 뜨면 각각 따로 세고, 잠시 안 쓰면 비워집니다. 요청 제한은 남용을 줄이는 정도이고 요금을 막아 주지는 않으므로 2번의 알림이 필요합니다.
- 한동안 호출이 없으면 첫 요청은 인스턴스를 띄우느라 더 걸립니다 (콜드 스타트).
- 요금과 무료 사용량은 [Lambda 요금 페이지](https://aws.amazon.com/lambda/pricing/)에서 확인하세요.
