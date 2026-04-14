"""Google OAuth login helpers for desktop UI authentication."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse

import requests

try:
    from .app_paths import env_file_candidates
except Exception:
    from app_paths import env_file_candidates

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


class GoogleOAuthError(RuntimeError):
    """Raised when Google OAuth login fails."""


@dataclass
class GoogleOAuthConfig:
    client_id: str
    client_secret: str
    enabled: bool
    allowed_domains: tuple[str, ...]
    admin_emails: tuple[str, ...]
    default_role: str


def _load_dotenv_file() -> None:
    if load_dotenv is None:
        return
    for dotenv_path in env_file_candidates():
        try:
            if dotenv_path.exists():
                load_dotenv(dotenv_path, override=False)
                return
        except Exception:
            continue


_load_dotenv_file()


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    items = []
    for item in raw.split(","):
        cleaned = item.strip().lower()
        if cleaned:
            items.append(cleaned)
    return tuple(items)


def _load_config() -> GoogleOAuthConfig:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    explicit_enabled = _env_flag("GOOGLE_LOGIN_ENABLED", default=False)
    enabled = explicit_enabled or bool(client_id)

    allowed_domains = _csv_env("GOOGLE_ALLOWED_DOMAINS")
    single_domain = os.getenv("GOOGLE_ALLOWED_DOMAIN", "").strip().lower()
    if single_domain:
        allowed_domains = tuple(sorted(set((*allowed_domains, single_domain))))

    admin_emails = _csv_env("GOOGLE_ADMIN_EMAILS")
    default_role = os.getenv("GOOGLE_DEFAULT_ROLE", "operator").strip().lower() or "operator"

    return GoogleOAuthConfig(
        client_id=client_id,
        client_secret=client_secret,
        enabled=enabled,
        allowed_domains=allowed_domains,
        admin_emails=admin_emails,
        default_role=default_role,
    )


def is_google_oauth_available() -> Tuple[bool, str]:
    """Return whether Google OAuth can be used and a user-friendly reason."""
    cfg = _load_config()
    if not cfg.enabled:
        return False, "Google login is disabled. Set GOOGLE_LOGIN_ENABLED=true."
    if not cfg.client_id:
        return False, "Google login needs GOOGLE_CLIENT_ID in .env."
    return True, ""


def _make_pkce_pair() -> Tuple[str, str]:
    verifier = secrets.token_urlsafe(72)
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return verifier, challenge


def _decode_id_token_payload(id_token: str) -> Dict[str, str]:
    parts = id_token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload.encode("utf-8"))
        parsed = json.loads(raw.decode("utf-8"))
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    except Exception:
        return {}
    return {}


def _resolve_role(email: str, cfg: GoogleOAuthConfig) -> str:
    if email.strip().lower() in cfg.admin_emails:
        return "admin"
    return cfg.default_role


def _validate_email_domain(email: str, cfg: GoogleOAuthConfig) -> None:
    if not cfg.allowed_domains:
        return
    _, _, domain = email.lower().rpartition("@")
    if domain in cfg.allowed_domains:
        return
    allowed = ", ".join(cfg.allowed_domains)
    raise GoogleOAuthError(f"Email domain is not allowed. Allowed domains: {allowed}")


def _exchange_code_for_tokens(
    cfg: GoogleOAuthConfig,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    timeout_sec: int,
) -> Dict[str, str]:
    payload = {
        "client_id": cfg.client_id,
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    if cfg.client_secret:
        payload["client_secret"] = cfg.client_secret

    try:
        response = requests.post(TOKEN_URL, data=payload, timeout=max(15, timeout_sec // 3))
    except Exception as exc:
        raise GoogleOAuthError(f"Failed to reach Google token endpoint: {exc}") from exc

    if not response.ok:
        detail = response.text[:300]
        raise GoogleOAuthError(f"Google token exchange failed: {detail}")

    data = response.json()
    if not isinstance(data, dict):
        raise GoogleOAuthError("Invalid token response from Google.")
    return {str(k): v for k, v in data.items()}


def _fetch_google_user_profile(tokens: Dict[str, str], timeout_sec: int) -> Dict[str, str]:
    access_token = tokens.get("access_token")
    if access_token:
        try:
            response = requests.get(
                USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=max(15, timeout_sec // 3),
            )
            if response.ok:
                data = response.json()
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
        except Exception:
            pass

    id_token = tokens.get("id_token", "")
    if id_token:
        payload = _decode_id_token_payload(id_token)
        if payload:
            return payload

    raise GoogleOAuthError("Google login succeeded but profile info could not be read.")


def login_with_google(timeout_sec: int = 180) -> Dict[str, str]:
    """Run a browser-based Google OAuth login and return a user dict."""
    cfg = _load_config()
    ok, reason = is_google_oauth_available()
    if not ok:
        raise GoogleOAuthError(reason)

    result: Dict[str, Optional[str]] = {"code": None, "error": None}
    state = secrets.token_urlsafe(16)
    code_verifier, code_challenge = _make_pkce_pair()

    class CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/oauth2callback":
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<html><body>Not found.</body></html>")
                return

            params = parse_qs(parsed.query or "")
            returned_state = (params.get("state") or [""])[0]
            if not returned_state or returned_state != state:
                result["error"] = "Invalid OAuth state."
            elif params.get("error"):
                result["error"] = (params.get("error_description") or params.get("error") or ["Login canceled"])[0]
            else:
                result["code"] = (params.get("code") or [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='font-family:Segoe UI,Arial;padding:20px;'>"
                b"<h2>Login complete</h2><p>You can close this tab and return to the app.</p>"
                b"</body></html>"
            )

    with ThreadingHTTPServer(("127.0.0.1", 0), CallbackHandler) as httpd:
        httpd.timeout = 1
        callback_port = int(httpd.server_address[1])
        redirect_uri = f"http://127.0.0.1:{callback_port}/oauth2callback"

        query = {
            "client_id": cfg.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "select_account",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "include_granted_scopes": "true",
        }
        auth_url = f"{AUTH_URL}?{urlencode(query)}"

        opened = webbrowser.open(auth_url, new=1, autoraise=True)
        if not opened:
            raise GoogleOAuthError("Could not open browser. Please open the Google login URL manually.")

        deadline = time.time() + max(60, timeout_sec)
        while time.time() < deadline and not (result.get("code") or result.get("error")):
            httpd.handle_request()

    if result.get("error"):
        raise GoogleOAuthError(str(result["error"]))
    if not result.get("code"):
        raise GoogleOAuthError("Google login timed out. Please try again.")

    tokens = _exchange_code_for_tokens(
        cfg=cfg,
        code=str(result["code"]),
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
        timeout_sec=timeout_sec,
    )
    profile = _fetch_google_user_profile(tokens, timeout_sec=timeout_sec)

    email = str(profile.get("email", "")).strip().lower()
    if not email:
        raise GoogleOAuthError("Google account email was not returned.")

    email_verified = str(profile.get("email_verified", "true")).lower()
    if email_verified in {"false", "0", "no"}:
        raise GoogleOAuthError("Google email is not verified.")

    _validate_email_domain(email, cfg)
    name = str(profile.get("name") or profile.get("given_name") or email.split("@")[0]).strip()

    return {
        "username": email,
        "email": email,
        "name": name or email,
        "role": _resolve_role(email, cfg),
        "auth_provider": "google",
    }
