# 테스터용 빌드 (콘솔 창 있음: 창을 닫으면 종료, 오류가 바로 보임).
# 빌드: venv/Scripts/python.exe -m PyInstaller lumi.spec --noconfirm  ->  dist/lumi/lumi.exe
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# rapidocr/models의 실험용 모델은 빼고, lumi/ocr/paddle.py가 쓰는 두 개만 넣음
MODELS = ["korean_PP-OCRv5_rec_mobile.onnx", "ch_PP-OCRv5_rec_mobile.onnx"]
rapidocr_data = [
    (src, dest)
    for src, dest in collect_data_files("rapidocr")
    if not src.endswith(".onnx") or os.path.basename(src) in MODELS
]

a = Analysis(
    ["lumi/__main__.py"],
    pathex=["."],
    datas=rapidocr_data + [("lumi/assets/characters", "lumi/assets/characters")],
    hiddenimports=collect_submodules("rapidocr") + ["lumi.app"],
    excludes=["tkinter", "pytest", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtNetwork", "PySide6.QtPdf"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lumi", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="lumi")
