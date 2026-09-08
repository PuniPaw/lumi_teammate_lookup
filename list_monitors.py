"""연결된 모니터 목록과 각 모니터의 좌표 범위를 출력합니다."""
import mss

with mss.mss() as sct:
    for i, m in enumerate(sct.monitors):
        print(f"[{i}] {m}")