"""
Clerk JWT verification for the backend.

Reads CLERK_JWKS_URL from the environment and verifies RS256 Bearer tokens
issued by Clerk, returning the Clerk user_id (``sub`` claim).

Usage:
    from core.auth import verify_clerk_token

    user_id = verify_clerk_token(token)   # raises ValueError on failure

Environment:
    CLERK_JWKS_URL  — e.g. https://<your-clerk-frontend-api>/.well-known/jwks.json
"""

from __future__ import annotations

import os

import jwt
from jwt import InvalidTokenError, PyJWKClient

# Module-level singleton; populated lazily on first call to verify_clerk_token.
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = os.environ.get("CLERK_JWKS_URL", "").strip()
        if not url:
            raise RuntimeError(
                "CLERK_JWKS_URL is not set. "
                "Add it to your .env file: "
                "CLERK_JWKS_URL=https://<your-clerk-frontend-api>/.well-known/jwks.json"
            )
        _jwks_client = PyJWKClient(url)
    return _jwks_client


def reset_jwks_client() -> None:
    """Clear the cached JWKS client (used in tests to swap URLs between runs)."""
    global _jwks_client
    _jwks_client = None


def verify_clerk_token(token: str) -> str:
    """
    Verify a Clerk-issued RS256 JWT and return the Clerk user ID (``sub`` claim).

    Raises:
        ValueError: if the token is empty, expired, malformed, or fails signature verification.
        RuntimeError: if CLERK_JWKS_URL is not configured.
    """
    if not token or not token.strip():
        raise ValueError("Token is empty.")
    try:
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except InvalidTokenError as exc:
        raise ValueError(f"Token verification failed: {exc}") from exc
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Token verification failed: {exc}") from exc

    user_id = payload.get("sub", "")
    if not user_id:
        raise ValueError("Token is missing the 'sub' (user ID) claim.")
    return user_id
