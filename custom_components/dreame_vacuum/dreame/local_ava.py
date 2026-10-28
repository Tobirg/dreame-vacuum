"""Local HTTP transport for a Dreame on-device AVA agent (no Dreame cloud)."""

from __future__ import annotations

import logging
from threading import Thread
from urllib.parse import urlencode, urlsplit

import requests

_LOGGER = logging.getLogger(__name__)


class DreameVacuumLocalAvaProtocol:
    """Present an agent as a cloud-shaped, but strictly LAN-only, transport."""

    # True selects the modern Dreame MIoT wire format and enables map handling;
    # it does NOT imply using an external service.
    dreame_cloud = True

    def __init__(self, host: str, token: str | None = None, device_id: str | None = None):
        if not host:
            raise ValueError("Local AVA agent host is required")
        target = host if "://" in host else "http://" + host
        parts = urlsplit(target)
        if (
            parts.scheme not in ("http", "https") or not parts.hostname
            or parts.username or parts.password
            or parts.path not in ("", "/") or parts.query or parts.fragment
        ):
            raise ValueError("Expected an HTTP(S) agent origin")
        self._base_url = f"{parts.scheme}://{parts.netloc}"
        self._origin = parts
        self._token = token or ""
        self._did = str(device_id) if device_id else None
        self._info = None
        self._session = requests.Session()
        self._logged_in = False
        self._connected = False
        self._auth_failed = False

    @property
    def logged_in(self):
        return self._logged_in

    @property
    def connected(self):
        return self._connected

    @property
    def auth_failed(self):
        return self._auth_failed

    @property
    def auth_key(self):
        return None

    @property
    def device_id(self):
        return self._did

    @property
    def object_name(self):
        return ""

    def _request(self, method, path, *, params=None, body=None, raw=False, timeout=10):
        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            response = self._session.request(
                method, self._base_url + path, params=params, json=body,
                headers=headers, timeout=(3, timeout), allow_redirects=False
            )
            if response.status_code in (401, 403):
                self._auth_failed = True
                self._logged_in = False
                self._connected = False
            if not 200 <= response.status_code < 300:
                _LOGGER.warning("Local AVA %s: HTTP %s", path, response.status_code)
                return None
            return response.content if raw else response.json()
        except (requests.RequestException, ValueError) as exc:
            _LOGGER.warning("Local AVA %s unavailable: %s", path, exc)
            self._connected = False
            return None

    def login(self):
        data = self._request("GET", "/api/info")
        if not isinstance(data, dict):
            self._logged_in = False
            return False
        if isinstance(data.get("data"), dict):
            data = data["data"]
        if isinstance(data.get("device"), dict):
            data = data["device"]
        if not data.get("model") or not data.get("mac"):
            _LOGGER.warning("Local AVA info missing model or MAC")
            self._logged_in = False
            return False
        self._info = dict(data)
        self._info.setdefault("fw_ver", self._info.get("firmware", "0_0"))
        self._info.setdefault("netif", {"localIp": self._origin.hostname})
        if self._info.get("did"):
            self._did = str(self._info["did"])
        self._logged_in = True
        self._connected = True
        self._auth_failed = False
        return True

    def connect(self, message_callback=None, connected_callback=None):
        # No MQTT: Home Assistant retains its normal property polling.
        if not self.login():
            return None
        if connected_callback:
            connected_callback()
        return dict(self._info)

    def get_info(self, mac=None):
        if not self._logged_in and not self.login():
            return None, None
        return self._token, self._base_url

    def send(self, method, parameters=None, retry_count=2, timeout=None):
        if not self._logged_in and not self.login():
            return None
        request = {
            "method": method,
            "params": parameters if parameters is not None else [],
        }
        if self._did:
            request["did"] = self._did
        payload = self._request(
            "POST", "/api/rpc", body=request, timeout=timeout or 15
        )
        if not isinstance(payload, dict):
            return None
        result = payload.get("result")
        if result is None and isinstance(payload.get("data"), dict):
            result = payload["data"].get("result")
        if method == "get_properties" and isinstance(result, list):
            normalized = []
            requested = parameters if isinstance(parameters, list) else []
            for index, item in enumerate(result):
                if not isinstance(item, dict):
                    continue
                prop = dict(item)
                if index < len(requested) and isinstance(requested[index], dict):
                    prop.setdefault("did", requested[index].get("did", "0"))
                normalized.append(prop)
            return normalized
        return result

    def send_async(self, callback, method, parameters=None, retry_count=2):
        def run():
            result = self.send(method, parameters, retry_count)
            if callback:
                callback(result)
        Thread(target=run, name="dreame-ava-rpc", daemon=True).start()

    def get_properties(self, keys):
        if isinstance(keys, str):
            try:
                siid, piid = (int(value) for value in keys.split(".", 1))
            except (ValueError, TypeError):
                return None
            keys = [{"siid": siid, "piid": piid}]
        return self.send("get_properties", keys)

    def get_device_event(self, *args, **kwargs):
        return []  # No local history API yet.

    def get_device_property(self, *args, **kwargs):
        return []

    def get_batch_device_datas(self, *args, **kwargs):
        return {}

    def set_batch_device_datas(self, *args, **kwargs):
        return None

    def _map_url(self, object_name):
        return self._base_url + "/api/maps?" + urlencode({"name": object_name or ""})

    def get_interim_file_url(self, object_name=""):
        return self._map_url(object_name)

    def get_file_url(self, object_name=""):
        return self._map_url(object_name)

    def get_file(self, url, retry_count=1):
        parsed = urlsplit(url)
        if (
            (parsed.scheme, parsed.netloc) != (self._origin.scheme, self._origin.netloc)
            or parsed.path != "/api/maps" or parsed.fragment
        ):
            _LOGGER.warning("Rejected map URL outside local AVA agent")
            return None
        return self._request(
            "GET", parsed.path, params=parsed.query, raw=True, timeout=20
        )

    def get_device_file(self, file_name, file_type, retried=False):
        return self._request(
            "GET", "/api/maps/device-file",
            params={"filename": file_name, "type": file_type},
            raw=True, timeout=20
        )

    def disconnect(self):
        self._connected = False
        self._logged_in = False
        self._session.close()
