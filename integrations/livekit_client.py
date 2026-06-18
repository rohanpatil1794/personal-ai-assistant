"""LiveKit server-side REST client for SIP/PSTN call management.

Uses the livekit-api SDK (v1.x) for token generation and room/SIP APIs.
"""
import asyncio  # used inside thread via concurrent.futures
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
        self._verify()

    def _verify(self) -> None:
        try:
            from livekit.api import LiveKitAPI  # noqa: F401
            log.info("livekit_client: SDK available", url=self._url)
        except ImportError as e:
            raise LiveKitError(f"livekit-api not installed: {e}") from e

    def _make_api(self):
        from livekit.api import LiveKitAPI
        return LiveKitAPI(self._url, self._api_key, self._api_secret)

    def _run(self, coro):
        """Run an async coroutine from any sync context (including AnyIO worker threads)."""
        import concurrent.futures
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=30)
        except Exception as e:
            raise LiveKitError(str(e)) from e

    async def _create_room_async(self, room_name: str, empty_timeout: int) -> None:
        from livekit.api import LiveKitAPI, CreateRoomRequest
        async with LiveKitAPI(self._url, self._api_key, self._api_secret) as lk:
            await lk.room.create_room(CreateRoomRequest(
                name=room_name,
                empty_timeout=empty_timeout,
            ))
        log.info("livekit_client: room created", room=room_name)

    def create_room(self, room_name: str, empty_timeout: int = 300) -> None:
        """Create a LiveKit room for the call (no-op if it already exists)."""
        self._run(self._create_room_async(room_name, empty_timeout))

    async def _dispatch_agent_async(self, room_name: str, metadata: dict) -> str:
        from livekit.api import LiveKitAPI, CreateAgentDispatchRequest
        async with LiveKitAPI(self._url, self._api_key, self._api_secret) as lk:
            resp = await lk.agent_dispatch.create_dispatch(CreateAgentDispatchRequest(
                agent_name="calling-agent",
                room=room_name,
                metadata=json.dumps(metadata),
            ))
        log.info("livekit_client: agent dispatched", room=room_name, dispatch_id=resp.id)
        return resp.id

    def dispatch_agent(self, room_name: str, metadata: dict) -> str:
        """Dispatch a calling agent job to the given room."""
        return self._run(self._dispatch_agent_async(room_name, metadata))

    async def _create_sip_participant_async(
        self,
        room_name: str,
        phone_number: str,
        display_name: str,
        identity: str,
    ) -> str:
        from livekit.api import LiveKitAPI, CreateSIPParticipantRequest as CreateSipParticipantRequest
        async with LiveKitAPI(self._url, self._api_key, self._api_secret) as lk:
            resp = await lk.sip.create_sip_participant(CreateSipParticipantRequest(
                room_name=room_name,
                sip_call_to=phone_number,
                sip_trunk_id=self._sip_trunk_id,
                participant_identity=identity,
                participant_name=display_name,
                play_dialtone=True,
                krisp_enabled=True,
                wait_until_answered=False,
            ))
        log.info("livekit_client: sip participant created", room=room_name, number=phone_number)
        return resp.participant_identity

    def create_sip_participant(
        self,
        room_name: str,
        phone_number: str,
        display_name: str = "Ronny",
        participant_identity: str | None = None,
    ) -> str:
        """Place an outbound SIP/PSTN call into the given room. Returns participant identity."""
        identity = participant_identity or f"sip_{phone_number.replace('+', '')}"
        return self._run(self._create_sip_participant_async(room_name, phone_number, display_name, identity))

    async def _hangup_async(self, room_name: str, participant_identity: str) -> None:
        from livekit.api import LiveKitAPI, RoomParticipantIdentity
        async with LiveKitAPI(self._url, self._api_key, self._api_secret) as lk:
            await lk.room.remove_participant(RoomParticipantIdentity(
                room=room_name,
                identity=participant_identity,
            ))
        log.info("livekit_client: participant removed", room=room_name, identity=participant_identity)

    def hangup(self, room_name: str, participant_identity: str) -> None:
        """Remove a participant from the room (hangs up the call)."""
        try:
            self._run(self._hangup_async(room_name, participant_identity))
        except Exception as e:
            log.warning("livekit_client: hangup failed (call may have already ended)", error=str(e))
