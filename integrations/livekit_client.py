"""LiveKit server-side REST client for SIP/PSTN call management.

Uses the livekit-api SDK for token generation and room/SIP APIs.
"""
import json
from utils.logger import get_logger

log = get_logger(__name__)


class LiveKitError(Exception):
    pass


class LiveKitClient:
    def __init__(
        self,
        url: str,
        api_key: str,
        api_secret: str,
        sip_trunk_id: str = "",
    ) -> None:
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._api_secret = api_secret
        self._sip_trunk_id = sip_trunk_id
        self._room_client = None
        self._sip_client = None
        self._agent_dispatch_client = None
        self._init_clients()

    def _init_clients(self) -> None:
        try:
            from livekit import api as lkapi
            self._room_client = lkapi.RoomServiceClient(self._url, self._api_key, self._api_secret)
            self._sip_client = lkapi.SipServiceClient(self._url, self._api_key, self._api_secret)
            self._agent_dispatch_client = lkapi.AgentDispatchClient(self._url, self._api_key, self._api_secret)
            log.info("livekit_client: initialised", url=self._url)
        except Exception as e:
            log.error("livekit_client: failed to initialise SDK clients", error=str(e))
            raise LiveKitError(f"LiveKit SDK init failed: {e}") from e

    def create_room(self, room_name: str, empty_timeout: int = 300) -> None:
        """Create a LiveKit room for the call (no-op if it already exists)."""
        from livekit.api import CreateRoomRequest
        try:
            self._room_client.create_room(CreateRoomRequest(
                name=room_name,
                empty_timeout=empty_timeout,
            ))
            log.info("livekit_client: room created", room=room_name)
        except Exception as e:
            raise LiveKitError(f"create_room failed: {e}") from e

    def dispatch_agent(self, room_name: str, metadata: dict) -> str:
        """Dispatch a calling agent job to the given room."""
        from livekit.api import CreateAgentDispatchRequest
        try:
            resp = self._agent_dispatch_client.create_dispatch(CreateAgentDispatchRequest(
                agent_name="calling-agent",
                room=room_name,
                metadata=json.dumps(metadata),
            ))
            log.info("livekit_client: agent dispatched", room=room_name, dispatch_id=resp.dispatch_id)
            return resp.dispatch_id
        except Exception as e:
            raise LiveKitError(f"dispatch_agent failed: {e}") from e

    def create_sip_participant(
        self,
        room_name: str,
        phone_number: str,
        display_name: str = "Ronny",
        participant_identity: str | None = None,
    ) -> str:
        """Place an outbound SIP/PSTN call into the given room. Returns participant identity."""
        from livekit.api import CreateSipParticipantRequest
        identity = participant_identity or f"sip_{phone_number.replace('+', '')}"
        try:
            resp = self._sip_client.create_sip_participant(CreateSipParticipantRequest(
                room_name=room_name,
                sip_call_to=phone_number,
                trunk_id=self._sip_trunk_id,
                participant_identity=identity,
                participant_name=display_name,
                play_dialtone=True,
                krisp_enabled=True,
                wait_until_answered=False,
            ))
            log.info("livekit_client: sip participant created", room=room_name, number=phone_number)
            return resp.participant_identity
        except Exception as e:
            raise LiveKitError(f"create_sip_participant failed: {e}") from e

    def hangup(self, room_name: str, participant_identity: str) -> None:
        """Remove a participant from the room (hangs up the call)."""
        from livekit.api import RemoveParticipantRequest
        try:
            self._room_client.remove_participant(RemoveParticipantRequest(
                room=room_name,
                identity=participant_identity,
            ))
            log.info("livekit_client: participant removed", room=room_name, identity=participant_identity)
        except Exception as e:
            log.warning("livekit_client: hangup failed (call may have already ended)", error=str(e))
