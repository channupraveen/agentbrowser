"""API discovery: watch the site's own JSON calls while the agent browses.

Every XHR/fetch that returns JSON is recorded as an endpoint (method + path
template). Later the agent can call that endpoint directly with the browser's
cookies, skipping the UI entirely, which is usually 10-100x faster than clicking.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from playwright.async_api import Response

SECRET_KEYS = re.compile(r"pass|token|secret|auth|session|cookie|otp|card|cvv|ssn", re.I)
ID_SEGMENT = re.compile(r"^(\d+|[0-9a-f]{8}-[0-9a-f-]{27,}|[0-9a-f]{16,}|[A-Za-z0-9_-]{24,})$")


def path_template(path: str) -> str:
    parts = [("{id}" if ID_SEGMENT.match(p) else p) for p in path.split("/")]
    return "/".join(parts) or "/"


def redact(value):
    if isinstance(value, dict):
        return {k: ("***" if SECRET_KEYS.search(k) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value[:2]]
    if isinstance(value, str) and len(value) > 60:
        return value[:60] + "…"
    return value


def shape(value, depth: int = 0):
    """Describe a JSON value by its structure, so the agent knows what comes back."""
    if depth > 2:
        return type(value).__name__
    if isinstance(value, dict):
        return {k: shape(v, depth + 1) for k, v in list(value.items())[:15]}
    if isinstance(value, list):
        return [shape(value[0], depth + 1)] if value else []
    return type(value).__name__


class ApiCatalog:
    def __init__(self, store: Path):
        self.store = store
        self.store.mkdir(parents=True, exist_ok=True)
        self.endpoints: dict[str, dict] = {}
        for f in self.store.glob("*.json"):
            for ep in json.loads(f.read_text()):
                self.endpoints[ep["key"]] = ep

    async def on_response(self, response: Response) -> None:
        req = response.request
        if req.resource_type not in ("xhr", "fetch"):
            return
        if "json" not in (response.headers.get("content-type") or ""):
            return
        try:
            body = await response.json()
        except Exception:
            return
        u = urlsplit(req.url)
        key = f"{req.method} {u.netloc}{path_template(u.path)}"
        payload = None
        if req.post_data:
            try:
                payload = redact(json.loads(req.post_data))
            except (ValueError, TypeError):
                payload = "(form/body)"
        ep = self.endpoints.get(key, {"key": key, "hits": 0})
        ep.update(
            method=req.method,
            host=u.netloc,
            path=path_template(u.path),
            example_url=f"{u.scheme}://{u.netloc}{u.path}",
            query_params=sorted({k for k, _ in parse_qsl(u.query)}),
            body_example=payload,
            status=response.status,
            response_shape=shape(body),
            last_seen=int(time.time()),
        )
        ep["hits"] += 1
        self.endpoints[key] = ep
        self._save(u.netloc)

    def _save(self, host: str) -> None:
        eps = [e for e in self.endpoints.values() if e["host"] == host]
        name = re.sub(r"[^A-Za-z0-9.-]", "_", host)
        (self.store / f"{name}.json").write_text(json.dumps(eps, indent=2))

    def list(self, host: str | None = None) -> list[dict]:
        return [e for e in self.endpoints.values() if host is None or host in e["host"]]
