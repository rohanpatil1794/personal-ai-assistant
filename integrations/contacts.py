"""Contact book backed by contacts.json. Supports fuzzy name lookup."""
import json
import threading
from pathlib import Path
from utils.logger import get_logger

log = get_logger(__name__)

DEFAULT_PATH = Path("contacts.json")


class ContactBook:
    def __init__(self, path: str | Path = DEFAULT_PATH) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("contacts: could not load file", path=str(self._path), error=str(e))
            self._data = {}

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def lookup(self, name: str) -> str | None:
        """Fuzzy case-insensitive search. Returns phone number or None."""
        with self._lock:
            key = name.strip().lower()
            # Exact match first
            if key in self._data:
                return self._data[key]
            # Substring match
            for stored_name, number in self._data.items():
                if key in stored_name or stored_name in key:
                    return number
            return None

    def add(self, name: str, phone_number: str) -> None:
        with self._lock:
            self._data[name.strip().lower()] = phone_number.strip()
            self._save()
        log.info("contacts: added", name=name, number=phone_number)

    def remove(self, name: str) -> bool:
        with self._lock:
            key = name.strip().lower()
            if key in self._data:
                del self._data[key]
                self._save()
                return True
            return False

    def list_all(self) -> dict[str, str]:
        with self._lock:
            return dict(self._data)
