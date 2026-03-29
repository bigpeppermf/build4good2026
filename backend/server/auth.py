from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions
from starlette.requests import Request
from starlette.responses import JSONResponse

_log = logging.getLogger(__name__)

DEFAULT_AUTHORIZED_PARTIES = ["http://localhost:5173"]


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    clerk_session_id: str | None
    payload: dict[str, Any]


def _authorized_parties() -> list[str]:
    raw = os.getenv("CLERK_AUTHORIZED_PARTIES", "").strip()
    if not raw:
        return DEFAULT_AUTHORIZED_PARTIES.copy()
    return [value.strip() for value in raw.split(",") if value.strip()]


def require_auth(request: Request) -> AuthContext | JSONResponse:
    secret_key = os.getenv("CLERK_SECRET_KEY", "").strip()
    if not secret_key:
        return JSONResponse(
            {"error": "Server authentication is not configured."},
            status_code=500,
        )

    request_state = authenticate_request(
        request,
        AuthenticateRequestOptions(
            secret_key=secret_key,
            authorized_parties=_authorized_parties(),
            accepts_token=["session_token"],
        ),
    )

    if not request_state.is_signed_in or request_state.payload is None:
        reason_code = request_state.reason.value[0] if request_state.reason else "unknown"
        _log.warning(
            "auth rejected: reason=%s message=%s path=%s",
            reason_code,
            request_state.message,
            getattr(request, "url", "?"),
        )
        return JSONResponse(
            {
                "error": request_state.message or "Authentication required.",
                "reason": reason_code,
            },
            status_code=401,
        )

    payload = request_state.payload
    raw_user_id = payload.get("sub") or payload.get("user_id")
    user_id = raw_user_id.strip() if isinstance(raw_user_id, str) else ""
    if not user_id:
        return JSONResponse(
            {"error": "Authenticated user id is missing from the Clerk token."},
            status_code=401,
        )

    raw_session_id = payload.get("sid") or payload.get("session_id")
    clerk_session_id = (
        raw_session_id.strip()
        if isinstance(raw_session_id, str) and raw_session_id.strip()
        else None
    )

    return AuthContext(
        user_id=user_id,
        clerk_session_id=clerk_session_id,
        payload=payload,
    )
