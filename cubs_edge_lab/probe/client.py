"""Sequential HTTP access and verifiable raw response storage."""

import hashlib
import json
import threading
import time
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://statsapi.mlb.com/api/v1/"
USER_AGENT = "CubsEdgeLab feasibility research/0.1 (public data probe)"


class ApiError(RuntimeError):
    """A request failed; no measurement is available."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class MalformedResponseError(ApiError):
    """The response cannot safely be interpreted."""


class RequestCeilingError(ApiError):
    """A persistent study request ceiling would be exceeded."""


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
    def __init__(
        self,
        root,
        session=None,
        offline=False,
        request_cap=220,
        ceiling=None,
        allowed_hosts=None,
        manifest_path=None,
        max_ceiling=150,
        cache_manifest_paths=None,
    ):
        self.root = Path(root)
        self.session = session or requests.Session()
        self.offline = offline
        self.limiter = RateLimiter()
        self.lock = threading.Lock()
        self.manifest_path = self.root / (
            manifest_path or "research/raw_manifest.json"
        )
        self.entries = (
            json.loads(self.manifest_path.read_text())
            if self.manifest_path.exists()
            else []
        )
        self.cache_entries = list(self.entries)
        for relative in cache_manifest_paths or []:
            path = self.root / relative
            if path.exists():
                self.cache_entries.extend(json.loads(path.read_text()))
        self.request_cap = request_cap
        self.new_request_count = 0
        if ceiling is not None and ceiling > max_ceiling:
            raise ValueError(f"ceiling cannot exceed {max_ceiling}")
        self.ceiling = ceiling
        self.allowed_hosts = set(allowed_hosts or {"statsapi.mlb.com"})
        self.ledger_path = self.root / "data/sendhold_request_ledger.json"
        if self.ledger_path.exists():
            self.ledger = json.loads(self.ledger_path.read_text())
        else:
            self.ledger = {"count": self._manifest_sendhold_count()}
            if self.ledger["count"]:
                atomic_json(self.ledger_path, self.ledger)

    def _manifest_sendhold_count(self):
        manifests = [self.entries]
        legacy = self.root / "research/raw_manifest.json"
        if legacy != self.manifest_path and legacy.exists():
            manifests.append(json.loads(legacy.read_text()))
        entries = {json.dumps(entry, sort_keys=True) for group in manifests
                   for entry in group}
        return sum(
            1
            for raw_entry in entries
            for entry in [json.loads(raw_entry)]
            if (
                "/game/" in entry["endpoint"]
                and "/playByPlay" in entry["endpoint"]
            )
            or (
                "baseballsavant.mlb.com/leaderboard/"
                in entry["endpoint"]
            )
            or (
                entry.get("params", {}).get("gameType") == "R"
                and entry.get("params", {}).get("season") in {2025, 2026}
            )
        )

    def get_url(self, url, text=False, **params):
        with self.lock:
            parsed = urlparse(url)
            if (
                parsed.scheme != "https"
                or parsed.hostname not in self.allowed_hosts
            ):
                raise ApiError("Disallowed request host or scheme")
            return self._request(url, params, text)

    def get(self, endpoint, **params):
        with self.lock:
            return self._get(endpoint, params)

    def _get(self, endpoint, params):
        url = BASE + endpoint
        return self._request(url, params, False)

    def _request(self, url, params, text):
        endpoint = url
        path = self._cache_path(url, params)
        key = hashlib.sha256(
            json.dumps([url, params], sort_keys=True).encode()
        ).hexdigest()
        if not path.exists():
            path = self.root / "data/raw" / (key + ".json")
        if path.exists():
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if not any(
                e["sha256"] == digest
                and e["endpoint"] == url
                and e["params"] == params
                for e in self.cache_entries
            ):
                raise ApiError("Cache has no matching manifest: " + endpoint)
        else:
            return self._request_new(url, params, text, endpoint, path)
        return self._read_response(url, params, text, endpoint, raw, digest)

    def _cache_path(self, url, params):
        if not url.startswith("https://"):
            url = BASE + url
        key = hashlib.sha256(
            json.dumps([url, params], sort_keys=True).encode()
        ).hexdigest()
        return self.root / "data/raw" / (key + ".json")

    def _request_new(self, url, params, text, endpoint, path):
        if self.offline:
            raise ApiError("Offline cache miss: " + endpoint)
        if self.new_request_count >= self.request_cap:
            raise RequestCeilingError("New request budget exceeded")
        if self.ceiling is not None and self.ledger["count"] >= self.ceiling:
            raise RequestCeilingError("Persistent request ceiling reached")
        self.limiter.wait()
        try:
            response = self.session.get(
                url,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=45,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            self.new_request_count += 1
            self._count_request()
            raise ApiError(f"{endpoint}: {exc}") from exc
        raw = response.content
        self.new_request_count += 1
        self._count_request()
        if 300 <= response.status_code < 400:
            raise ApiError("Redirect refused", status=response.status_code)
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
        self.cache_entries.append(self.entries[-1])
        atomic_json(self.manifest_path, self.entries)
        return self._read_response(url, params, text, endpoint, raw, digest)

    def _read_response(self, url, params, text, endpoint, raw, digest):
        entry = next(
            e
            for e in reversed(self.cache_entries)
            if (
                e["endpoint"] == url
                and e["params"] == params
                and e["sha256"] == digest
            )
        )
        if entry["http_status"] != 200:
            raise ApiError(f"{endpoint}: HTTP {entry['http_status']}")
        if text:
            return raw.decode("utf-8-sig")
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise MalformedResponseError(endpoint + ": invalid JSON") from exc
        if not isinstance(result, dict):
            raise MalformedResponseError(endpoint + ": expected object")
        if "messageNumber" in result or "error" in result:
            raise ApiError(f"{endpoint}: API error {result}")
        return result

    def _count_request(self):
        if self.ceiling is not None:
            self.ledger["count"] += 1
            atomic_json(self.ledger_path, self.ledger)
