"""Calling integration — places and tracks PSTN calls via LiveKit SIP."""
from integrations.base import Integration
from integrations.calling_tools import CALLING_TOOLS
from integrations.call_store import CallStore
from integrations.contacts import ContactBook
from integrations.livekit_client import LiveKitClient, LiveKitError
from utils.logger import get_logger

log = get_logger(__name__)


class CallingIntegration(Integration):
    name = "calling"

    def __init__(
        self,
        livekit: LiveKitClient | None,
        contacts: ContactBook,
        store: CallStore,
        callback_base_url: str = "http://localhost:8000",
    ) -> None:
        self._livekit = livekit
        self._contacts = contacts
        self._store = store
        self._callback_base_url = callback_base_url.rstrip("/")

    def is_available(self) -> bool:
        return self._livekit is not None

    @classmethod
    def get_tools(cls) -> list[dict]:
        return CALLING_TOOLS

    def dispatch(self, tool_name: str, args: dict) -> dict:
        try:
            if tool_name == "call_place":
                return self._place_call(args)
            elif tool_name == "call_get_result":
                return self._get_result(args)
            elif tool_name == "call_list_contacts":
                return {"contacts": self._contacts.list_all()}
            elif tool_name == "call_add_contact":
                self._contacts.add(args["name"], args["phone_number"])
                return {"success": True, "message": f"Saved {args['name']} as {args['phone_number']}."}
            else:
                return {"error": f"Unknown calling tool: {tool_name}"}
        except LiveKitError as e:
            log.error("calling_integration: livekit error", tool=tool_name, error=str(e))
            return {"error": f"Call setup failed: {e}"}
        except Exception as e:
            log.error("calling_integration: dispatch error", tool=tool_name, error=str(e))
            return {"error": str(e)}

    def _place_call(self, args: dict) -> dict:
        contact_name = args.get("contact_name")
        phone_number = args.get("phone_number")
        message = args["message"]
        extract_intent = args["extract_intent"]

        # Resolve phone number
        resolved_name = contact_name
        if contact_name and not phone_number:
            phone_number = self._contacts.lookup(contact_name)
            if not phone_number:
                return {"error": f"No contact named '{contact_name}' found. Ask the user for their phone number."}

        if not phone_number:
            return {"error": "Either contact_name or phone_number must be provided."}

        # Create call record
        record = self._store.create(
            phone_number=phone_number,
            mission=f"Message: {message} | Extract: {extract_intent}",
            contact_name=resolved_name,
        )
        call_id = record.call_id
        room_name = call_id

        # Set up LiveKit room + dispatch agent + initiate call
        self._livekit.create_room(room_name)

        metadata = {
            "call_id": call_id,
            "phone_number": phone_number,
            "contact_name": resolved_name or phone_number,
            "message": message,
            "extract_intent": extract_intent,
            "callback_url": f"{self._callback_base_url}/api/internal/call-result",
        }
        self._livekit.dispatch_agent(room_name, metadata)
        self._livekit.create_sip_participant(room_name, phone_number)

        log.info("calling_integration: call initiated", call_id=call_id, number=phone_number)
        return {
            "call_id": call_id,
            "status": "dialing",
            "phone_number": phone_number,
            "contact": resolved_name or phone_number,
            "message": "Call is being placed. Use call_get_result with this call_id to check the outcome.",
        }

    def _get_result(self, args: dict) -> dict:
        call_id = args["call_id"]
        record = self._store.get(call_id)
        if record is None:
            return {"error": f"No call found with id '{call_id}'."}
        result = {
            "call_id": call_id,
            "contact": record.contact_name or record.phone_number,
            "status": record.status,
            "response": record.response,
            "summary": record.summary,
        }
        if record.completed_at:
            result["completed_at"] = record.completed_at.isoformat()
        return result
