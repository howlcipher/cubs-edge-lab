"""Sequential HTTP access and verifiable raw response storage."""

import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://statsapi.mlb.com/api/v1/"
USER_AGENT = "CubsEdgeLab feasibility research/0.1 (public data probe)"


class ApiError(RuntimeError):
    """A request failed; no measurement is available."""


class MalformedResponseError(ApiError):
    """The response cannot safely be interpreted."""


class RateLimiter:
    def __init__(self, clock=time.monotonic, sleep=time.sleep):
        self.clock = clock
        self.sleep = sleep
        self.last = None

    def wait(self):
        if self.last is not None:
            while self.clock() - self.last < 0.5:
                self.sleep(0.5 - (self.clock() - self.last))
        self.last = self.clock()


def atomic_json(path, value, indent=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=indent) + "\n")
    temporary.replace(path)


class Client:
    def __init__(self, root, session=None, offline=False, request_cap=220):
        self.root = Path(root)
        self.session = session or requests.Session()
        self.offline = offline
        self.limiter = RateLimiter()
        self.lock = threading.Lock()
        self.manifest_path = self.root / "research/raw_manifest.json"
        self.entries = (
            json.loads(self.manifest_path.read_text())
            if self.manifest_path.exists()
            else []
        )
        self.request_cap = request_cap
        self.new_request_count = 0

    def get(self, endpoint, **params):
        with self.lock:
            return self._get(endpoint, params)

    def _get(self, endpoint, params):
        url = BASE + endpoint
        key = hashlib.sha256(
            json.dumps([url, params], sort_keys=True).encode()
        ).hexdigest()
        path = self.root / "data/raw" / (key + ".json")
        if path.exists():
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if not any(
                e["sha256"] == digest
                and e["endpoint"] == url
                and e["params"] == params
                for e in self.entries
            ):
                raise ApiError("Cache has no matching manifest: " + endpoint)
        else:
            if self.offline:
                raise ApiError("Offline cache miss: " + endpoint)
            if self.new_request_count >= self.request_cap:
                raise ApiError("New request budget exceeded")
            self.limiter.wait()
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=45,
                )
            except requests.RequestException as exc:
                raise ApiError(f"{endpoint}: {exc}") from exc
            raw = response.content
            self.new_request_count += 1
            digest = hashlib.sha256(raw).hexdigest()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            self.entries.append(
                {
                    "endpoint": url,
                    "params": params,
                    "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                    "sha256": digest,
                    "byte_size": len(raw),
                    "file": str(path.relative_to(self.root)),
                    "http_status": response.status_code,
                }
            )
            atomic_json(self.manifest_path, self.entries)
        entry = next(
            e
            for e in reversed(self.entries)
            if e["endpoint"] == url
            and e["params"] == params
            and e["sha256"] == digest
        )
        if entry["http_status"] != 200:
            raise ApiError(f"{endpoint}: HTTP {entry['http_status']}")
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise MalformedResponseError(endpoint + ": invalid JSON") from exc
        if not isinstance(result, dict):
            raise MalformedResponseError(endpoint + ": expected object")
        if "messageNumber" in result or "error" in result:
            raise ApiError(f"{endpoint}: API error {result}")
        return result
