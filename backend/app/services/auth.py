import re
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from anyio import to_thread
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    invalid_credentials,
    validate_auth_settings,
    verify_password,
)
from app.db import auth as repository
from app.domain.auth import AuthTokens, User, UserCreate


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return hash_password(generate_refresh_token())


async def create_user(db: AsyncSurrealConnection, data: UserCreate) -> User:
    password_hash = await to_thread.run_sync(hash_password, data.password)
    return await repository.create_user(db, data, password_hash)


async def bootstrap_admin(db: AsyncSurrealConnection, settings: Settings) -> None:
    validate_auth_settings(settings)
    if await repository.has_admin(db):
        return
    if not settings.admin_username or settings.admin_password in ("", "change-me"):
        raise ValueError("Initial admin credentials must be configured")
    data = UserCreate(
        username=settings.admin_username,
        password=settings.admin_password,
        role="admin",
        must_change_password=settings.app_env == "production",
        source_lang=settings.source_language,
        target_lang=settings.target_language,
    )
    password_hash = await to_thread.run_sync(hash_password, data.password)
    await repository.bootstrap_admin(db, data, password_hash)


def _tokens(user: User, refresh: str, settings: Settings) -> AuthTokens:
    return AuthTokens(user, create_access_token(user.id, user.role, settings), refresh)


async def login(
    db: AsyncSurrealConnection, settings: Settings, username: str, password: str
) -> AuthTokens:
    validate_auth_settings(settings)
    user = await repository.find_by_username(db, username)
    stored_hash = user.password_hash if user else await to_thread.run_sync(_dummy_hash)
    valid = await to_thread.run_sync(verify_password, password, stored_hash)
    if not valid or user is None or user.disabled:
        raise invalid_credentials()
    refresh = generate_refresh_token()
    current = await repository.issue_refresh(
        db,
        user.id,
        hash_refresh_token(refresh),
        datetime.now(UTC) + timedelta(days=settings.jwt_refresh_ttl_days),
    )
    if current is None:
        raise invalid_credentials()
    return _tokens(current, refresh, settings)


def _validate_refresh(token: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise invalid_credentials()


async def refresh(db: AsyncSurrealConnection, settings: Settings, token: str) -> AuthTokens:
    validate_auth_settings(settings)
    _validate_refresh(token)
    replacement = generate_refresh_token()
    now = datetime.now(UTC)
    user = await repository.consume_refresh(
        db,
        hash_refresh_token(token),
        now,
        hash_refresh_token(replacement),
        now + timedelta(days=settings.jwt_refresh_ttl_days),
    )
    # Reuse revocation must commit before the generic authentication error is raised.
    if user is None:
        raise invalid_credentials()
    return _tokens(user, replacement, settings)


async def logout(db: AsyncSurrealConnection, token: str) -> None:
    _validate_refresh(token)
    await repository.consume_refresh(db, hash_refresh_token(token), datetime.now(UTC))
