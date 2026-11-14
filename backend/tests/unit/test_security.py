import base64
from datetime import UTC, datetime

import jwt
import pytest
from pydantic_settings import SettingsConfigDict

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    validate_auth_settings,
    verify_password,
)
from app.domain.identity import user_key, user_subject


class _Settings(Settings):
    model_config = SettingsConfigDict(env_file=None)


@pytest.fixture
def settings() -> Settings:
    return _Settings(jwt_secret="unit-test-signing-secret-of-at-least-48-bytes-for-hmac")


def test_argon2id_passwords_are_salted_and_verified() -> None:
    first, second = hash_password("long-password"), hash_password("long-password")
    assert first.startswith("$argon2id$")
    assert first != second
    assert verify_password("long-password", first)
    assert not verify_password("wrong-password", first)
    assert not verify_password("long-password", "not-a-password-hash")


def test_jwt_roundtrip_and_default_ttl(settings: Settings) -> None:
    subject = user_subject("test_user")
    token = create_access_token(subject, "admin", settings)
    claims = decode_access_token(token, settings)
    assert claims.sub == subject and claims.role == "admin"
    assert claims.exp - claims.iat == 3600
    assert user_key(claims.sub) == "test_user"


@pytest.mark.parametrize(
    "change",
    [
        {"exp": 1, "iat": 0},
        {"exp": "9999999999"},
        {"exp": 9999999999.5},
        {"exp": True},
        {"exp": 0},
        {"iat": "1"},
        {"iat": 1.5},
        {"iat": True},
        {"iat": -1},
        {"iat": 9999999999},
        {"role": "superadmin"},
        {"role": ["admin"]},
        {"sub": ""},
        {"sub": "user:alice"},
        {"sub": base64.urlsafe_b64encode(b"project:alice").decode().rstrip("=")},
        {"sub": 1},
        {"sub": None},
    ],
)
def test_jwt_rejects_expired_or_invalid_claims(
    settings: Settings, change: dict[str, object]
) -> None:
    now = int(datetime.now(UTC).timestamp())
    payload = {"sub": user_subject("alice"), "role": "user", "iat": now, "exp": now + 60}
    payload.update(change)
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(AppError) as error:
        decode_access_token(token, settings)
    assert error.value.code == "auth.invalid_credentials"


@pytest.mark.parametrize("missing", ["sub", "role", "iat", "exp"])
def test_jwt_requires_every_claim(settings: Settings, missing: str) -> None:
    payload = {"sub": user_subject("alice"), "role": "user", "iat": 1, "exp": 9999999999}
    del payload[missing]
    with pytest.raises(AppError):
        decode_access_token(jwt.encode(payload, settings.jwt_secret, algorithm="HS256"), settings)


def test_jwt_rejects_tampering_and_wrong_algorithm(settings: Settings) -> None:
    subject = user_subject("alice")
    good = create_access_token(subject, "user", settings)
    header, payload, _ = good.split(".")
    tokens = [
        f"{header}.{payload}.{'A' * 43}",
        jwt.encode(
            {"sub": subject, "role": "user", "iat": 1, "exp": 9999999999},
            settings.jwt_secret,
            algorithm="HS384",
        ),
        "invalid",
    ]
    for token in tokens:
        with pytest.raises(AppError):
            decode_access_token(token, settings)


def test_refresh_tokens_have_256_bits_and_are_hashed() -> None:
    first, second = generate_refresh_token(), generate_refresh_token()
    assert len(base64.urlsafe_b64decode(first + "=")) == 32
    assert first != second
    assert len(hash_refresh_token(first)) == 64
    assert hash_refresh_token(first) != hash_refresh_token(second)


@pytest.mark.parametrize("secret", ["", "short", "replace-with-a-long-random-secret"])
def test_auth_rejects_unconfigured_secrets(secret: str) -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        validate_auth_settings(_Settings(jwt_secret=secret))
