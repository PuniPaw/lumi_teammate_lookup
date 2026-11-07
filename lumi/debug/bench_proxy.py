"""
배포된 프록시로 팀원 3명 조회를 반복 측정합니다. 앱과 같은 제한(PROXY_TIMEOUT), 동시 조회.

사용법: python -m lumi.debug.bench_proxy [회차 수] [회차 간격(초)]
한 회차 = 캐시 없는 조회 1번 + 바로 이어서 캐시 있는 조회 1번.
캐시(5분)가 끝나야 다음 회차가 캐시 없는 조회가 되므로 간격은 기본 330초입니다.
결과: debug/bench_proxy.jsonl (이어서 추가), 끝나면 요약 출력.
"""

import collections
import json
import os
import statistics
import sys
import threading
import time
from datetime import datetime

import httpx
from bserpy import Client

from lumi.api import player_stats
from lumi.api.client import _PROXY_PLACEHOLDER_KEY, PROXY_TIMEOUT
from lumi.config import load_settings

TEAMS = [
    ("PuniPaw", "sooin", "BlackBrave"),
    ("HYUHAN", "MirNight", "로즈만때리는루크"),
    ("마브하라", "레몬데몬", "얼음마녀"),
]


def _ocr(names) -> list[dict]:
    return [
        {"name": f"teammate_{i}", "best": n, "confidence": 95, "candidates": [n], "candidate_scores": {n: 95}}
        for i, n in enumerate(names)
    ]


def measure(api_url: str, names, label: str) -> dict:
    lock = threading.Lock()
    statuses: collections.Counter = collections.Counter()
    caches: collections.Counter = collections.Counter()

    def on_response(response: httpx.Response) -> None:
        with lock:
            statuses[response.status_code] += 1
            caches[response.headers.get("x-lumi-cache", "none")] += 1

    def make_client() -> Client:
        http = httpx.Client(base_url=api_url, timeout=PROXY_TIMEOUT, event_hooks={"response": [on_response]})
        return Client(api_key=_PROXY_PLACEHOLDER_KEY, http_client=http)

    started = time.monotonic()
    error = None
    team: list[dict] = []
    try:
        team = player_stats.EternalReturnStats(make_client).team_stats(_ocr(names))
    except Exception as e:  # 시즌 조회 실패 등: 회차 전체 실패로 기록
        error = repr(e)
    return {
        "at": datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "seconds": round(time.monotonic() - started, 2),
        "names": list(names),
        "ok": sum(1 for s in team if s["tier"] != player_stats.FAILED_TIER),
        "total": len(names),
        "statuses": {str(k): v for k, v in statuses.items()},
        "caches": dict(caches),
        "error": error,
    }


def summarize(rows: list[dict]) -> None:
    for label in ("miss", "cached"):
        part = [r for r in rows if r["label"] == label]
        if not part:
            continue
        times = sorted(r["seconds"] for r in part)
        full = sum(1 for r in part if r["ok"] == r["total"])
        ok, total = sum(r["ok"] for r in part), sum(r["total"] for r in part)
        limited = sum(r["statuses"].get("429", 0) for r in part)
        p90 = times[min(len(times) - 1, int(len(times) * 0.9))]
        print(
            f"{label:6} {len(part)}회 | 시간 중앙값 {statistics.median(times):.1f}s, 90% {p90:.1f}s, 최대 {times[-1]:.1f}s"
            f" | 회차 성공 {full}/{len(part)}, 팀원 성공 {ok}/{total} | 429 {limited}번"
        )


def main() -> None:
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 330
    settings = load_settings()
    if not settings.api_url:
        print("LUMI_API_URL 또는 DEFAULT_API_URL이 없습니다.")
        return
    player_stats.print = lambda *a, **k: None  # 팀원별 출력 끄기

    os.makedirs(settings.debug_dir, exist_ok=True)
    path = os.path.join(settings.debug_dir, "bench_proxy.jsonl")
    rows = []
    for i in range(cycles):
        names = TEAMS[i % len(TEAMS)]
        for label in ("miss", "cached"):
            row = measure(settings.api_url, names, label)
            rows.append(row)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[{i + 1}/{cycles}] {label} {row['seconds']}s 성공 {row['ok']}/{row['total']} {row['statuses']}", flush=True)
        if i < cycles - 1:
            time.sleep(interval)
    print()
    summarize(rows)


if __name__ == "__main__":
    main()
