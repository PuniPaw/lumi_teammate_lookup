/**
 * lumi API 프록시 (Cloudflare Worker).
 *
 * 앱(lumi/api/client.py)은 키 없이 이 Worker를 Open API와 같은 경로로 부르고,
 * Worker가 x-api-key를 붙여 open-api.bser.io로 전달합니다. 키는 Worker의 secret(ER_API_KEY)에만 있음.
 *
 * - 앱이 쓰는 GET 경로만 허용 (ROUTES). 나머지는 403
 * - 응답 캐시: 같은 팀원을 여러 사용자가 조회하는 일이 많아 Open API 호출 수가 줄어듦
 *     1) 메모리 (Worker 인스턴스마다, 재시작하면 비워짐)
 *     2) Cache API (Cloudflare 문서에는 workers.dev에서 동작하지 않는다고 나오지만, 실측에서는
 *        x-lumi-cache: edge, age 헤더로 캐시 응답이 나옴. 언제든 안 될 수 있다고 보고 메모리와 같이 씀)
 * - IP별 요청 제한 (RATE_LIMITER 바인딩, wrangler.toml). 정확한 제한은 아니고 남용을 막는 정도
 */

const UPSTREAM = "https://open-api.bser.io";

// [경로 정규식, 캐시 시간(초)]. bserpy가 실제로 부르는 경로 (lumi/api, bserpy/resources)
const ROUTES = [
  // 닉네임 -> uid (?query=닉네임). Open API는 조회할 때마다 다른 uid를 주고 유효 기간을 알 수 없어서
  // 길게 캐시하지 않음 (uid가 만료되면 그 유저는 캐시가 끝날 때까지 조회 실패). 전적 캐시와 같은 시간
  [/^\/v1\/user\/nickname$/, 5 * 60],
  [/^\/v1\/rank\/uid\/[^/]+\/\d+\/\d+$/, 5 * 60], // 랭크/MMR
  [/^\/v2\/user\/stats\/uid\/[^/]+\/\d+\/\d+$/, 5 * 60], // 시즌 통계
  [/^\/v1\/user\/games\/uid\/[^/]+$/, 2 * 60], // 최근 게임 (?next=커서)
  [/^\/v2\/data\/(Character|Season)$/, 24 * 3600], // 캐릭터 이름, 현재 시즌
  [/^\/v1\/l10n\/[A-Za-z]+$/, 24 * 3600], // 번역 파일 주소
];

// 응답 본문 code가 404(없는 닉네임 등)이면 짧게 캐시 (닉네임을 방금 바꾼 유저가 있을 수 있음)
const NOT_FOUND_TTL = 10 * 60;

// 캐시 시간을 줄이면 올려서, 예전 시간으로 저장된 Cache API 항목을 쓰지 않게 함
const CACHE_VERSION = "v2";

const MEMORY_MAX_ENTRIES = 2000;
const memory = new Map(); // url -> { body, status, expires }

function json(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function ttlFor(pathname) {
  for (const [pattern, ttl] of ROUTES) {
    if (pattern.test(pathname)) return ttl;
  }
  return null;
}

/** 캐시해도 되는 응답의 캐시 시간. 오류(요청 초과 등)는 0 */
function cacheTtl(status, body, routeTtl) {
  if (status !== 200) return 0;
  let code;
  try {
    code = JSON.parse(body).code;
  } catch {
    return 0;
  }
  if (code === 200) return routeTtl;
  if (code === 404) return Math.min(routeTtl, NOT_FOUND_TTL);
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

function respond(entry, source) {
  return new Response(entry.body, {
    status: entry.status,
    headers: { "content-type": "application/json; charset=utf-8", "x-lumi-cache": source },
  });
}

export default {
  async fetch(request, env, ctx) {
    if (request.method !== "GET") return json(405, { code: 405, message: "GET only" });

    const url = new URL(request.url);
    const routeTtl = ttlFor(url.pathname);
    if (routeTtl === null) return json(403, { code: 403, message: "path not allowed" });

    if (env.RATE_LIMITER) {
      const ip = request.headers.get("cf-connecting-ip") || "unknown";
      const { success } = await env.RATE_LIMITER.limit({ key: ip });
      // bserpy는 429를 요청 초과로 보고 잠시 뒤 다시 시도함
      if (!success) return json(429, { code: 429, message: "too many requests" });
    }

    // 쿼리 순서가 달라도 같은 캐시를 쓰도록 정렬
    url.searchParams.sort();
    const key = url.pathname + url.search;

    const hit = memoryGet(key);
    if (hit) return respond(hit, "memory");

    const cache = caches.default;
    const cacheKey = new Request(`https://lumi-cache-${CACHE_VERSION}${key}`);
    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    if (!env.ER_API_KEY) return json(500, { code: 500, message: "ER_API_KEY secret is not set" });
    const upstream = await fetch(UPSTREAM + key, { headers: { "x-api-key": env.ER_API_KEY } });
    const body = await upstream.text();
    const entry = { body, status: upstream.status, expires: 0 };

    const ttl = cacheTtl(upstream.status, body, routeTtl);
    if (ttl > 0) {
      entry.expires = Date.now() + ttl * 1000;
      memoryPut(key, entry);
      const toCache = respond(entry, "edge");
      toCache.headers.set("cache-control", `max-age=${ttl}`);
      ctx.waitUntil(cache.put(cacheKey, toCache));
    }
    return respond(entry, "miss");
  },
};
