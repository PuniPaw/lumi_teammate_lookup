"""닉네임 OCR. 엔진은 설정(Settings.ocr_engine)으로 고릅니다."""

from lumi.config import Settings
from lumi.ports import NicknameReader


def make_reader(settings: Settings) -> NicknameReader:
    """설정한 OCR 엔진의 NicknameReader. paddle인데 rapidocr가 없으면 Tesseract로."""
    if settings.ocr_engine != "tesseract":
        try:
            from lumi.ocr.paddle import PaddleReader

            return PaddleReader()
        except ImportError as e:
            print(f"⚠️ PP-OCR을 쓸 수 없어 Tesseract로 읽습니다 ({e}). pip install rapidocr onnxruntime")
    from lumi.ocr.reader import TesseractReader

    return TesseractReader(settings.tesseract_cmd)
