"""Loads and saves the user profile (name, about) from profile.json."""
import json
from pathlib import Path
from utils.logger import get_logger

log = get_logger(__name__)

PROFILE_PATH = Path("profile.json")
_DEFAULT: dict = {"name": "", "about": ""}


def load() -> dict:
    try:
        if PROFILE_PATH.exists():
            return {**_DEFAULT, **json.loads(PROFILE_PATH.read_text(encoding="utf-8"))}
    except Exception as e:
        log.warning("profile: could not load", error=str(e))
    return dict(_DEFAULT)


def save(data: dict) -> None:
    PROFILE_PATH.write_text(
        json.dumps({"name": data.get("name", ""), "about": data.get("about", "")},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("profile: saved", name=data.get("name"))
