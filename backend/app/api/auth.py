from typing import Annotated, cast

from fastapi import APIRouter, Cookie, Depends, Request, Response

from app.api.dependencies import Db, current_user, get_settings
from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import invalid_credentials
from app.domain.auth import AuthRead, AuthTokens, LoginRequest, PasswordChange, User, UserRead
from app.domain.review_preferences import ReviewPreferences, ReviewPreferencesUpdate
from app.domain.srs import SrsPreferences, SrsPreferencesUpdate
from app.services import auth, review_preferences, srs
from app.services.login_backoff import LoginBackoff

router = APIRouter(prefix="/api/auth", tags=["auth"])
Config = Annotated[Settings, Depends(get_settings)]
CurrentUser = Annotated[User, Depends(current_user)]
RefreshCookie = Annotated[str | None, Cookie(alias="refresh_token")]


def _public_user(user: User) -> UserRead:
    return UserRead.model_validate(user.model_dump(exclude={"password_hash"}))


def _clear_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        "refresh_token",
        path="/api/auth",
        httponly=True,
        secure=settings.app_env == "production",
        samesite="strict",
    )


def _response(tokens: AuthTokens, response: Response, settings: Settings) -> AuthRead:
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        "refresh_token",
        tokens.refresh_token,
        max_age=settings.jwt_refresh_ttl_days * 86400,
        path="/api/auth",
        httponly=True,
        secure=settings.app_env == "production",
        samesite="strict",
    )
    return AuthRead(access_token=tokens.access_token, user=_public_user(tokens.user))


@router.post("/login")
async def login(
    data: LoginRequest, request: Request, response: Response, db: Db, settings: Config
) -> AuthRead:
    protection = cast(LoginBackoff, request.app.state.login_backoff)
    key = protection.begin(data.username, request.client.host if request.client else "unknown")
    try:
        tokens = await auth.login(db, settings, data.username, data.password)
    except BaseException as exc:
        protection.finish(
            key,
            success=False,
            failed_credentials=isinstance(exc, AppError) and exc.code == "auth.invalid_credentials",
        )
        raise
    protection.finish(key, success=True)
    return _response(tokens, response, settings)


@router.post("/refresh")
async def refresh(
    response: Response, db: Db, settings: Config, refresh_token: RefreshCookie = None
) -> AuthRead:
    try:
        if refresh_token is None:
            raise invalid_credentials()
        tokens = await auth.refresh(db, settings, refresh_token)
    except AppError as exc:
        # Exception handlers own error responses; attach deletion to the domain error.
        cleared = Response()
        _clear_cookie(cleared, settings)
        exc.headers = {"Set-Cookie": cleared.headers["set-cookie"], "Cache-Control": "no-store"}
        raise
    return _response(tokens, response, settings)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    db: Db,
    settings: Config,
    user: CurrentUser,
    refresh_token: RefreshCookie = None,
) -> None:
    if refresh_token is not None:
        await auth.logout(db, refresh_token, user.id)
    _clear_cookie(response, settings)
    response.headers["Cache-Control"] = "no-store"


@router.get("/me")
async def me(response: Response, user: CurrentUser) -> UserRead:
    response.headers["Cache-Control"] = "no-store"
    return _public_user(user)


@router.post("/password")
async def password(
    data: PasswordChange, response: Response, db: Db, settings: Config, user: CurrentUser
) -> AuthRead:
    tokens = await auth.change_password(db, settings, user, data)
    return _response(tokens, response, settings)


@router.get("/me/srs-preferences")
async def srs_preferences(response: Response, db: Db, user: CurrentUser) -> SrsPreferences:
    response.headers["Cache-Control"] = "no-store"
    return await srs.read_preferences(db, user.id)


@router.patch("/me/srs-preferences")
async def patch_srs_preferences(
    data: SrsPreferencesUpdate, response: Response, db: Db, user: CurrentUser
) -> SrsPreferences:
    response.headers["Cache-Control"] = "no-store"
    return await srs.update_preferences(db, user.id, data)


@router.get("/me/review-preferences")
async def read_review_preferences(
    response: Response, db: Db, user: CurrentUser
) -> ReviewPreferences:
    response.headers["Cache-Control"] = "no-store"
    return await review_preferences.read(db, user.id)


@router.patch("/me/review-preferences")
async def patch_review_preferences(
    data: ReviewPreferencesUpdate, response: Response, db: Db, user: CurrentUser
) -> ReviewPreferences:
    response.headers["Cache-Control"] = "no-store"
    return await review_preferences.update(db, user.id, data)
