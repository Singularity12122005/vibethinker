"""Explicitly approved HTTPS transport for optional external judging."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit


class JsonTransport(Protocol):
    def post_json(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class NetworkDisabledTransport:
    """Default transport for tests and local scoring."""

    def post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("network is disabled; inject an explicitly approved transport")


@dataclass(frozen=True)
class EndpointPolicy:
    allowed_hosts: frozenset[str]
    data_sending_confirmed: bool

    def validate(self, endpoint: str) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https":
            raise ValueError("external judge endpoint must use HTTPS")
        if not parsed.hostname or parsed.hostname not in self.allowed_hosts:
            raise ValueError(f"endpoint host is not allowlisted: {parsed.hostname!r}")
        if parsed.username or parsed.password:
            raise ValueError("endpoint URL cannot contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("endpoint URL cannot contain query parameters or fragments")
        if parsed.port not in {None, 443}:
            raise ValueError("external judge endpoint must use port 443")
        if not self.data_sending_confirmed:
            raise PermissionError(
                "external judging sends prompts and model outputs; explicit confirmation "
                "is required"
            )


class HttpsJsonTransport:
    """Minimal HTTPS JSON client; credentials are read only from an environment variable."""

    def __init__(
        self,
        endpoint: str,
        *,
        policy: EndpointPolicy,
        api_key_env: str,
        timeout_seconds: float = 180,
    ) -> None:
        policy.validate(endpoint)
        if not api_key_env or "=" in api_key_env:
            raise ValueError("api_key_env must name an environment variable")
        self._endpoint = endpoint
        self._api_key_env = api_key_env
        self._timeout_seconds = timeout_seconds

    def __repr__(self) -> str:
        return (
            f"HttpsJsonTransport(endpoint={self._endpoint!r}, "
            f"api_key_env={self._api_key_env!r}, credentials=<redacted>)"
        )

    def post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        api_key = os.environ.get(self._api_key_env)
        if not api_key:
            raise RuntimeError("required API key environment variable is not set")
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                value = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"judge endpoint returned HTTP {exc.code}") from exc
        if not isinstance(value, dict):
            raise RuntimeError("judge endpoint returned a non-object response")
        return value
