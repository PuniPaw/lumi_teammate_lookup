// 실행: node --test proxy/lambda/index.test.mjs  (Open API 없이 가짜 fetch로)
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import { handler } from "./index.mjs";

const SEASON_OK = JSON.stringify({ code: 200, data: [] });
let calls;
let nextResponse;

function event(path, { method = "GET", query = "", ip = "1.1.1.1" } = {}) {
  return { rawPath: path, rawQueryString: query, requestContext: { http: { method, sourceIp: ip } } };
}

// 캐시와 요청 제한이 모듈에 남으므로 테스트마다 다른 경로/닉네임/IP를 씀
beforeEach(() => {
  calls = [];
  nextResponse = { status: 200, body: SEASON_OK };
  process.env.ER_API_KEY = "secret-key";
  globalThis.fetch = async (url, init) => {
    calls.push({ url, key: init.headers["x-api-key"] });
    if (nextResponse.throws) throw nextResponse.throws;
    return { status: nextResponse.status, text: async () => nextResponse.body };
  };
});

test("허용하지 않은 경로와 메서드는 Open API를 부르지 않음", async () => {
  assert.equal((await handler(event("/v1/games/1"))).statusCode, 403);
  assert.equal((await handler(event("/v2/data/Hash"))).statusCode, 403);
  assert.equal((await handler(event("/v2/data/Season", { method: "POST" }))).statusCode, 405);
  assert.equal(calls.length, 0);
});

test("키를 붙여 전달하고 응답에는 키가 없음", async () => {
  const res = await handler(event("/v1/rank/uid/abc/41/3"));
  assert.equal(res.statusCode, 200);
  assert.deepEqual(calls, [{ url: "https://open-api.bser.io/v1/rank/uid/abc/41/3", key: "secret-key" }]);
  assert.ok(!JSON.stringify(res).includes("secret-key"));
});

test("두 번째 요청은 캐시에서, 쿼리 순서가 달라도 같은 캐시", async () => {
  const first = await handler(event("/v1/user/games/uid/u1", { query: "a=1&next=2" }));
  const second = await handler(event("/v1/user/games/uid/u1", { query: "next=2&a=1" }));
  assert.equal(first.headers["x-lumi-cache"], "miss");
  assert.equal(second.headers["x-lumi-cache"], "memory");
  assert.equal(calls.length, 1);
});

test("닉네임이 쿼리에 그대로 전달됨 (한글 포함)", async () => {
  await handler(event("/v1/user/nickname", { query: `query=${encodeURIComponent("얼음마녀")}` }));
  assert.equal(new URL(calls[0].url).searchParams.get("query"), "얼음마녀");
});

test("요청 초과는 캐시하지 않고 상태 코드를 그대로 전달", async () => {
  nextResponse = { status: 429, body: JSON.stringify({ code: 429 }) };
  assert.equal((await handler(event("/v1/rank/uid/limited/41/3"))).statusCode, 429);
  nextResponse = { status: 200, body: SEASON_OK };
  assert.equal((await handler(event("/v1/rank/uid/limited/41/3"))).statusCode, 200);
  assert.equal(calls.length, 2);
});

test("없는 닉네임(HTTP 200, code 404)은 짧게 캐시", async () => {
  nextResponse = { status: 200, body: JSON.stringify({ code: 404 }) };
  await handler(event("/v1/user/nickname", { query: "query=nobody" }));
  const again = await handler(event("/v1/user/nickname", { query: "query=nobody" }));
  assert.equal(again.headers["x-lumi-cache"], "memory");
});

test("Open API 연결 실패는 502, 오류 내용을 돌려주지 않음", async () => {
  nextResponse = { throws: new Error("connect failed secret-key") };
  const res = await handler(event("/v1/rank/uid/down/41/3"));
  assert.equal(res.statusCode, 502);
  assert.ok(!res.body.includes("secret-key"));
});

test("키가 설정되지 않으면 500", async () => {
  delete process.env.ER_API_KEY;
  assert.equal((await handler(event("/v1/rank/uid/nokey/41/3"))).statusCode, 500);
  assert.equal(calls.length, 0);
});

test("IP별 요청 제한은 그 IP만 막음", async () => {
  const ip = "9.9.9.9";
  for (let i = 0; i < 120; i++) {
    assert.equal((await handler(event("/v2/data/Character", { ip }))).statusCode, 200);
  }
  assert.equal((await handler(event("/v2/data/Character", { ip }))).statusCode, 429);
  assert.equal((await handler(event("/v2/data/Character", { ip: "8.8.8.8" }))).statusCode, 200);
});
