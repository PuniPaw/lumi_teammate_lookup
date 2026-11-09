/**
 * lumi API 프록시 (AWS Lambda, 서울 리전, Function URL). 배포 방법: proxy/lambda/README.md
 *
 * 앱(lumi/api/client.py)은 키 없이 이 함수를 Open API와 같은 경로로 부르고,
 * 함수가 x-api-key를 붙여 open-api.bser.io로 전달합니다. 키는 Lambda 환경 변수(ER_API_KEY)에만 있음.
 *
 * Cloudflare Worker(proxy/worker.js)를 옮긴 것. 한국에서 Cloudflare 미국 서버로 연결돼 느렸음
 * (docs/DEVELOPMENT_NOTES.md의 'API 프록시').
 *
 * - 앱이 쓰는 GET 경로만 허용 (ROUTES). 나머지는 403
 * - 응답 캐시: 메모리 (Lambda 인스턴스마다, 인스턴스가 내려가면 비워짐)
 * - IP별 요청 제한: 역시 인스턴스마다 따로 세므로 정확하지 않음. 남용을 막는 정도
 */

const UPSTREAM = "https://open-api.bser.io";
const UPSTREAM_TIMEOUT_MS = 8000; // 앱의 제한(PROXY_TIMEOUT 10초)보다 먼저 끝나도록

// [경로 정규식, 캐시 시간(초)]. bserpy가 실제로 부르는 경로 (lumi/api, bserpy/resources)
const ROUTES = [
  // 닉네임 -> uid (?query=닉네임). Open API는 조회할 때마다 다른 uid를 주고 유효 기간을 알 수 없어서
  // 길게 캐시하지 않음 (uid가 만료되면 그 유저는 캐시가 끝날 때까지 조회 실패). 전적 캐시와 같은 시간
  [/^\/v1\/user\/nickname$/, 5 * 60],
  [/^\/v1\/rank\/uid\/[^/]+\/\d+\/\d+$/, 5 * 60], // 랭크/MMR
  [/^\/v2\/user\/stats\/uid\/[^/]+\/\d+\/\d+$/, 5 * 60], // 시즌 통계
  [/^\/v1\/user\/games\/uid\/[^/]+$/, 2 * 60], // 최근 게임 (?next=커서)
  [/^\/v2\/data\/(Character|CharacterMastery|Season)$/, 24 * 3600], // 캐릭터 이름, 캐릭터별 무기, 현재 시즌
  [/^\/v1\/l10n\/[A-Za-z]+$/, 24 * 3600], // 번역 파일 주소
];

const RATE_LIMIT = 120; // IP당 RATE_WINDOW_MS 안에 허용하는 요청 수
const RATE_WINDOW_MS = 60 * 1000;
const MEMORY_MAX_ENTRIES = 2000;

const memory = new Map(); // key -> { body, status, expires }
const ipWindows = new Map(); // ip -> { start, count }

function response(statusCode, body, cache) {
  const headers = { "content-type": "application/json; charset=utf-8" };
  if (cache) headers["x-lumi-cache"] = cache;
  return { statusCode, headers, body };
}

function error(statusCode, message) {
  return response(statusCode, JSON.stringify({ code: statusCode, message }));
}

function ttlFor(path) {
  for (const [pattern, ttl] of ROUTES) {
    if (pattern.test(path)) return ttl;
  }
  return null;
}

/** 캐시해도 되는 응답의 캐시 시간. 오류(요청 초과 등)는 0. 없는 닉네임(code 404)은 짧게 */
function cacheTtl(status, body, routeTtl) {
  if (status !== 200) return 0;
  let code;
  try {
    code = JSON.parse(body).code;
  } catch {
    return 0;
  }
  if (code === 200) return routeTtl;
  if (code === 404) return Math.min(routeTtl, 5 * 60);
  return 0;
}

function memoryGet(key) {
  const hit = memory.get(key);
  if (!hit) return null;
  if (hit.expires < Date.now()) {
    memory.delete(key);
    return null;
  }
  return hit;
}

function memoryPut(key, entry) {
  if (memory.size >= MEMORY_MAX_ENTRIES) {
    memory.delete(memory.keys().next().value); // 가장 오래 전에 넣은 것
  }
  memory.set(key, entry);
}

function rateLimited(ip) {
  const now = Date.now();
  const current = ipWindows.get(ip);
  if (!current || now - current.start >= RATE_WINDOW_MS) {
    if (ipWindows.size >= MEMORY_MAX_ENTRIES) ipWindows.clear();
    ipWindows.set(ip, { start: now, count: 1 });
    return false;
  }
  current.count += 1;
  return current.count > RATE_LIMIT;
}

export const handler = async (event) => {
  const http = event.requestContext?.http ?? {};
  if (http.method !== "GET") return error(405, "GET only");

  const path = event.rawPath ?? "";
  const routeTtl = ttlFor(path);
  if (routeTtl === null) return error(403, "path not allowed");

  // bserpy는 429를 요청 초과로 보고 잠시 뒤 다시 시도함
  if (rateLimited(http.sourceIp ?? "unknown")) return error(429, "too many requests");

  const query = new URLSearchParams(event.rawQueryString ?? "");
  query.sort(); // 쿼리 순서가 달라도 같은 캐시를 쓰도록
  const search = query.toString();
  const key = search ? `${path}?${search}` : path;

  const hit = memoryGet(key);
  if (hit) return response(hit.status, hit.body, "memory");

  if (!process.env.ER_API_KEY) return error(500, "ER_API_KEY is not set");

  let upstream;
  try {
    upstream = await fetch(UPSTREAM + key, {
      headers: { "x-api-key": process.env.ER_API_KEY },
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch (e) {
    console.error("upstream failed:", e.name); // 키가 로그에 남지 않도록 오류 이름만
    return error(502, "upstream request failed"); // bserpy가 잠시 뒤 다시 시도함
  }

  const body = await upstream.text();
  const ttl = cacheTtl(upstream.status, body, routeTtl);
  if (ttl > 0) memoryPut(key, { body, status: upstream.status, expires: Date.now() + ttl * 1000 });
  return response(upstream.status, body, "miss");
};
