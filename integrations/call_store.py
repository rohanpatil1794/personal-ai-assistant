"""Thread-safe in-memory store for call records.

Results are posted back here by calling_agent.py via the
/api/internal/call-result FastAPI endpoint.
"""
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class CallRecord:
    call_id: str
    phone_number: str
    contact_name: str | None
    mission: str                   # message to deliver + what to extract
    status: str                    # dialing | connected | completed | failed | no-answer | voicemail
    response: str | None = None    # verbatim response from the other party
    summary: str | None = None     # agent's one-sentence summary
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None


class CallStore:
    def __init__(self) -> None:
        self._records: dict[str, CallRecord] = {}
        self._lock = threading.Lock()

    def create(
        self,
        phone_number: str,
        mission: str,
        contact_name: str | None = None,
    ) -> CallRecord:
        call_id = f"call_{uuid.uuid4().hex[:8]}"
        record = CallRecord(
            call_id=call_id,
            phone_number=phone_number,
            contact_name=contact_name,
            mission=mission,
            status="dialing",
        )
        with self._lock:
            self._records[call_id] = record
        log.info("call_store: created", call_id=call_id, number=phone_number)
        return record

    def update(self, call_id: str, **fields) -> None:
        with self._lock:
            record = self._records.get(call_id)
            if record is None:
                log.warning("call_store: update on unknown call_id", call_id=call_id)
                return
            for k, v in fields.items():
                if hasattr(record, k):
                    setattr(record, k, v)
            if fields.get("status") in ("completed", "failed", "no-answer", "voicemail"):
                record.completed_at = datetime.now()
        log.info("call_store: updated", call_id=call_id, fields=list(fields.keys()))

    def get(self, call_id: str) -> CallRecord | None:
        with self._lock:
            return self._records.get(call_id)

    def list_recent(self, n: int = 10) -> list[CallRecord]:
        with self._lock:
            records = sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)
            return records[:n]
