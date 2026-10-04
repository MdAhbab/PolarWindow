"""Session tokens: what verifies, and what does not."""

from __future__ import annotations

import base64
import json
import time

import jwt
import pytest

from app.config import get_settings
from app.services import auth_service


def test_a_demo_token_is_the_project_manager_and_verifies() -> None:
    token, claims = auth_service.issue_demo()
    assert claims.role == auth_service.ROLE_MANAGER
    assert claims.role_name == "Project manager"
    back = auth_service.verify(token)
    assert back == claims
    assert back.expires_at - back.issued_at == get_settings().jwt_ttl_s


def test_a_changed_token_is_refused() -> None:
    token, _ = auth_service.issue_demo()
    head, body, sig = token.split(".")
    with pytest.raises(auth_service.InvalidToken):
        auth_service.verify(f"{head}.{body}.{sig[:-2]}AA")


def test_a_token_signed_with_another_secret_is_refused() -> None:
    now = int(time.time())
    forged = jwt.encode(
        {"sub": "x", "role": "project_manager", "iss": "polar-window", "iat": now, "exp": now + 60},
        "a-different-secret-that-is-long-enough-0123456789",
        algorithm="HS256",
    )
    with pytest.raises(auth_service.InvalidToken):
        auth_service.verify(forged)


def test_an_expired_token_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PW_JWT_TTL_S", "-10")
    get_settings.cache_clear()
    token, _ = auth_service.issue_demo()
    with pytest.raises(auth_service.InvalidToken):
        auth_service.verify(token)


def test_an_unsigned_token_is_refused() -> None:
    now = int(time.time())

    def part(d: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    claims = {"sub": "x", "role": "project_manager", "iss": "polar-window", "iat": now}
    none_alg = f"{part({'alg': 'none', 'typ': 'JWT'})}.{part({**claims, 'exp': now + 60})}."
    with pytest.raises(auth_service.InvalidToken):
        auth_service.verify(none_alg)


def test_one_click_sign_in_can_be_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PW_DEMO_SIGN_IN", "false")
    get_settings.cache_clear()
    with pytest.raises(auth_service.SignInDisabled):
        auth_service.issue_demo()


def test_production_refuses_to_start_without_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PW_ENV", "prod")
    monkeypatch.setenv("PW_JWT_SECRET", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="PW_JWT_SECRET"):
            get_settings()
    finally:
        get_settings.cache_clear()
