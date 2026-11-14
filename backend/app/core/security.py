import hashlib
import secrets
from datetime import UTC, datetime
from typing import cast

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.auth import AccessClaims, Role
from app.domain.identity import user_key

_password_hash = PasswordHash((Argon2Hasher(),))


def invalid_credentials() -> AppError:
    return AppError("auth.invalid_credentials", 401, "Invalid credentials.")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(password, password_hash)
    except UnknownHashError, ValueError:
        return False


def validate_auth_settings(settings: Settings) -> None:
    if (
        len(settings.jwt_secret.encode()) < 32
        or settings.jwt_secret == "replace-with-a-long-random-secret"
    ):
        raise ValueError("JWT_SECRET must be a non-placeholder secret of at least 32 bytes")


def create_access_token(subject: str, role: Role, settings: Settings) -> str:
    validate_auth_settings(settings)
    user_key(subject)
    if role not in ("admin", "user"):
        raise ValueError("Invalid role")
    now = int(datetime.now(UTC).timestamp())
    return jwt.encode(
        {
            "sub": subject,
            "role": role,
            "iat": now,
            "exp": now + settings.jwt_access_ttl_minutes * 60,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> AccessClaims:
    validate_auth_settings(settings)
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "role", "exp", "iat"]},
        )
        sub, role, exp, iat = (payload[key] for key in ("sub", "role", "exp", "iat"))
        user_key(sub)
        if (
            role not in ("admin", "user")
            or type(exp) is not int
            or type(iat) is not int
            or exp <= iat
            or iat < 0
        ):
            raise ValueError("Invalid claims")
        return AccessClaims(sub, cast(Role, role), exp, iat)
    except jwt.InvalidTokenError, ValueError, TypeError, OverflowError:
        raise invalid_credentials() from None


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
