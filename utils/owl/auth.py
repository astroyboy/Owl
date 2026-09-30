from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    base_url: str = "https://ems.sungrow.cn/service"
    login_path: str = "/security/auth/login"
    username: str = ""
    password: str = ""
    timeout: float = 20.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            base_url=os.getenv("SUNGROW_BASE_URL", cls.base_url).rstrip("/"),
            login_path=os.getenv("SUNGROW_LOGIN_PATH", cls.login_path),
            username=os.getenv("SUNGROW_USERNAME", cls.username),
            password=os.getenv("SUNGROW_PASSWORD", cls.password),
            timeout=float(os.getenv("SUNGROW_TIMEOUT", str(cls.timeout))),
        )

    @property
    def login_url(self) -> str:
        if self.login_path.startswith(("http://", "https://")):
            return self.login_path
        return f"{self.base_url}/{self.login_path.lstrip('/')}"


class SungrowApiError(RuntimeError):
    """Raised when SUNGROW rejects a request or returns an unusable response."""


class SungrowAuthenticator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def login(self, *, client: httpx.Client | None = None) -> str:
        if not self.settings.username or not self.settings.password:
            raise ValueError("SUNGROW_USERNAME and SUNGROW_PASSWORD are required")

        response = _post_login(self.settings, client=client)
        if response.get("code") != 200:
            raise SungrowApiError(
                "SUNGROW login failed; "
                f"response shape: {_describe_response(response)}"
            )
        token = _find_token(response)
        if not token:
            raise SungrowApiError(
                "SUNGROW login response did not contain a token; "
                f"response shape: {_describe_response(response)}"
            )
        return token


def _post_login(
    settings: Settings,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Send the SUNGROW login request and return its decoded JSON response."""
    payload = {
        "accountCode": settings.username,
        # The web client sends the lowercase MD5 digest, not the plain password.
        "password": hashlib.md5(
            settings.password.encode("utf-8"), usedforsecurity=False
        ).hexdigest(),
    }
    owns_client = client is None
    request_client = client or httpx.Client(timeout=settings.timeout)
    try:
        response = request_client.post(
            settings.login_url,
            json=payload,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": "https://ems.sungrow.cn",
                "Referer": "https://ems.sungrow.cn/",
                "X-AUTH-CLIENT": "web",
                "X-AUTH-SCOPE": "",
                "X-AUTH-TENANT": "",
                "X-AUTH-TOKEN": "",
                "X-LOCALE": "zh_CN",
                "Cookie": "locale=zh_CN",
            },
        )
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError as exc:
            raise SungrowApiError("SUNGROW login returned invalid JSON") from exc
        if not isinstance(body, dict):
            raise SungrowApiError("SUNGROW login returned a non-object response")
        return body
    except httpx.HTTPError as exc:
        raise SungrowApiError(f"SUNGROW login request failed: {exc}") from exc
    finally:
        if owns_client:
            request_client.close()


def _find_token(value: Any) -> str | None:
    """Accept common token response shapes without coupling later API code."""
    if isinstance(value, dict):
        for key in (
            "token",
            "accessToken",
            "access_token",
            "jwt",
            "authorization",
            "authorizetoken",
        ):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for key in ("data", "result", "payload", "body"):
            token = _find_token(value.get(key))
            if token:
                return token
    return None


def _describe_response(value: Any) -> str:
    """Describe response fields without printing credentials or token values."""
    if not isinstance(value, dict):
        return type(value).__name__

    keys = sorted(str(key) for key in value)
    details: list[str] = [f"keys={keys}"]
    for key in ("code", "msg", "message", "success"):
        if key in value and isinstance(value[key], (str, int, float, bool)):
            details.append(f"{key}={value[key]!r}")
    return ", ".join(details)
