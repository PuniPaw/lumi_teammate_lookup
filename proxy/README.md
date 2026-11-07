# lumi API 프록시

배포판 앱은 API 키 없이 이 프록시를 부르고, 프록시가 키를 붙여 이터널 리턴 Open API로 전달합니다.
키를 exe에 넣으면 누구나 꺼내 쓸 수 있어서 키는 여기(Cloudflare secret)에만 둡니다.

```
lumi 앱 ──(키 없음)──> lumi-proxy (Cloudflare Worker) ──(x-api-key)──> open-api.bser.io
```

- 앱이 쓰는 GET 경로만 허용합니다 (`worker.js`의 `ROUTES`). 다른 경로는 403.
- 응답을 캐시합니다 (닉네임→uid 5분, 랭크/통계 5분, 최근 게임 2분, 메타 데이터 1일, 없는 닉네임 5분). uid는 조회할 때마다 값이 달라지고 유효 기간을 알 수 없어 길게 캐시하지 않습니다.
  같은 팀원을 여러 사용자가 조회하는 일이 많아 Open API 호출이 줄어듭니다.
  - 메모리 캐시와 Cloudflare Cache API를 같이 씁니다. 문서에는 Cache API가 `workers.dev`에서 동작하지 않는다고 나오지만 실측에서는 캐시 응답이 나왔습니다.
- IP별 요청 제한: 60초에 120회 (`wrangler.toml`). 정확한 제한은 아니고 남용을 막는 정도입니다.
- 응답 헤더 `x-lumi-cache`: `miss`(Open API 호출), `memory`, `edge`(캐시).

## 처음 배포

Node.js가 필요합니다. 이 폴더(`proxy/`)에서:

1. Cloudflare 로그인 (브라우저가 열림, 계정이 없으면 가입. 무료 플랜으로 충분)
   ```
   npx wrangler login
   ```
2. API 키 등록 (입력 프롬프트에 키를 붙여넣기. 화면과 파일에 남지 않음)
   ```
   npx wrangler secret put ER_API_KEY
   ```
3. 배포
   ```
   npx wrangler deploy
   ```
   끝나면 `https://lumi-proxy.<계정 이름>.workers.dev` 주소가 나옵니다.
4. 앱에 주소 넣기: `lumi/config.py`의 `DEFAULT_API_URL = "https://lumi-proxy.<계정 이름>.workers.dev"`

확인: 브라우저로 `https://lumi-proxy.<계정 이름>.workers.dev/v2/data/Season`을 열어 시즌 목록 JSON이 나오면 됩니다.

## 코드 수정 후

```
npx wrangler deploy
```

## 로컬에서 시험

1. 이 폴더에 `.dev.vars` 파일 (`.gitignore`에 있음, 커밋하지 마세요)
   ```
   ER_API_KEY=발급받은 키
   ```
2. 실행: `npx wrangler dev` → `http://localhost:8787`
3. 앱을 키 없이 프록시로: 저장소 `.env`에서 `ETERNAL_RETURN_API_KEY`를 빼고 `LUMI_API_URL=http://localhost:8787`

## 비용과 한도

- Workers 무료 플랜: 하루 요청 10만 회. 한 판에 약 19회(팀원 3명, 최근 게임 3페이지씩)라 캐시 없이도 하루 약 5,200판.
- 먼저 걸릴 가능성이 높은 건 Open API 키의 요청 한도입니다. 사용자가 늘면 개발자 포털에서 한도 상향을 신청하세요.
- 사용량은 Cloudflare 대시보드 → Workers & Pages → lumi-proxy에서 볼 수 있습니다.
