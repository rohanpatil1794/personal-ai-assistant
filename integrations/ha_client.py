import httpx
from utils.exceptions import HAClientError
from utils.logger import get_logger

log = get_logger(__name__)


class HAClient:
    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self._base}/api{path}"

    def _get(self, path: str) -> dict | list:
        try:
            resp = httpx.get(self._url(path), headers=self._headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise HAClientError(f"HA GET {path} failed ({e.response.status_code}): {e.response.text}") from e
        except Exception as e:
            raise HAClientError(f"HA GET {path} error: {e}") from e

    def _post(self, path: str, payload: dict) -> dict:
        try:
            resp = httpx.post(self._url(path), headers=self._headers, json=payload, timeout=10)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except httpx.HTTPStatusError as e:
            raise HAClientError(f"HA POST {path} failed ({e.response.status_code}): {e.response.text}") from e
        except Exception as e:
            raise HAClientError(f"HA POST {path} error: {e}") from e

    def get_states(self, domain: str | None = None) -> list[dict]:
        states: list[dict] = self._get("/states")
        if domain:
            states = [s for s in states if s["entity_id"].startswith(f"{domain}.")]
        return [
            {
                "entity_id": s["entity_id"],
                "name": s["attributes"].get("friendly_name", s["entity_id"]),
                "state": s["state"],
            }
            for s in states
        ]

    def call_service(self, domain: str, service: str, service_data: dict) -> dict:
        log.info("ha_client: calling service", domain=domain, service=service, data=service_data)
        return self._post(f"/services/{domain}/{service}", service_data)

    def turn_on(self, entity_id: str, **kwargs) -> dict:
        data = {"entity_id": entity_id, **kwargs}
        domain = entity_id.split(".")[0]
        return self.call_service(domain, "turn_on", data)

    def turn_off(self, entity_id: str) -> dict:
        domain = entity_id.split(".")[0]
        return self.call_service(domain, "turn_off", {"entity_id": entity_id})

    def toggle(self, entity_id: str) -> dict:
        domain = entity_id.split(".")[0]
        return self.call_service(domain, "toggle", {"entity_id": entity_id})

    def activate_scene(self, scene_entity_id: str) -> dict:
        return self.call_service("scene", "turn_on", {"entity_id": scene_entity_id})
