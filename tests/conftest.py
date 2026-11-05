import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
sys.path.insert(0, ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def fixture(name: str) -> str:
    return os.path.join(FIXTURES, name)


def name_crops(name: str, refine: bool = True):
    from lumi.capture.screen import ImageScreen

    return ImageScreen(fixture(name)).name_crops(refine=refine)
