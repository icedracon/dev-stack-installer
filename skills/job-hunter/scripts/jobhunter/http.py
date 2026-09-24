"""Minimal polite HTTP client (stdlib only). Honours HTTPS_PROXY via urllib defaults.

Deliberately does NOT: send cookies, log in, rotate user agents, solve CAPTCHAs or
retry on 401/403. A 403 means "not allowed" and the source is reported as blocked."""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlsplit


class FetchError(Exception):
    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


_last_hit: dict[str, float] = {}
_lock = threading.Lock()


def _throttle(host: str, delay: float) -> None:
    with _lock:
        wait = _last_hit.get(host, 0) + delay - time.monotonic()
        _last_hit[host] = time.monotonic() + max(0.0, wait)
    if wait > 0:
        time.sleep(wait)


class Http:
    def __init__(self, run_cfg: dict | None = None):
        run_cfg = run_cfg or {}
        self.delay = float(run_cfg.get("request_delay_seconds", 1.0))
        self.timeout = float(run_cfg.get("timeout_seconds", 25))
        self.max_bytes = int(float(run_cfg.get("max_response_mb", 25)) * 1024 * 1024)
        self.ua = run_cfg.get("user_agent", "job-hunter/0.1")
        self.requests = 0

    def get_json(self, url: str, params: dict | None = None, retries: int = 2):
        if params:
            url = f"{url}{'&' if '?' in url else '?'}{urlencode(params)}"
        host = urlsplit(url).hostname or ""
        attempt = 0
        while True:
            _throttle(host, self.delay)
            self.requests += 1
            req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read(self.max_bytes + 1)
                    if len(body) > self.max_bytes:
                        raise FetchError(f"response larger than {self.max_bytes} bytes: {url}")
                    return json.loads(body.decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                    retry_after = e.headers.get("Retry-After") if e.headers else None
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** (attempt + 1)
                    time.sleep(min(wait, 60))
                    attempt += 1
                    continue
                raise FetchError(f"HTTP {e.code} ({host}{urlsplit(url).path})", e.code) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                reason = str(getattr(e, "reason", e))
                # A proxy/firewall refusal is a policy answer, not a transient failure: don't retry it.
                blocked = re.search(r"\b(403|407)\b|forbidden|tunnel connection failed", reason, re.I)
                if attempt < retries and not blocked:
                    time.sleep(2 ** (attempt + 1))
                    attempt += 1
                    continue
                kind = "blocked by proxy/firewall" if blocked else "network error"
                raise FetchError(f"{kind} ({host}): {reason[:120]}") from None
            except json.JSONDecodeError:
                raise FetchError(f"non-JSON response from {url}") from None
