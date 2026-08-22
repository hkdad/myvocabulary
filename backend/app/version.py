from functools import lru_cache
from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"


@lru_cache(maxsize=1)
def get_version() -> str:
    """Return the app release version from the repo-root VERSION file."""
    return _VERSION_FILE.read_text(encoding="utf-8").strip()
