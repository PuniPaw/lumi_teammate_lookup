"""exe 로그 파일: 출력이 파일에 남고, 이전 실행 기록을 하나 보관."""

import sys

from lumi.logfile import setup_log


def test_output_goes_to_file_and_previous_log_is_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)  # 콘솔 없는 경우도 앱이 죽지 않아야 함
    monkeypatch.setattr(sys, "stderr", None)
    (tmp_path / "app.log").write_text("이전 실행", encoding="utf-8")

    path = setup_log(str(tmp_path), "app")
    print("✅ 닉네임")
    sys.stderr.write("오류\n")
    sys.stdout._log.close()

    assert open(path, encoding="utf-8").read() == "✅ 닉네임\n오류\n"
    assert (tmp_path / "app.old.log").read_text(encoding="utf-8") == "이전 실행"
