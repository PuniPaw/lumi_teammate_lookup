import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
sys.path.insert(0, ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ETERNAL_RETURN_API_KEY", "test-key")


def fixture(name: str) -> str:
    return os.path.join(FIXTURES, name)
